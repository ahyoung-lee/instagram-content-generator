import os
import re
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from src.agent_trend import get_article_text
from src.agent_creative import generate_instagram_plan
from src.script_vision import generate_carousel_images
from src.script_instagram import publish_to_instagram

app = FastAPI(title="Instagram Monetization Automation Dashboard (IMAD) API")

# Presenter-only access key. When ACCESS_KEY is set (e.g. on Render), the
# costly API endpoints require a matching "X-Access-Key" header so that only
# the presenter can trigger paid generation. If it is empty/unset, the API
# stays open (convenient for local development).
ACCESS_KEY = os.getenv("ACCESS_KEY", "").strip()

def verify_access(x_access_key: Optional[str]):
    """Rejects the request unless the caller supplied the correct access key.

    No-op when ACCESS_KEY is not configured, keeping local dev frictionless.
    """
    if not ACCESS_KEY:
        return
    if not x_access_key or x_access_key != ACCESS_KEY:
        raise HTTPException(
            status_code=401,
            detail="접근 권한이 없습니다. 발표자 전용 액세스 키가 필요합니다.",
        )

# Configure CORS to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
# (/api/generate takes multipart form data instead of JSON, because it also
#  accepts an optional background photo upload.)
class PublishRequest(BaseModel):
    image_paths: List[str]
    caption: str
    date_str: str

class UpdateTitleRequest(BaseModel):
    date_str: str
    title: str

class PrepareDownloadRequest(BaseModel):
    date_str: str
    caption: str
    title: str

class CreateReelRequest(BaseModel):
    date_str: str

class DeleteImageRequest(BaseModel):
    date_str: str
    filename: str

# Define Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "save")
os.makedirs(SAVE_DIR, exist_ok=True)

# --- Slide ordering ("sequence") helpers ---
# A post's card order is stored as plan.json["sequence"], an ordered list of
# filenames in the post folder, so downloads and reels honor the exact order.
# It holds the AI cards (slide_XX.jpg) plus any standalone photos (extra_*.jpg)
# left over from posts made before photos became part of a card.

def _plan_path(post_dir: str) -> str:
    return os.path.join(post_dir, "plan.json")

def _load_plan_data(post_dir: str) -> dict:
    with open(_plan_path(post_dir), "r", encoding="utf-8") as f:
        return json.load(f)

