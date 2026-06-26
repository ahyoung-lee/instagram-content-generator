import os
import re
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

def get_system_font(size: int, bold: bool = False):
    """
    Attempts to load custom fonts placed in the folder first, then loads standard/system fonts.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(current_dir)
    
    # 1. Scan for custom font files in the workspace root and src/ directory
    custom_fonts = []
    for directory in [workspace_root, current_dir]:
        if os.path.exists(directory):
            try:
                for f in os.listdir(directory):
                    f_lower = f.lower()
                    # Only accept .ttf or .otf, exclude default bundled fonts to avoid loop
                    if (f_lower.endswith('.ttf') or f_lower.endswith('.otf')) and f != "NanumGothic.ttf" and f != "seguiemj.ttf":
                        custom_fonts.append(os.path.join(directory, f))
            except Exception:
                pass

    if custom_fonts:
        # If bold font requested, try to find a custom font with 'bold' or 'bd' in the filename
        if bold:
            bold_customs = [f for f in custom_fonts if "bold" in os.path.basename(f).lower() or "bd" in os.path.basename(f).lower()]
            if bold_customs:
                try:
                    return ImageFont.truetype(bold_customs[0], size)
                except Exception:
                    pass
        # Try to use the first custom font found
        for f in custom_fonts:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue

    # 2. If no custom font works, fallback to system fonts
    font_paths = []
    
    if bold:
        # Prioritize Windows Malgun Gothic Bold or macOS Apple SD Gothic Neo Bold, etc.
        font_paths.extend([
            "C:\\Windows\\Fonts\\malgunbd.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo-Bold.otf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "C:\\Windows\\Fonts\\malgun.ttf", # Fallback to malgun if no malgunbd
        ])
    else:
        # Prioritize local NanumGothic font
        bundled_font_path = os.path.join(current_dir, "NanumGothic.ttf")
        if os.path.exists(bundled_font_path):
            font_paths.append(bundled_font_path)
            
        font_paths.extend([
            "C:\\Windows\\Fonts\\malgun.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/AppleGothic.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
        ])
        
    # If bold requested but no bold font succeeded, we will fallback to regular font paths
    if bold:
        bundled_font_path = os.path.join(current_dir, "NanumGothic.ttf")
        if os.path.exists(bundled_font_path):
            font_paths.append(bundled_font_path)
        font_paths.extend([
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/AppleGothic.ttf",
            "/System/Library/Fonts/Helvetica.ttc"
        ])

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Fallback to default Pillow font if none found
    return ImageFont.load_default()

def get_emoji_font(size: int):
    """
    Attempts to locate standard system emoji fonts for Windows, macOS, or Linux.
    Prioritizes the user-supplied seguiemj.ttf or bundled NotoColorEmoji.ttf font if available.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(current_dir)
    
    paths = []
    
    # Prioritize user's seguiemj.ttf in workspace root or src/
    for folder in [workspace_root, current_dir]:
        p = os.path.join(folder, "seguiemj.ttf")
        if os.path.exists(p):
            paths.append(p)
            
    # Then NotoColorEmoji.ttf
    for folder in [workspace_root, current_dir]:
        p = os.path.join(folder, "NotoColorEmoji.ttf")
        if os.path.exists(p):
            paths.append(p)
            
    # System font fallbacks
    paths.extend([
        "C:\\Windows\\Fonts\\seguiemj.ttf",  # Windows standard emoji font
        "/System/Library/Fonts/Apple Color Emoji.ttc",  # macOS standard
        "/System/Library/Fonts/Apple Color Emoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux Noto Emoji
        "/usr/share/fonts/truetype/emoji/NotoColorEmoji.ttf"
    ])
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None

def is_emoji(char: str) -> bool:
    ord_val = ord(char)
    # Common emoji Unicode blocks & modifiers
    return (
        0x1F300 <= ord_val <= 0x1F9FF or
        0x1FA70 <= ord_val <= 0x1FAFF or
        0x2600 <= ord_val <= 0x27BF or
        0x1F100 <= ord_val <= 0x1F1FF or
        # Zero Width Joiner & Variation selectors
        ord_val == 0x200D or
        0xFE00 <= ord_val <= 0xFE0F or
        # Symbols, Arrows, and Geometric Shapes (e.g. ▶)
        0x2500 <= ord_val <= 0x2BFF
    )

