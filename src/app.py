import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from src.agent_trend import get_article_text
from src.agent_creative import generate_instagram_plan
from src.script_vision import generate_carousel_images
from src.script_instagram import publish_to_instagram

app = FastAPI(title="Instagram Monetization Automation Dashboard (IMAD) API")

# Configure CORS to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class GenerateRequest(BaseModel):
    url: Optional[str] = None

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

# Define Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "save")
os.makedirs(SAVE_DIR, exist_ok=True)

@app.post("/api/generate")
def api_generate(payload: GenerateRequest):
    try:
        import hashlib
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Determine unique subfolder for this URL to isolate caching
        url_normalized = (payload.url or "trending_rss").strip().lower().rstrip('/')
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
                if cached_req_url == payload.url:
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

        # Step 1: Crawl URL or fallback to RSS trending topic
        trend_result = get_article_text(payload.url)
        title = trend_result.get("title", "Trending")
        content = trend_result.get("content", "")
        scraped_url = trend_result.get("url", "N/A")
        
        # Step 2: Use LLM agent to create structured slide copy and captions
        plan = generate_instagram_plan(title, content)
        
        # Step 4: Render 4:5 Pillow images
        generated_files = generate_carousel_images(plan, post_dir, reuse_background=reuse_background, article_title=title)
        
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
            
        # Save to plan.json cache
        cache_content = {
            "requested_url": payload.url,
            "request_count": request_count,
            "title": title,
            "url": scraped_url,
            "plan": plan,
            "image_urls": relative_image_urls,
            "absolute_paths": generated_files,
            "zip_url": relative_zip_url
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
            "zip_url": relative_zip_url
        }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Generation error: {error_details}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/publish")
def api_publish(payload: PublishRequest):
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
def api_update_title(payload: UpdateTitleRequest):
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
        
        relative_image_urls = []
        for file_path in generated_files:
            filename = os.path.basename(file_path)
            relative_image_urls.append(f"/save/{payload.date_str}/{filename}")
            
        # Update caption.txt and zip archive too
        from src.script_instagram import save_caption_file, create_zip_archive
        caption_path = save_caption_file(plan_data["plan"].get("final_caption", ""), post_dir)
        zip_path = create_zip_archive(generated_files, caption_path, post_dir)
        relative_zip_url = f"/save/{payload.date_str}/{os.path.basename(zip_path)}"
        
        return {
            "success": True,
            "image_urls": relative_image_urls,
            "zip_url": relative_zip_url,
            "absolute_paths": generated_files
        }
    except Exception as e:
        import traceback
        print(f"Update title error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prepare_download")
def api_prepare_download(payload: PrepareDownloadRequest):
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
        
        # Create ZIP containing updated files
        zip_path = create_zip_archive(generated_files, caption_path, post_dir)
        relative_zip_url = f"/save/{payload.date_str}/{os.path.basename(zip_path)}"
        
        return {
            "success": True,
            "zip_url": relative_zip_url
        }
    except Exception as e:
        import traceback
        print(f"Prepare download error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount save directory to serve generated images
app.mount("/save", StaticFiles(directory=SAVE_DIR), name="save")

# Serve the frontend files (HTML/CSS/JS) directly from root folder
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