def _save_plan_data(post_dir: str, data: dict) -> None:
    with open(_plan_path(post_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def _default_sequence(post_dir: str) -> List[str]:
    """Filenames of the AI cards on disk, in page order (fallback when no sequence)."""
    import glob
    return [os.path.basename(p) for p in sorted(glob.glob(os.path.join(post_dir, "slide_*.jpg")))]

def _get_sequence(post_dir: str, data: dict) -> List[str]:
    seq = data.get("sequence")
    if not seq:
        seq = _default_sequence(post_dir)
    # Drop any entries whose files no longer exist on disk.
    return [name for name in seq if os.path.exists(os.path.join(post_dir, name))]

def _ordered_paths(post_dir: str, data: dict) -> List[str]:
    return [os.path.join(post_dir, name) for name in _get_sequence(post_dir, data)]

def _urls_from_sequence(date_str: str, sequence: List[str]) -> List[str]:
    return [f"/save/{date_str}/{name}" for name in sequence]

# --- Per-card user photos ---
# A user photo is not its own slide: it is stored as plan["slides"][i]["user_photo"]
# and drawn across the top of that card, with the card's copy shrunk underneath.

def _page_from_slide_name(name: str) -> int:
    """"slide_02.jpg" -> 2. Raises a 400 for anything that isn't a generated card."""
    match = re.match(r"^slide_(\d+)\.jpg$", os.path.basename(name or ""))
    if not match:
        raise HTTPException(status_code=400, detail="생성된 카드에만 사진을 넣을 수 있습니다.")
    return int(match.group(1))

def _find_slide(data: dict, page: int) -> Optional[dict]:
    for slide in data.get("plan", {}).get("slides", []):
        if int(slide.get("page", 0)) == page:
            return slide
    return None

def _photo_slides(data: dict) -> List[str]:
    """Filenames of the cards that currently carry a user photo (for the UI)."""
    return [
        f"slide_{int(slide.get('page', 0)):02d}.jpg"
        for slide in data.get("plan", {}).get("slides", [])
        if slide.get("user_photo")
    ]

def _rerender_response(date_str: str, post_dir: str, data: dict) -> dict:
    """
    Re-draws every card from the stored plan and returns the refreshed carousel.
    Reuses background_master.png, so this never calls the paid image API.
    """
    generate_carousel_images(
        data["plan"],
        post_dir,
        reuse_background=True,
        article_title=data.get("title"),
        allow_paid_background=False,
    )
    sequence = _get_sequence(post_dir, data)
    return {
        "success": True,
        "image_urls": _urls_from_sequence(date_str, sequence),
        "sequence": sequence,
        "photo_slides": _photo_slides(data),
    }

@app.post("/api/generate")
async def api_generate(
    url: Optional[str] = Form(default=None),
    background: Optional[UploadFile] = File(default=None),
    x_access_key: Optional[str] = Header(default=None),
):
    """
    Builds a carousel for `url` (or today's trending topic when it is empty).

    An optional `background` photo replaces the AI-generated cover artwork: the
    uploaded image becomes this post's background master, so no paid image call
    is made. Without a photo the background is generated as before.
    """
    verify_access(x_access_key)
    try:
        import hashlib
        date_str = datetime.now().strftime("%Y-%m-%d")

        # An empty form field arrives as "" -> treat it the same as "no URL".
        url = (url or "").strip() or None

        # Read the attached photo (if any) before anything expensive happens.
        custom_bg_bytes = None
        if background is not None and (background.filename or "").strip():
            if not (background.content_type or "").lower().startswith("image/"):
                raise HTTPException(status_code=400, detail="이미지 파일만 첨부할 수 있습니다.")
            custom_bg_bytes = await background.read()
            if not custom_bg_bytes:
                raise HTTPException(status_code=400, detail="빈 파일입니다.")

        # Determine unique subfolder for this URL to isolate caching
        url_normalized = (url or "trending_rss").strip().lower().rstrip('/')
        url_hash = hashlib.md5(url_normalized.encode('utf-8')).hexdigest()[:12]

        post_dir = os.path.join(SAVE_DIR, date_str, url_hash)
        os.makedirs(post_dir, exist_ok=True)
        plan_file = os.path.join(post_dir, "plan.json")

        # Check if cache exists and matches the requested URL for background image reuse
        reuse_background = False
        request_count = 1
        if os.path.exists(plan_file):
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)

                cached_req_url = cached_data.get("requested_url")
                if cached_req_url == url:
                    prev_count = cached_data.get("request_count", 1)
                    request_count = prev_count + 1
                    
                    # If request_count is even (2nd, 4th, etc. request), reuse the background image
                    if request_count % 2 == 0:
                        reuse_background = True
                        print(f"Same URL requested (count {request_count}). Will reuse background image.")
                    else:
                        reuse_background = False
                        print(f"Same URL requested (count {request_count}). Generating a NEW background image.")
            except Exception as cache_err:
                print(f"Error reading cache plan.json for background check: {cache_err}")

        # An attached photo becomes the background master and is always reused,
        # which also bypasses the parity rule above (and the paid image API).
        if custom_bg_bytes:
            from src.script_vision import save_background_master
            save_background_master(custom_bg_bytes, post_dir)
            reuse_background = True
            print("Using the uploaded photo as the background; skipping AI background generation.")

        # Step 1: Crawl URL or fallback to RSS trending topic
        trend_result = get_article_text(url)
        title = trend_result.get("title", "Trending")
        content = trend_result.get("content", "")
        scraped_url = trend_result.get("url", "N/A")
        
        # Step 2: Use LLM agent to create structured slide copy and captions
        plan = generate_instagram_plan(title, content)

        # The post title is the AI's click-worthy rewrite of the headline, not the
        # raw scraped one. The original is kept as source_title for reference.
        source_title = title
        title = (plan.get("hooking_title") or "").strip() or source_title

        # Step 4: Render 4:5 Pillow images
        generated_files = generate_carousel_images(
            plan,
            post_dir,
            reuse_background=reuse_background,
            article_title=title,
            allow_paid_background=not custom_bg_bytes,
        )
        
        # Format paths relative to static /save mount for the frontend
        relative_image_urls = []
        for file_path in generated_files:
            filename = os.path.basename(file_path)
            relative_image_urls.append(f"/save/{date_str}/{url_hash}/{filename}")
            
        # Automatically save caption file and create ZIP archive
        from src.script_instagram import save_caption_file, create_zip_archive
        caption_path = save_caption_file(plan.get("final_caption", ""), post_dir)
        zip_path = create_zip_archive(generated_files, caption_path, post_dir)
        relative_zip_url = f"/save/{date_str}/{url_hash}/{os.path.basename(zip_path)}"
            
        # Ordered list of card filenames (AI cards now; user photos inserted later).
        sequence = [os.path.basename(p) for p in generated_files]

        # Save to plan.json cache
        cache_content = {
            "requested_url": url,
            "request_count": request_count,
            "custom_background": bool(custom_bg_bytes),
            "title": title,
            "source_title": source_title,
            "url": scraped_url,
            "plan": plan,
            "image_urls": relative_image_urls,
            "absolute_paths": generated_files,
            "zip_url": relative_zip_url,
            "sequence": sequence
        }
        try:
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(cache_content, f, ensure_ascii=False, indent=4)
        except Exception as cache_save_err:
            print(f"Error saving cache plan.json: {cache_save_err}")
            
        # Return plan along with the paths
        return {
            "success": True,
            "title": title,
            "url": scraped_url,
            "plan": plan,
            "image_urls": relative_image_urls,
            "date_str": f"{date_str}/{url_hash}",
            "absolute_paths": generated_files,
            "zip_url": relative_zip_url,
            "photo_slides": []  # a fresh post has no user photos attached yet
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Generation error: {error_details}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/insert_image")
async def api_insert_image(
    date_str: str = Form(...),
    target: str = Form(...),
    file: UploadFile = File(...),
    x_access_key: Optional[str] = Header(default=None),
):
    """
    Attaches a user-uploaded photo to one generated card (`target`, e.g.
    "slide_02.jpg"). The photo is drawn across the top of that card and the
    card's copy shrinks and moves below it, so no extra slide is added.
    """
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, date_str)
        if not os.path.exists(_plan_path(post_dir)):
            raise HTTPException(status_code=404, detail="콘텐츠를 먼저 생성해 주세요.")

        # Basic validation: only accept image uploads.
        if not (file.content_type or "").lower().startswith("image/"):
            raise HTTPException(status_code=400, detail="이미지 파일만 삽입할 수 있습니다.")

        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="빈 파일입니다.")

        data = _load_plan_data(post_dir)
        page = _page_from_slide_name(target)
        slide = _find_slide(data, page)
        if slide is None:
            raise HTTPException(status_code=400, detail="사진을 넣을 카드를 찾을 수 없습니다.")
        if slide.get("type") == "cover":
            raise HTTPException(status_code=400, detail="표지에는 사진을 넣을 수 없습니다.")

        # One photo per card: a re-upload overwrites the previous file.
        from src.script_vision import save_uploaded_photo
        photo_name = f"photo_{page:02d}.jpg"
        save_uploaded_photo(contents, post_dir, photo_name)
        slide["user_photo"] = photo_name
        _save_plan_data(post_dir, data)

        return _rerender_response(date_str, post_dir, data)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Insert image error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/delete_image")