def split_emojis(text: str) -> list:
    segments = []
    current_segment = []
    is_current_emoji = None
    
    for char in text:
        char_is_emoji = is_emoji(char)
        if is_current_emoji is None:
            is_current_emoji = char_is_emoji
            current_segment.append(char)
        elif is_current_emoji == char_is_emoji:
            current_segment.append(char)
        else:
            segments.append(("".join(current_segment), is_current_emoji))
            current_segment = [char]
            is_current_emoji = char_is_emoji
            
    if current_segment:
        segments.append(("".join(current_segment), is_current_emoji))
        
    return segments

def draw_text_safe(draw, xy, text, fill, font, stroke_width=0, stroke_fill=None, **kwargs):
    """
    Safely draws text. Detects emojis and draws them using system emoji fonts
    if available to avoid rendering tofu (blank squares).
    """
    emoji_font = None
    if hasattr(font, "size"):
        emoji_font = get_emoji_font(font.size)
        
    s_fill = stroke_fill if stroke_fill is not None else fill

    if emoji_font is None:
        try:
            if stroke_width > 0:
                draw.text(xy, text, fill=fill, font=font, stroke_width=stroke_width, stroke_fill=s_fill, **kwargs)
            else:
                draw.text(xy, text, fill=fill, font=font, **kwargs)
        except TypeError:
            if stroke_width > 0:
                x, y = xy
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        draw.text((x + dx, y + dy), text, fill=fill, font=font, **kwargs)
            else:
                draw.text(xy, text, fill=fill, font=font, **kwargs)
        return

    # Draw segments sequentially
    segments = split_emojis(text)
    x, y = xy
    for segment, is_seg_emoji in segments:
        current_font = emoji_font if is_seg_emoji else font
        try:
            if stroke_width > 0 and not is_seg_emoji:
                draw.text((x, y), segment, fill=fill, font=current_font, stroke_width=stroke_width, stroke_fill=s_fill, **kwargs)
            else:
                draw.text((x, y), segment, fill=fill, font=current_font, **kwargs)
        except TypeError:
            if stroke_width > 0 and not is_seg_emoji:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        draw.text((x + dx, y + dy), segment, fill=fill, font=current_font, **kwargs)
            else:
                draw.text((x, y), segment, fill=fill, font=current_font, **kwargs)
                
        # Advance x coordinate
        if hasattr(draw, "textlength"):
            w = draw.textlength(segment, font=current_font)
        else:
            w = current_font.getbbox(segment)[2] - current_font.getbbox(segment)[0]
        x += w

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

