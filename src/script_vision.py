import os
import requests
import urllib.parse
from io import BytesIO
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define Dimensions for 4:5 Instagram Post
WIDTH = 1080
HEIGHT = 1350

def get_system_font(size: int):
    """
    Attempts to load the bundled NanumGothic font first, then falls back to macOS/system fonts.
    """
    # 1. Prioritize local NanumGothic font for Korean character support on all OS
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_font_path = os.path.join(current_dir, "NanumGothic.ttf")
    
    font_paths = []
    if os.path.exists(bundled_font_path):
        font_paths.append(bundled_font_path)
        
    # 2. System fallbacks
    font_paths.extend([
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    ])
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Fallback to default Pillow font if none found
    return ImageFont.load_default()

def draw_gradient_background(width: int, height: int, color_start: tuple, color_end: tuple) -> Image.Image:
    """
    Creates a smooth vertical linear gradient background.
    """
    base = Image.new("RGBA", (width, height), color_start)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / height
        r = int(color_start[0] + (color_end[0] - color_start[0]) * ratio)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * ratio)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    return base

def wrap_text(text: str, font, max_width: int) -> list:
    """
    Wraps text to fit within a maximum width, respecting existing newlines.
    """
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split(" ")
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word]) if current_line else word
            # Safely get text bounding box
            if hasattr(font, "getbbox"):
                bbox = font.getbbox(test_line)
                w = bbox[2] - bbox[0]
            else:
                # Fallback for old default font
                w = len(test_line) * 6
                
            if w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
    return lines

def get_relative_luminance(image: Image.Image, box: tuple) -> float:
    """
    Calculates the average relative luminance of a region in an image.
    Formula: Y = 0.2126 * R + 0.7152 * G + 0.0722 * B
    """
    cropped = image.crop(box).convert("RGB")
    pixels = list(cropped.getdata())
    if not pixels:
        return 0.0
    
    total_r, total_g, total_b = 0, 0, 0
    for r, g, b in pixels:
        total_r += r
        total_g += g
        total_b += b
        
    count = len(pixels)
    avg_r = (total_r / count) / 255.0
    avg_g = (total_g / count) / 255.0
    avg_b = (total_b / count) / 255.0
    
    return 0.2126 * avg_r + 0.7152 * avg_g + 0.0722 * avg_b

def draw_watermark(image: Image.Image, text: str = "@alwaysg00d"):
    """
    Draws a watermark at the bottom of the image, adjusting contrast
    dynamically based on the background's relative luminance.
    """
    draw = ImageDraw.Draw(image)
    font_size = 28
    font = get_system_font(font_size)
    
    # Estimate watermark size
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    else:
        w = len(text) * 16
        h = 24
        
    x = (WIDTH - w) // 2
    y = HEIGHT - 80
    
    # Calculate luminance in the target drawing box
    box = (x, y, x + w, y + h)
    luminance = get_relative_luminance(image, box)
    
    # If background is bright, draw dark gray/black. If dark, draw white.
    if luminance > 0.5:
        color = (30, 30, 30, 180) # Dark gray with opacity
    else:
        color = (240, 240, 240, 180) # Light gray with opacity
        
    draw.text((x, y), text, fill=color, font=font)