def api_delete_image(payload: DeleteImageRequest, x_access_key: Optional[str] = Header(default=None)):
    """
    Removes an image from the carousel order. Standalone photos inserted by older
    versions (extra_*) are also deleted from disk; AI cards are only removed from
    the sequence so they can be restored by a re-render.
    """
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, payload.date_str)
        if not os.path.exists(_plan_path(post_dir)):
            raise HTTPException(status_code=404, detail="콘텐츠를 먼저 생성해 주세요.")

        name = os.path.basename(payload.filename)  # guard against path traversal
        data = _load_plan_data(post_dir)
        sequence = [n for n in _get_sequence(post_dir, data) if n != name]
        data["sequence"] = sequence
        _save_plan_data(post_dir, data)

        # Physically remove standalone user photos only.
        if name.startswith("extra_"):
            try:
                os.remove(os.path.join(post_dir, name))
            except OSError:
                pass

        return {
            "success": True,
            "image_urls": _urls_from_sequence(payload.date_str, sequence),
            "sequence": sequence,
            "photo_slides": _photo_slides(data),
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Delete image error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/remove_photo")
def api_remove_photo(payload: DeleteImageRequest, x_access_key: Optional[str] = Header(default=None)):
    """
    Detaches the user photo from a card ("slide_02.jpg") and redraws it, so the
    card goes back to the full-size copy layout.
    """
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, payload.date_str)
        if not os.path.exists(_plan_path(post_dir)):
            raise HTTPException(status_code=404, detail="콘텐츠를 먼저 생성해 주세요.")

        data = _load_plan_data(post_dir)
        page = _page_from_slide_name(payload.filename)
        slide = _find_slide(data, page)
        if slide is None or not slide.get("user_photo"):
            raise HTTPException(status_code=400, detail="이 카드에는 삽입된 사진이 없습니다.")

        photo_name = os.path.basename(slide.pop("user_photo"))
        _save_plan_data(post_dir, data)
        try:
            os.remove(os.path.join(post_dir, photo_name))
        except OSError:
            pass

        return _rerender_response(payload.date_str, post_dir, data)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Remove photo error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/publish")
