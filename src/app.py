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

# Define Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "save")
os.makedirs(SAVE_DIR, exist_ok=True)

@app.post("/api/generate")
def api_generate(payload: GenerateRequest):
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        post_dir = os.path.join(SAVE_DIR, date_str)
        os.makedirs(post_dir, exist_ok=True)
        plan_file = os.path.join(post_dir, "plan.json")
        
        # Check if cache exists and matches the requested URL
        if os.path.exists(plan_file):
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                
                cached_req_url = cached_data.get("requested_url")
                cached_image_paths = cached_data.get("absolute_paths", [])
                
                # Verify that all cached images still exist on disk
                if cached_req_url == payload.url and len(cached_image_paths) > 0:
                    all_exist = True
                    for img_path in cached_image_paths:
                        if not os.path.exists(img_path):
                            all_exist = False
                            break
                    
                    if all_exist:
                        print(f"Cache hit! Reusing existing generated files for URL: {payload.url}")
                        return {
                            "success": True,
                            "title": cached_data.get("title"),
                            "url": cached_data.get("url"),
                            "plan": cached_data.get("plan"),
                            "image_urls": cached_data.get("image_urls"),
                            "date_str": date_str,
                            "absolute_paths": cached_image_paths
                        }
            except Exception as cache_err:
                print(f"Error reading cache plan.json: {cache_err}. Proceeding with fresh generation.")

        # Step 1: Crawl URL or fallback to RSS trending topic
        trend_result = get_article_text(payload.url)
        title = trend_result.get("title", "Trending")
        content = trend_result.get("content", "")
        scraped_url = trend_result.get("url", "N/A")
        
        # Step 2: Use LLM agent to create structured slide copy and captions
        plan = generate_instagram_plan(title, content)
        
        # Step 4: Render 4:5 Pillow images
        generated_files = generate_carousel_images(plan, post_dir)
        
        # Format paths relative to static /save mount for the frontend
        relative_image_urls = []
        for file_path in generated_files:
            filename = os.path.basename(file_path)
            relative_image_urls.append(f"/save/{date_str}/{filename}")
            
        # Save to plan.json cache
        cache_content = {
            "requested_url": payload.url,
            "title": title,
            "url": scraped_url,
            "plan": plan,
            "image_urls": relative_image_urls,
            "absolute_paths": generated_files
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
            "date_str": date_str,
            "absolute_paths": generated_files
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
        return pub_result
        
    except Exception as e:
        import traceback
        print(f"Publishing error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount save directory to serve generated images
app.mount("/save", StaticFiles(directory=SAVE_DIR), name="save")

# Serve the frontend files (HTML/CSS/JS) directly from root folder
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
