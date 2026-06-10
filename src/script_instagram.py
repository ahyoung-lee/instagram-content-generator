import os
import time
import requests
import json
import zipfile
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def save_caption_file(caption: str, output_dir: str) -> str:
    """
    Saves the caption text to a text file in the output directory.
    """
    os.makedirs(output_dir, exist_ok=True)
    caption_path = os.path.join(output_dir, "caption.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)
    print(f"Caption saved to: {caption_path}")
    return caption_path

def create_zip_archive(image_paths: list, caption_path: str, output_dir: str) -> str:
    """
    Creates a ZIP file containing all generated images and the caption.txt.
    Returns the path of the created ZIP file.
    """
    zip_filename = f"instagram_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        # Add images
        for img_path in image_paths:
            if os.path.exists(img_path):
                zipf.write(img_path, os.path.basename(img_path))
        # Add caption
        if os.path.exists(caption_path):
            zipf.write(caption_path, os.path.basename(caption_path))
            
    print(f"ZIP archive created at: {zip_path}")
    return zip_path

def publish_to_instagram(image_paths: list, caption: str, output_dir: str) -> dict:
    """
    Executes the Meta Graph API publishing pipeline for carousels.
    Includes fallback logging and ZIP package creation upon failure.
    """
    log_messages = []
    def log(msg):
        print(msg)
        log_messages.append(msg)

    # 1. Save caption & create ZIP early in case of later failures
    caption_path = save_caption_file(caption, output_dir)
    zip_path = create_zip_archive(image_paths, caption_path, output_dir)
    
    # Extract relative zip path for frontend download (e.g. save/YYYY-MM-DD/xxx.zip)
    # Get the relative path starting from 'save/'
    relative_zip_path = ""
    try:
        parts = zip_path.split(os.sep)
        if "save" in parts:
            idx = parts.index("save")
            relative_zip_path = "/".join(parts[idx:])
    except Exception:
        relative_zip_path = zip_path

    # Get credentials
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    access_token = os.getenv("META_ACCESS_TOKEN")
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    
    log(f"Initiating Instagram publishing for {len(image_paths)} images...")
    
    # Check basic credentials
    if not ig_user_id or "instagram_business_account_id" in ig_user_id or not access_token or "meta_access_token" in access_token:
        error_msg = "Meta Graph API credentials (INSTAGRAM_BUSINESS_ACCOUNT_ID or META_ACCESS_TOKEN) are missing or invalid."
        log(f"ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "log": "\n".join(log_messages),
            "zip_path": relative_zip_path,
            "caption": caption
        }

    container_ids = []
    
    try:
        # Phase 1: Upload each image to its own container
        for idx, img_path in enumerate(image_paths):
            # Calculate the relative path from 'save' or just the workspace directory
            # For FastAPI static serving, it's served under /save/
            filename = os.path.basename(img_path)
            # Find directory name (should be YYYY-MM-DD)
            dir_name = os.path.basename(os.path.dirname(img_path))
            
            # The URL that Facebook's servers will request to download the image
            public_image_url = f"{public_base_url}/save/{dir_name}/{filename}"
            log(f"[{idx+1}/{len(image_paths)}] Creating media container for: {public_image_url}")
            
            # Meta endpoint
            url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
            payload = {
                "image_url": public_image_url,
                "is_carousel_item": "true",
                "access_token": access_token
            }
            
            response = requests.post(url, data=payload, timeout=15)
            res_data = response.json()
            
            if response.status_code != 200:
                raise Exception(f"Failed to create image container. Status: {response.status_code}, Msg: {res_data.get('error', {}).get('message', 'Unknown error')}")
                
            container_id = res_data.get("id")
            if not container_id:
                raise Exception(f"No container ID returned in response: {res_data}")
                
            container_ids.append(container_id)
            log(f"[{idx+1}/{len(image_paths)}] Created container successfully. ID: {container_id}")

        # Phase 2: Poll status of each container to ensure they are fully processed by Meta
        log("Polling container processing status...")
        for cid in container_ids:
            max_attempts = 15
            for attempt in range(max_attempts):
                status_url = f"https://graph.facebook.com/v19.0/{cid}"
                params = {
                    "fields": "status_code",
                    "access_token": access_token
                }
                status_res = requests.get(status_url, params=params, timeout=10)
                status_data = status_res.json()
                
                if status_res.status_code != 200:
                    raise Exception(f"Failed to get container status. Status: {status_res.status_code}, Msg: {status_data.get('error', {}).get('message', 'Unknown error')}")
                
                status_code = status_data.get("status_code")
                log(f"Container {cid} status: {status_code} (Attempt {attempt+1}/{max_attempts})")
                
                if status_code == "FINISHED":
                    break
                elif status_code in ["ERROR", "EXPIRED"]:
                    raise Exception(f"Container {cid} processing failed with status: {status_code}")
                
                time.sleep(3)
            else:
                raise Exception(f"Timeout waiting for container {cid} to finish processing.")

        # Phase 3: Create Carousel Container
        log("Creating Carousel Container...")
        carousel_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
        carousel_payload = {
            "media_type": "CAROUSEL",
            "children": json.dumps(container_ids),
            "caption": caption,
            "access_token": access_token
        }
        
        carousel_res = requests.post(carousel_url, data=carousel_payload, timeout=20)
        carousel_data = carousel_res.json()
        
        if carousel_res.status_code != 200:
            raise Exception(f"Failed to create carousel container. Status: {carousel_res.status_code}, Msg: {carousel_data.get('error', {}).get('message', 'Unknown error')}")
            
        carousel_container_id = carousel_data.get("id")
        log(f"Carousel container created successfully. ID: {carousel_container_id}")

        # Phase 4: Publish Carousel
        log("Publishing Carousel on Instagram...")
        publish_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
        publish_payload = {
            "creation_id": carousel_container_id,
            "access_token": access_token
        }
        
        publish_res = requests.post(publish_url, data=publish_payload, timeout=20)
        publish_data = publish_res.json()
        
        if publish_res.status_code != 200:
            raise Exception(f"Failed to publish carousel. Status: {publish_res.status_code}, Msg: {publish_data.get('error', {}).get('message', 'Unknown error')}")
            
        post_id = publish_data.get("id")
        log(f"SUCCESS! Carousel published successfully. Post ID: {post_id}")
        
        return {
            "success": True,
            "post_id": post_id,
            "log": "\n".join(log_messages)
        }

    except Exception as e:
        error_msg = f"Instagram publishing process failed: {str(e)}"
        log(f"ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "log": "\n".join(log_messages),
            "zip_path": relative_zip_path,
            "caption": caption
        }

if __name__ == "__main__":
    # Test script execution
    print("Testing Instagram publisher module structure...")
    # Will not call live APIs without credentials
    res = publish_to_instagram([], "Test Caption #alwaysg00d", "./test_output")
    print("Test result:", res["success"])