def api_publish(payload: PublishRequest, x_access_key: Optional[str] = Header(default=None)):
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, payload.date_str)
        
        # Resolve absolute paths if the frontend sends relative paths
        resolved_paths = []
        for path in payload.image_paths:
            if path.startswith("/save/") or path.startswith("save/"):
                # strip leadings
                clean_path = path.replace("/save/", "").replace("save/", "")
                resolved_paths.append(os.path.join(SAVE_DIR, clean_path))
            else:
                resolved_paths.append(path)
                
        # Call publishing pipeline
        pub_result = publish_to_instagram(resolved_paths, payload.caption, post_dir)
        
        # Automatically copy the published/edited images, caption and zip to today's date folder
        try:
            import shutil
            daily_dir = os.path.dirname(post_dir)
            if daily_dir != SAVE_DIR: # Make sure we copy to save/YYYY-MM-DD instead of save/
                os.makedirs(daily_dir, exist_ok=True)
                for file_path in resolved_paths:
                    if os.path.exists(file_path):
                        shutil.copy(file_path, os.path.join(daily_dir, os.path.basename(file_path)))
                
                # Copy caption.txt and zip files if they exist in post_dir
                caption_file = os.path.join(post_dir, "caption.txt")
                if os.path.exists(caption_file):
                    # Update caption.txt with user-edited caption inside today's folder
                    with open(os.path.join(daily_dir, "caption.txt"), "w", encoding="utf-8") as f:
                        f.write(payload.caption)
                
                # Copy zip
                for filename in os.listdir(post_dir):
                    if filename.endswith(".zip"):
                        shutil.copy(os.path.join(post_dir, filename), os.path.join(daily_dir, filename))
                print(f"Automatically saved/copied publication assets to: {daily_dir}")
        except Exception as copy_err:
            print(f"Error copying publication assets to daily dir: {copy_err}")
            
        return pub_result
        
    except Exception as e:
        import traceback
        print(f"Publishing error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/update_title")