def draw_logo_watermark(image: Image.Image, opacity: float = 0.45):
    """
    Loads 'img/alwaysgood_logo.png', resizes it to a suitable size,
    adjusts its opacity, and pastes it in the bottom-right corner of the image.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(current_dir)
    logo_path = os.path.join(workspace_root, "img", "alwaysgood_logo.png")
    
    if not os.path.exists(logo_path):
        # Fallback if run from workspace root
        logo_path = os.path.join("img", "alwaysgood_logo.png")
        if not os.path.exists(logo_path):
            print(f"Warning: Logo watermark not found at {logo_path}")
            return
            
    try:
        logo = Image.open(logo_path).convert("RGBA")
        
        # Determine target watermark size (e.g., width 160px)
        target_width = 160
        aspect_ratio = logo.height / logo.width
        target_height = int(target_width * aspect_ratio)
        
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.ANTIALIAS
            
        logo = logo.resize((target_width, target_height), resample_filter)
        
        # Apply opacity to alpha channel
        r, g, b, a = logo.split()
        a = a.point(lambda p: int(p * opacity))
        transparent_logo = Image.merge("RGBA", (r, g, b, a))
        
        # Place in bottom-right corner with padding
        x = WIDTH - target_width - 50
        y = HEIGHT - target_height - 50
        
        # Paste with transparent mask
        image.paste(transparent_logo, (x, y), transparent_logo)
    except Exception as e:
        print(f"Failed to draw logo watermark: {e}")

def generate_dalle_background(prompt_text: str) -> Image.Image:
    """
    Calls OpenAI Image API to generate a background image based on the provided prompt_text.
    Returns a PIL Image object, or None if generation fails.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or "your_openai_api_key" in openai_key:
        print("Warning: OPENAI_API_KEY is not configured for AI background generation. Falling back to gradient.")
        return None

    try:
        print(f"Generating AI background via OpenAI for: '{prompt_text[:50]}...'")
        client = OpenAI(api_key=openai_key)
        
        # Optimize prompt to generate a highly intuitive, direct visual concept matching the title keywords
        is_english = prompt_text and any(c.isalpha() for c in prompt_text) and not any(ord(c) > 127 for c in prompt_text)
        
        if is_english:
            prompt = (
                f"{prompt_text}. "
                "Premium high-quality visual aesthetics, center-focused composition, clean, minimalist and sophisticated. "
                "Strictly NO text, NO letters, NO words, NO label overlays, NO realistic human faces, NO signatures, NO watermarks. "
                "Suitable for a clean, modern Instagram card news background."
            )
        else:
            prompt = (
                f"A highly intuitive, clear, and direct visual concept representing the key subject of: '{prompt_text}'. "
                "This is a background for an Instagram post, so it must feature a central, iconic symbol or metaphor matching the keywords. "
                "The image must be simple, centered, visually striking, with a clean and professional layout. "
                "Strictly NO text, NO letters, NO words, NO label overlays, NO realistic human faces. "
                "Modern premium digital illustration, with a clean color scheme matching the subject."
            )
        
        try:
            # Try gpt-image-1-mini first (supported on this API key)
            response = client.images.generate(
                model="gpt-image-1-mini",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
        except Exception as e:
            print(f"gpt-image-1-mini failed: {e}. Retrying with same model or failing back.")
            # Fallback to gpt-image-1-mini just in case of transient error
            response = client.images.generate(
                model="gpt-image-1-mini",
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

def draw_card_layout(slide: dict, total_pages: int, hooking_title: str, bg_image: Image.Image = None, article_title: str = None) -> Image.Image:
    """
    Generates a single 4:5 image slide based on its content and type.
    Uses a premium glassmorphic card news layout structure for content/CTA,
    and a bold bottom-gradient layout for the cover to make the title pop.
    """
    slide_type = slide.get("type", "content")
    key_color = (255, 102, 0, 255) # #FF6600
    
    if bg_image is not None:
        # We make a copy of the pre-resized cover image
        image = bg_image.copy()
        
        # Ensure RGBA mode
        if image.mode != "RGBA":
            image = image.convert("RGBA")
            
        if slide_type != "cover":
            # Apply Gaussian Blur to content slides
            image = image.filter(ImageFilter.GaussianBlur(15))
            # Draw standard transparent overlay for content slides
            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (10, 10, 15, 80)) # ~30% opacity
            image = Image.alpha_composite(image, overlay)
        else:
            # For Cover Slide: Crisp background with bottom-up dark gradient shadow
            gradient_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(gradient_overlay)
            start_y = 500
            end_y = 1350
            for y in range(start_y, end_y):
                # Calculate alpha: linear transition from 0 to 240
                alpha = int(240 * (y - start_y) / (end_y - start_y))
                # Draw a horizontal line
                g_draw.line([(0, y), (WIDTH, y)], fill=(10, 10, 15, alpha))
            image = Image.alpha_composite(image, gradient_overlay)
    else:
        # Fallback to premium gradient if bg_image is None
        color_start = (20, 20, 30)
        color_end = (45, 20, 10)
        image = draw_gradient_background(WIDTH, HEIGHT, color_start, color_end)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
            
        if slide_type == "cover":
            # Still apply the bottom gradient overlay for consistency on fallback
            gradient_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(gradient_overlay)
            start_y = 500
            end_y = 1350
            for y in range(start_y, end_y):
                alpha = int(220 * (y - start_y) / (end_y - start_y))
                g_draw.line([(0, y), (WIDTH, y)], fill=(10, 10, 15, alpha))
            image = Image.alpha_composite(image, gradient_overlay)

    draw = ImageDraw.Draw(image)
    
    # Bottom key color brand accent bar (drawn on all pages)
    draw.rectangle([80, HEIGHT - 35, WIDTH - 80, HEIGHT - 31], fill=key_color)
    
    if slide_type == "cover":
        # Cover Page Layout (No card, text drawn directly on bottom gradient)
        
        # Render slide page indicator inside the cover area (top-right)
        page_num = slide.get("page", 1)
        page_text = f"{page_num} / {total_pages}"
        page_font = get_system_font(26)
        draw.text((WIDTH - 180, 285), page_text, fill=(180, 180, 180, 220), font=page_font)

        # Draw cover top badge
        draw.rounded_rectangle([80, 650, 390, 695], radius=15, fill=key_color)
        badge_font = get_system_font(22)
        draw.text((110, 660), "TRENDING INSIGHT", fill=(255, 255, 255, 255), font=badge_font)
        
        # Draw Main Title (Bold & Large)
        title_text = slide.get("main_text", hooking_title)
        if article_title and article_title.strip():
            clean_title = article_title.strip()
            if len(clean_title) > 35:
                title_text = clean_title[:35] + "..."
            else:
                title_text = clean_title
                
        title_font = get_system_font(84, bold=True)  # Increased from 72 to 84 for larger text
        lines = wrap_text(title_text, title_font, WIDTH - 160)
        
        y_cursor = 730
        for line in lines:
            # Draw a subtle drop shadow (semi-transparent dark gray) at (3, 3) offset
            draw_text_safe(draw, (80 + 3, y_cursor + 3), line, fill=(10, 10, 15, 200), font=title_font, stroke_width=0)
            # Set stroke_width to 0 for maximum clarity, avoiding fat/bloated rendering
            draw_text_safe(draw, (80, y_cursor), line, fill=(255, 255, 255, 255), font=title_font, stroke_width=0)
            y_cursor += 110  # Increased from 95 to 110 to match the 84 font size
            
        # Draw teaser text at the bottom
        teaser_text = "옆으로 넘겨서 핵심 요약 보기 ▶"
        teaser_font = get_system_font(26)
        draw.text((80, HEIGHT - 130), teaser_text, fill=key_color, font=teaser_font) # Placed at bottom left in key color
        
    else:
        # Define layout dimensions for content/CTA cards
        card_x0, card_y0 = 80, 240
        card_x1, card_y1 = WIDTH - 80, HEIGHT - 220
        
        # Create card overlay layer for premium glassmorphism
        card_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        
        # Choose card fill and border color based on slide type
        if slide_type == "cta":
            card_fill = (12, 12, 20, 215)  # Slightly higher opacity for final slide contrast
            card_border = (255, 102, 0, 90)  # Subtle orange highlight border
        else:
            card_fill = (12, 12, 20, 210)  # ~82% opacity
            card_border = (255, 255, 255, 40)
            
        card_draw.rounded_rectangle(
            [card_x0, card_y0, card_x1, card_y1],
            radius=35,
            fill=card_fill,
            outline=card_border,
            width=2
        )
        
        # Alpha composite the card onto the main background
        image = Image.alpha_composite(image, card_overlay)
        draw = ImageDraw.Draw(image)
        
        # Render slide page indicator inside the card (top-right corner)
        page_num = slide.get("page", 1)
        page_text = f"{page_num} / {total_pages}"
        page_font = get_system_font(26)
        draw.text((WIDTH - 180, 285), page_text, fill=(180, 180, 180, 220), font=page_font)
        
        if slide_type == "cta":
            # Draw CTA page badge (Centered)
            badge_text = "THANK YOU"
            badge_font = get_system_font(22, bold=True)
            if hasattr(badge_font, "getbbox"):
                bbox = badge_font.getbbox(badge_text)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w = len(badge_text) * 11
                text_h = 22
            box_w = text_w + 60
            x0 = (WIDTH - box_w) // 2
            x1 = x0 + box_w
            y0, y1 = 280, 325
            
            draw.rounded_rectangle([x0, y0, x1, y1], radius=15, fill=key_color)
            text_x = x0 + (box_w - text_w) // 2
            text_y = y0 + (y1 - y0 - text_h) // 2 - 2
            draw.text((text_x, text_y), badge_text, fill=(255, 255, 255, 255), font=badge_font)
            
            content_font = get_system_font(48)
            content_font_bold = get_system_font(48, bold=True)
            main_text = slide.get("main_text", "")
            lines = wrap_text(main_text, content_font, WIDTH - 260)
            
            # Center text vertically inside the card body
            line_height = 85
            total_text_height = len(lines) * line_height
            card_content_height = (HEIGHT - 220) - 360
            y_cursor = 360 + (card_content_height - total_text_height) // 2
            if y_cursor < 360:
                y_cursor = 360
                
            for idx, line in enumerate(lines):
                is_highlight = (idx == 0 or "마음에 들었다면" in line or "공유해보세요" in line)
                current_font = content_font_bold if is_highlight else content_font
                line_color = key_color if is_highlight else (255, 255, 255, 255)
                
                if hasattr(current_font, "getbbox"):
                    bbox = current_font.getbbox(line)
                    w = bbox[2] - bbox[0]
                else:
                    w = len(line) * 24
                x_pos = (WIDTH - w) // 2
                
                draw_text_safe(draw, (x_pos, y_cursor), line, fill=line_color, font=current_font)
                y_cursor += line_height

        else:
            # Standard Content Slide Layout
            # Draw Key Point badge (Centered)
            badge_text = f"KEY POINT 0{page_num - 1}" if page_num < 10 else f"KEY POINT {page_num - 1}"
            badge_font = get_system_font(22, bold=True)
            if hasattr(badge_font, "getbbox"):
                bbox = badge_font.getbbox(badge_text)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w = len(badge_text) * 11
                text_h = 22
            box_w = text_w + 60
            x0 = (WIDTH - box_w) // 2
            x1 = x0 + box_w
            y0, y1 = 280, 325
            
            draw.rounded_rectangle([x0, y0, x1, y1], radius=15, fill=key_color)
            text_x = x0 + (box_w - text_w) // 2
            text_y = y0 + (y1 - y0 - text_h) // 2 - 2
            draw.text((text_x, text_y), badge_text, fill=(255, 255, 255, 255), font=badge_font)
            
            content_font = get_system_font(44)
            content_font_bold = get_system_font(44, bold=True)
            main_text = slide.get("main_text", "")
            lines = wrap_text(main_text, content_font, WIDTH - 260)
            
            # Center text vertically inside the card body
            line_height = 75
            total_text_height = len(lines) * line_height
            card_content_height = (HEIGHT - 220) - 360 # 770 px
            y_cursor = 360 + (card_content_height - total_text_height) // 2
            if y_cursor < 360:
                y_cursor = 360
                
            for line in lines:
                # Check if this line is a header (like "1. xxx", "첫째", "1단계")
                is_header = False
                cleaned = line.strip()
                if re.match(r'^\d+\.', cleaned) or re.match(r'^\d+단계', cleaned) or cleaned.startswith(("첫째", "둘째", "셋째", "넷째", "다섯째", "마지막")):
                    is_header = True
                
                current_font = content_font_bold if is_header else content_font
                line_color = key_color if is_header else (245, 245, 250, 255)
                
                if hasattr(current_font, "getbbox"):
                    bbox = current_font.getbbox(line)
                    w = bbox[2] - bbox[0]
                else:
                    w = len(line) * 22
                x_pos = (WIDTH - w) // 2
                
                draw_text_safe(draw, (x_pos, y_cursor), line, fill=line_color, font=current_font)
                y_cursor += line_height
                
    # Apply logo watermark to the bottom right corner (outside the card)
    draw_logo_watermark(image)
    
    return image

def generate_carousel_images(plan: dict, output_dir: str, reuse_background: bool = False, article_title: str = None) -> list:
    """
    Generates all slide images based on the plan and saves them to output_dir.
    Returns a list of generated file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    total_pages = plan.get("total_pages", 4)
    hooking_title = plan.get("hooking_title", "Trending")
    image_prompt = plan.get("image_prompt", hooking_title)
    slides = plan.get("slides", [])
    
    master_bg_path = os.path.join(output_dir, "background_master.png")
    bg_image = None
    
    if reuse_background and os.path.exists(master_bg_path):
        print(f"Reusing existing background master image: {master_bg_path}")
        try:
            bg_image = Image.open(master_bg_path)
            bg_image.load()
        except Exception as e:
            print(f"Failed to load existing master background: {e}. Generating new one.")
            bg_image = None
            
    if bg_image is None:
        # Generate DALL-E master background using the detailed image_prompt
        raw_bg = generate_dalle_background(image_prompt)
        if raw_bg is not None:
            bg_image = resize_to_cover(raw_bg, WIDTH, HEIGHT)
            try:
                bg_image.save(master_bg_path, "PNG")
                print(f"Saved background master image to: {master_bg_path}")
            except Exception as e:
                print(f"Failed to save background master image: {e}")
        
    image_paths = []
    for slide in slides:
        page_num = slide.get("page", 1)
        img = draw_card_layout(slide, total_pages, hooking_title, bg_image, article_title=article_title)
        
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