def generate_dalle_background(hooking_title: str) -> Image.Image:
    """
    Calls OpenAI Image API to generate a background image based on the hooking title.
    Returns a PIL Image object, or None if generation fails.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or "your_openai_api_key" in openai_key:
        print("Warning: OPENAI_API_KEY is not configured for AI background generation. Falling back to gradient.")
        return None

    try:
        print(f"Generating AI background via OpenAI for: '{hooking_title}'...")
        client = OpenAI(api_key=openai_key)
        
        # Optimize prompt to generate a text-free, abstract, modern dark card news background
        prompt = (
            f"A modern premium abstract visual background for an Instagram card news post about: '{hooking_title}'. "
            "Minimalist and clean layout, dark obsidian and deep navy theme with warm neon orange accent glows. "
            "Strictly NO text, NO letters, NO words, NO overlay elements, NO human faces. "
            "High resolution, smooth colors, professional digital art style."
        )
        
        try:
            # Try gpt-image-1-mini first (extremely cost-efficient, approx 4x cheaper)
            response = client.images.generate(
                model="gpt-image-1-mini",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
        except Exception as e:
            print(f"gpt-image-1-mini failed: {e}. Trying gpt-image-2 fallback...")
            # Fallback to gpt-image-2 (higher quality flagship, more expensive)
            response = client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            
        # Parse result: support both url and base64 formats
        image_data = response.data[0]
        if hasattr(image_data, 'b64_json') and image_data.b64_json:
            import base64
            print("AI image generated successfully (Base64 format).")
            return Image.open(BytesIO(base64.b64decode(image_data.b64_json)))
        elif hasattr(image_data, 'url') and image_data.url:
            image_url = image_data.url
            print(f"AI image generated successfully (URL format): {image_url}")
            img_response = requests.get(image_url, timeout=15)
            img_response.raise_for_status()
            return Image.open(BytesIO(img_response.content))
        else:
            raise ValueError("No image data (b64_json or url) returned in OpenAI response.")
    except Exception as e:
        print(f"Error generating AI background via OpenAI: {e}. Falling back to gradient.")
        return None

def resize_to_cover(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """
    Resizes and crops a PIL Image to cover the target dimensions (aspect ratio fill).
    """
    img_w, img_h = image.size
    target_ratio = target_width / target_height
    img_ratio = img_w / img_h

    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.ANTIALIAS

    if img_ratio > target_ratio:
        # Image is wider than target ratio: scale based on height
        new_h = target_height
        new_w = int(img_w * (target_height / img_h))
    else:
        # Image is taller than target ratio: scale based on width
        new_w = target_width
        new_h = int(img_h * (target_width / img_w))

    resized_img = image.resize((new_w, new_h), resample_filter)

    # Crop the center
    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2
    right = left + target_width
    bottom = top + target_height

    return resized_img.crop((left, top, right, bottom))

def draw_card_layout(slide: dict, total_pages: int, hooking_title: str, bg_image: Image.Image = None) -> Image.Image:
    """
    Generates a single 4:5 image slide based on its content and type.
    If bg_image is provided, it is used as the visual backdrop.
    """
    slide_type = slide.get("type", "content")
    
    if bg_image is not None:
        # We make a copy of the pre-resized cover image
        image = bg_image.copy()
        
        # Ensure RGBA mode
        if image.mode != "RGBA":
            image = image.convert("RGBA")
            
        if slide_type != "cover":
            # Apply Gaussian Blur to content slides
            image = image.filter(ImageFilter.GaussianBlur(20))
            
        # Draw transparent overlay for readability
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        if slide_type == "cover":
            # 55% opacity dark overlay for cover
            draw_overlay.rectangle([0, 0, WIDTH, HEIGHT], fill=(10, 10, 15, 140))
        else:
            # 80% opacity dark overlay for content slides
            draw_overlay.rectangle([0, 0, WIDTH, HEIGHT], fill=(10, 10, 15, 204))
            
        image = Image.alpha_composite(image, overlay)
    else:
        # Fallback to premium gradient if bg_image is None
        color_start = (20, 20, 30)
        color_end = (45, 20, 10)
        image = draw_gradient_background(WIDTH, HEIGHT, color_start, color_end)
        
    draw = ImageDraw.Draw(image)
    
    # Key color accent line (bottom border accent)
    key_color = (255, 102, 0, 255) # #FF6600
    draw.rectangle([50, HEIGHT - 30, WIDTH - 50, HEIGHT - 25], fill=key_color)
    
    # Render slide page indicator
    page_num = slide.get("page", 1)
    page_text = f"{page_num} / {total_pages}"
    page_font = get_system_font(24)
    draw.text((WIDTH - 100, 50), page_text, fill=(180, 180, 180, 255), font=page_font)
    
    if slide_type == "cover":
        # Cover Page Layout
        title_font = get_system_font(68)
        subtitle_font = get_system_font(32)
        
        # Draw top accent label
        draw.text((100, 150), "TRENDING INSIGHT", fill=key_color, font=subtitle_font)
        
        # Draw Main Title
        title_text = slide.get("main_text", hooking_title)
        lines = wrap_text(title_text, title_font, WIDTH - 200)
        
        y_cursor = 350
        for line in lines:
            draw.text((100, y_cursor), line, fill=(255, 255, 255, 255), font=title_font)
            y_cursor += 90
            
        # Draw CTA teaser at the bottom
        teaser_text = "옆으로 넘겨서 핵심 요약 보기 ▶"
        draw.text((100, HEIGHT - 150), teaser_text, fill=(200, 200, 200, 255), font=subtitle_font)
        
    elif slide_type == "cta":
        # CTA Page Layout
        title_font = get_system_font(52)
        content_font = get_system_font(42)
        
        # Draw top accent
        draw.text((100, 150), "WHAT TO DO NEXT", fill=key_color, font=get_system_font(32))
        
        main_text = slide.get("main_text", "")
        lines = wrap_text(main_text, content_font, WIDTH - 200)
        
        y_cursor = 350
        for line in lines:
            draw.text((100, y_cursor), line, fill=(255, 255, 255, 255), font=content_font)
            y_cursor += 75
            
        # Draw action encouragement icon representation
        draw.rectangle([100, y_cursor + 50, WIDTH - 100, y_cursor + 52], fill=(255, 102, 0, 100))
        draw.text((100, y_cursor + 80), "❤ 좋아요 | 💾 저장 | 🚀 공유 | 👤 팔로우", fill=(200, 200, 200, 255), font=get_system_font(28))

    else:
        # Standard Content Layout
        header_font = get_system_font(36)
        content_font = get_system_font(45)
        
        # Draw header section
        header_text = f"KEY POINT 0{page_num - 1}" if page_num < 10 else f"KEY POINT {page_num - 1}"
        draw.text((100, 150), header_text, fill=key_color, font=header_font)
        
        main_text = slide.get("main_text", "")
        lines = wrap_text(main_text, content_font, WIDTH - 200)
        
        y_cursor = 350
        for line in lines:
            draw.text((100, y_cursor), line, fill=(255, 255, 255, 255), font=content_font)
            y_cursor += 80
            
    # Apply relative luminance watermark
    draw_watermark(image, "@alwaysg00d")
    
    return image

def generate_carousel_images(plan: dict, output_dir: str) -> list:
    """
    Generates all slide images based on the plan and saves them to output_dir.
    Returns a list of generated file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    total_pages = plan.get("total_pages", 4)
    hooking_title = plan.get("hooking_title", "Trending")
    slides = plan.get("slides", [])
    
    # Generate DALL-E master background
    raw_bg = generate_dalle_background(hooking_title)
    bg_image = None
    if raw_bg is not None:
        bg_image = resize_to_cover(raw_bg, WIDTH, HEIGHT)
        
    image_paths = []
    for slide in slides:
        page_num = slide.get("page", 1)
        img = draw_card_layout(slide, total_pages, hooking_title, bg_image)
        
        filename = f"slide_{page_num:02d}.jpg"
        filepath = os.path.join(output_dir, filename)
        
        # Save as JPEG (Quality: 95)
        img.convert("RGB").save(filepath, "JPEG", quality=95)
        image_paths.append(filepath)
        print(f"Generated and saved: {filepath}")
        
    return image_paths

if __name__ == "__main__":
    # Test layout generation
    test_plan = {
        "total_pages": 3,
        "hooking_title": "테스트 카드뉴스",
        "slides": [
            {"page": 1, "type": "cover", "main_text": "인스타 자동화로\n돈 버는 비밀 공개"},
            {"page": 2, "type": "content", "main_text": "첫째, 트렌드를 분석하고\n둘째, 카피라이팅을 자동화합니다."},
            {"page": 3, "type": "cta", "main_text": "더 보려면 프로필 링크 클릭!"}
        ]
    }
    generate_carousel_images(test_plan, "./test_output")