def api_update_title(payload: UpdateTitleRequest, x_access_key: Optional[str] = Header(default=None)):
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, payload.date_str)
        plan_file = os.path.join(post_dir, "plan.json")
        
        if not os.path.exists(plan_file):
            raise HTTPException(status_code=404, detail="Plan file not found")
            
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
            
        # Update fields
        plan_data["title"] = payload.title
        # Also update the title in the first slide if it is a cover slide
        if plan_data.get("plan", {}).get("slides"):
            plan_data["plan"]["slides"][0]["main_text"] = payload.title
            
        # Write updated plan back to cache
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=4)
            
        # Re-render Pillow images
        # Since background_master.png exists, it will reuse it (reuse_background=True)
        generated_files = generate_carousel_images(
            plan_data["plan"], 
            post_dir, 
            reuse_background=True, 
            article_title=payload.title
        )
        
        # Re-rendering rewrites the slide_XX files in place, so the stored
        # sequence (incl. any inserted photos) stays valid. Return it in order.
        sequence = _get_sequence(post_dir, plan_data)
        relative_image_urls = _urls_from_sequence(payload.date_str, sequence)

        # Update caption.txt and zip archive too (zip follows the sequence order)
        from src.script_instagram import save_caption_file, create_zip_archive
        caption_path = save_caption_file(plan_data["plan"].get("final_caption", ""), post_dir)
        zip_path = create_zip_archive(_ordered_paths(post_dir, plan_data), caption_path, post_dir)
        relative_zip_url = f"/save/{payload.date_str}/{os.path.basename(zip_path)}"
        
        return {
            "success": True,
            "image_urls": relative_image_urls,
            "zip_url": relative_zip_url,
            "absolute_paths": generated_files,
            "photo_slides": _photo_slides(plan_data)
        }
    except Exception as e:
        import traceback
        print(f"Update title error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prepare_download")
def api_prepare_download(payload: PrepareDownloadRequest, x_access_key: Optional[str] = Header(default=None)):
    verify_access(x_access_key)
    try:
        post_dir = os.path.join(SAVE_DIR, payload.date_str)
        plan_file = os.path.join(post_dir, "plan.json")
        
        if not os.path.exists(plan_file):
            raise HTTPException(status_code=404, detail="Plan file not found")
            
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
            
        # Update title & caption in memory and cache
        plan_data["title"] = payload.title
        if plan_data.get("plan", {}).get("slides"):
            plan_data["plan"]["slides"][0]["main_text"] = payload.title
        plan_data["plan"]["final_caption"] = payload.caption
        
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=4)
            
        # Re-render Pillow images
        generated_files = generate_carousel_images(
            plan_data["plan"], 
            post_dir, 
            reuse_background=True, 
            article_title=payload.title
        )
        
        # Save sufficed/edited caption
        from src.script_instagram import save_caption_file, create_zip_archive
        caption_path = save_caption_file(payload.caption, post_dir)

        # Create ZIP following the sequence order (includes inserted photos)
        zip_path = create_zip_archive(_ordered_paths(post_dir, plan_data), caption_path, post_dir)
        relative_zip_url = f"/save/{payload.date_str}/{os.path.basename(zip_path)}"
        
        return {
            "success": True,
            "zip_url": relative_zip_url
        }
    except Exception as e:
        import traceback
        print(f"Prepare download error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/create_reel")
def api_create_reel(payload: CreateReelRequest, x_access_key: Optional[str] = Header(default=None)):
    """
    Stitches the already-generated card images for a post into an
    Instagram-Reels-ready MP4 (1080x1920, cross-fade between cards).
    """
    verify_access(x_access_key)
    try:
        import glob
        post_dir = os.path.join(SAVE_DIR, payload.date_str)

        # Prefer the saved sequence (AI cards + inserted photos, in order);
        # fall back to whatever slide images are on disk.
        slide_files = []
        if os.path.exists(_plan_path(post_dir)):
            slide_files = _ordered_paths(post_dir, _load_plan_data(post_dir))
        if not slide_files:
            slide_files = sorted(glob.glob(os.path.join(post_dir, "slide_*.jpg")))
        print(f"[reel] request date_str={payload.date_str}, slides={len(slide_files)}", flush=True)
        if not slide_files:
            raise HTTPException(status_code=404, detail="릴스로 만들 카드 이미지를 찾을 수 없습니다. 먼저 콘텐츠를 생성해 주세요.")

        from src.script_reels import create_reel_video
        reel_path = create_reel_video(slide_files, post_dir)

        relative_reel_url = f"/save/{payload.date_str}/{os.path.basename(reel_path)}"
        print(f"[reel] success -> {relative_reel_url}", flush=True)
        return {
            "success": True,
            "reel_url": relative_reel_url
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[reel] ERROR: {traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))

# Mount save directory to serve generated images
app.mount("/save", StaticFiles(directory=SAVE_DIR), name="save")

# Serve the frontend files (HTML/CSS/JS) directly from root folder
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
