import os
import re
import random
import requests
import urllib.parse
from io import BytesIO
from typing import Optional
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define Dimensions for 4:5 Instagram Post
WIDTH = 1080
HEIGHT = 1350

# Card canvases. Every card is drawn natively at its canvas size, so text stays
# crisp: "portrait" is the 4:5 Instagram carousel, "landscape" the 16:9 YouTube
# frame and "story" the 9:16 Shorts/Reels frame. `paper` holds every position
# the newspaper layout needs, so the shapes share one code path.
CANVASES = {
    "portrait": {
        "size": (WIDTH, HEIGHT),
        "margin": 80,
        "paper": {
            "header_top": 95, "header_h": 56, "header_font": 26,
            "rule_y": 1245, "logo": 92, "page_font": 24,
            # Cover headline zone and sub-copy typed under it on the dashboard.
            "title_top": 215, "title_bottom": 740, "title_wrap": 920,
            "title_steps": ((84, 100), (76, 92), (68, 84), (60, 74)),
            "sub_font": 30, "sub_line": 44, "sub_gap": 22, "sub_wrap": 920,
            # Cover photo box: its top follows the headline (min..given), its
            # bottom is fixed.
            "photo_box": (80, 800, 1000, 1180), "photo_top_min": 600, "shadow": 14,
            # Content cards and the one-card post.
            "body_top": 205, "body_bottom": 1190, "card_wrap": 920,
            "badge_font": 24, "badge_h": 48, "badge_gap": 34,
            "body": (46, 74), "body_photo": (38, 58),      # (size, line height)
            "cta": (50, 80), "cta_photo": (40, 62), "min_line": 46,
            "photo_min": 300, "photo_max": 560, "photo_gap": 44,
            # (headline size, headline line, body size, body line)
            "single_steps": ((76, 90, 36, 56), (68, 82, 34, 52), (60, 74, 31, 47), (54, 66, 28, 43)),
            "single_photo_min": 240,
        },
        # Card 2 (spotlight): label spot, photo circle (center x, center y,
        # radius), the black fade (start y, fully black y), and the centered
        # headline + body block (its center y, wrap width, headline (size, line
        # height) steps, body (size, line height), gap between them).
        "spotlight": {
            "label": (80, 46, 24), "circle": (540, 640, 600), "fade": (420, 1180),
            "center_y": 675, "title_wrap": 940, "body": (34, 52), "body_gap": 34,
            "title_steps": ((104, 150), (94, 136), (84, 122), (74, 108)),
        },
    },
    "landscape": {
        # 1920x1080 is YouTube's recommended long-form size; the video step
        # scales it down to 1280x720. Photos sit in a column beside the copy.
        "size": (1920, 1080),
        "margin": 140,
        "paper": {
            "header_top": 70, "header_h": 60, "header_font": 28,
            "rule_y": 975, "logo": 96, "page_font": 26,
            "title_top": 200, "title_bottom": 920, "title_wrap": 820,
            "title_steps": ((92, 110), (84, 100), (76, 92), (68, 82)),
            "sub_font": 34, "sub_line": 50, "sub_gap": 26, "sub_wrap": 820,
            "photo_box": (1030, 200, 1764, 900), "photo_top_min": 200, "shadow": 16,
            "body_top": 185, "body_bottom": 925, "card_wrap": 1500,
            "badge_font": 26, "badge_h": 50, "badge_gap": 32,
            "body": (44, 70), "body_photo": (38, 60),
            "cta": (54, 84), "cta_photo": (44, 68), "min_line": 46,
            "photo_min": 0, "photo_max": 0, "photo_gap": 40,
            "single_steps": ((84, 100, 40, 62), (76, 92, 37, 57), (68, 82, 34, 52), (60, 74, 31, 47)),
            "single_photo_min": 0,
        },
        "spotlight": {
            "label": (140, 60, 26), "circle": (960, 520, 580), "fade": (280, 1040),
            "center_y": 540, "title_wrap": 1100, "body": (36, 54), "body_gap": 34,
            "title_steps": ((104, 146), (94, 134), (84, 120), (74, 106)),
        },
    },
    "story": {
        # 9:16 for a Shorts/Reels cut. The page is centered vertically: about
        # 315px of paper above the header and below the logo, which also keeps
        # the header clear of YouTube's top bar (~100px).
        "size": (1080, 1920),
        "margin": 80,
        "paper": {
            "header_top": 315, "header_h": 56, "header_font": 26,
            "rule_y": 1560, "logo": 92, "page_font": 24,
            "title_top": 440, "title_bottom": 1005, "title_wrap": 920,
            "title_steps": ((84, 100), (76, 92), (68, 84), (60, 74)),
            "sub_font": 30, "sub_line": 44, "sub_gap": 22, "sub_wrap": 920,
            "photo_box": (80, 1065, 1000, 1495), "photo_top_min": 845, "shadow": 14,
            "body_top": 430, "body_bottom": 1505, "card_wrap": 920,
            "badge_font": 24, "badge_h": 48, "badge_gap": 34,
            "body": (46, 74), "body_photo": (38, 58),
            "cta": (50, 80), "cta_photo": (40, 62), "min_line": 46,
            "photo_min": 320, "photo_max": 620, "photo_gap": 44,
            "single_steps": ((76, 90, 36, 56), (68, 82, 34, 52), (60, 74, 31, 47), (54, 66, 28, 43)),
            "single_photo_min": 260,
        },
        # The headline stays clear of the Shorts UI at the bottom (~350px).
        "spotlight": {
            "label": (80, 150, 26), "circle": (540, 820, 640), "fade": (640, 1560),
            "center_y": 960, "title_wrap": 940, "body": (36, 54), "body_gap": 36,
            "title_steps": ((104, 150), (94, 136), (84, 122), (74, 108)),
        },
    },
}
DEFAULT_CANVAS = "portrait"

# The user's uploaded background photo, kept uncropped next to background_master.png.
BACKGROUND_SOURCE = "background_source.jpg"


def get_canvas(name: str) -> dict:
    return CANVASES.get(name or DEFAULT_CANVAS, CANVASES[DEFAULT_CANVAS])

# Color themes. The creative agent assigns a theme name at random (independent of
# the article topic); the renderer uses its key color for the labels, marker
# strokes and the block behind each photo.
THEMES = {
    "orange": {"key": (255, 102, 0, 255)},
    "blue":   {"key": (10, 132, 255, 255)},
    "green":  {"key": (34, 197, 94, 255)},
    "purple": {"key": (149, 97, 246, 255)},
    "pink":   {"key": (244, 63, 94, 255)},
    "teal":   {"key": (20, 184, 166, 255)},
    "yellow": {"key": (250, 204, 21, 255)},
    "red":    {"key": (255, 59, 48, 255)},
}
DEFAULT_THEME = "orange"

def get_theme(name: str) -> dict:
    """Resolves a theme name to its palette, falling back to the default theme."""
    if isinstance(name, str):
        key = name.strip().lower()
        if key in THEMES:
            return THEMES[key]
    return THEMES[DEFAULT_THEME]

# Brand fonts in the project root: NanumSquare Round ExtraBold for headlines and
# labels, Regular for body copy.
BRAND_FONT_BOLD = "NanumSquareRoundEB.ttf"
BRAND_FONT_REGULAR = "NanumSquareRoundR.ttf"


def get_system_font(size: int, bold: bool = False):
    """
    Attempts to load custom fonts placed in the folder first, then loads standard/system fonts.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(current_dir)

    # 0. The brand fonts: headlines in the heavy weight, copy in the regular one.
    brand_file = BRAND_FONT_BOLD if bold else BRAND_FONT_REGULAR
    for directory in (workspace_root, current_dir):
        path = os.path.join(directory, brand_file)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

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

# Glyphs that fall in emoji ranges but are intentional design elements to keep.
_EMOJI_KEEP = {"▶", "◀", "♡", "♥", "❤"}  # ▶ ◀ ♡ ♥ ❤

def remove_emojis(text: str) -> str:
    """
    Strips pictographic emoji from text (they render as monochrome/tofu with the
    bundled emoji font). Intentional design glyphs like the teaser arrow ▶ and
    the CTA heart ♡ are preserved, and leftover double spaces are collapsed.
    """
    if not text:
        return text
    out = []
    for ch in text:
        if ch in _EMOJI_KEEP or not is_emoji(ch):
            out.append(ch)
    cleaned = "".join(out)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)   # collapse gaps left by removed emoji
    cleaned = re.sub(r'[ \t]+(\n|$)', r'\1', cleaned)  # trim trailing spaces per line
    return cleaned


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

def format_korean_line_breaks(text: str) -> str:
    """
    Applies natural line-break rules for Korean readability.

    Only breaks at *sentence* boundaries (terminal punctuation followed by
    whitespace) so that each complete sentence stays on its own line instead of
    being chopped in the middle of a phrase. Width-based line wrapping within a
    sentence is handled separately by wrap_text(), which balances line lengths.

    This intentionally does NOT break after particles/connectives (을/를/와/과/,)
    because ending a line on a dangling particle reads unnaturally.
    """
    if not text:
        return text
    # Break after terminal punctuation (. ! ? …) followed by whitespace.
    # A trailing space is required so decimals/ratios like "3.5" stay intact,
    # and a digit before the mark is excluded so ordered-list markers like
    # "1." / "2." (and numbers ending a clause) are not split off.
    text = re.sub(r'(?<!\d)([.!?…]+)[ \t]+', r'\1\n', text)
    # Trim stray spaces around every newline and collapse excessive blank lines.
    text = re.sub(r'[ \t]*\n[ \t]*', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

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

def strip_highlight_markers(text: str) -> tuple:
    """
    Removes '**' emphasis markers from a line and reports whether any were
    present. The creative agent wraps an important sentence in **...** so the
    renderer can paint it in the theme's key color.
    """
    has_highlight = "**" in text
    return text.replace("**", ""), has_highlight


# How many typed lines the cover sub-copy accepts. The dashboard offers a
# three-line box under the title field, and the renderer honours the same cap.
COVER_SUB_MAX_LINES = 3

# The one-card post carries its whole story in the body block under the
# headline, so it gets a roomier cap: three or four lines normally, up to five
# when the article holds more facts the reader must not miss.
SINGLE_BODY_MAX_LINES = 5


def cover_sub_lines(text: Optional[str], max_lines: int = COVER_SUB_MAX_LINES) -> list:
    """
    Cleans typed sub-copy into at most `max_lines` lines.

    Blank lines are dropped so a stray newline from the dashboard textarea does
    not eat one of the slots. Each surviving line keeps its own '**...**'
    markers, which the renderer paints in the theme's key color.

    The cover keeps the default cap; the one-card body passes the roomier
    SINGLE_BODY_MAX_LINES.
    """
    if not text:
        return []
    lines = [line.strip() for line in remove_emojis(str(text)).split("\n")]
    return [line for line in lines if line][:max_lines]


def _text_width(font, text: str) -> int:
    """Returns the pixel width of a string for the given font (with a fallback)."""
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    # Fallback for the old default bitmap font
    return len(text) * 6


def _break_long_word(word: str, font, max_width: int) -> list:
    """
    Splits a single token that is wider than max_width into character-level
    chunks so it never overflows the card (handles long URLs, hashtags, or
    space-less Korean runs).
    """
    chunks = []
    current = ""
    for ch in word:
        if current and _text_width(font, current + ch) > max_width:
            chunks.append(current)
            current = ch
        else:
            current += ch
    if current:
        chunks.append(current)
    return chunks


def _wrap_balanced(words: list, font, max_width: int) -> list:
    """
    Wraps words using minimum-raggedness (balanced) line breaking so lines are
    filled evenly instead of a long line followed by a lonely orphan word. The
    final line carries no penalty, so it is allowed to be short.
    """
    n = len(words)
    if n == 0:
        return []

    space_w = _text_width(font, " ")
    word_w = [_text_width(font, w) for w in words]

    INF = float("inf")
    cost = [INF] * (n + 1)
    nxt = [n] * (n + 1)
    cost[n] = 0

    for i in range(n - 1, -1, -1):
        line_w = 0
        for j in range(i, n):
            line_w += word_w[j]
            if j > i:
                line_w += space_w
            # Stop extending once a multi-word line exceeds the width.
            if line_w > max_width and j > i:
                break
            is_last = (j == n - 1)
            slack = max_width - line_w
            penalty = 0 if is_last else slack * slack
            total = penalty + cost[j + 1]
            if total < cost[i]:
                cost[i] = total
                nxt[i] = j + 1
        # Guarantee forward progress even if a single word overflows.
        if cost[i] == INF:
            cost[i] = cost[i + 1]
            nxt[i] = i + 1

    lines = []
    i = 0
    while i < n:
        j = nxt[i]
        lines.append(" ".join(words[i:j]))
        i = j
    return lines


def wrap_text(text: str, font, max_width: int) -> list:
    """
    Wraps text to fit within a maximum width, respecting existing newlines and
    using balanced (minimum-raggedness) line breaking for natural-looking lines.
    Overlong single tokens are split at the character level as a safety net.
    """
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue

        # Split into words, pre-splitting any token wider than the card.
        words = []
        for word in paragraph.split(" "):
            if not word:
                continue
            if _text_width(font, word) > max_width:
                words.extend(_break_long_word(word, font, max_width))
            else:
                words.append(word)

        lines.extend(_wrap_balanced(words, font, max_width))
    return lines

PHOTO_CAMERAS = (
    "shot on a full-frame DSLR with a 50mm prime lens, shallow depth of field",
    "shot on a 35mm lens at eye level, moderate depth of field",
    "shot on 35mm film with visible natural grain",
    "shot on a smartphone camera, casual handheld framing",
    "shot on a medium-format camera with an 80mm lens",
    "shot from a slightly high angle with a 28mm lens",
)
PHOTO_LIGHTS = (
    "soft natural window light",
    "warm golden-hour sunlight",
    "even overcast daylight",
    "late-evening ambient light with practical lamps",
    "crisp midday light with defined shadows",
    "cool early-morning light",
)

def generate_dalle_background(prompt_text: str) -> Image.Image:
    """
    Calls OpenAI Image API to generate a background image based on the provided prompt_text.
    Returns a PIL Image object, or None if generation fails.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or "your_openai_api_key" in openai_key:
        print("Warning: OPENAI_API_KEY is not configured for AI background generation. Drawing without a photo.")
        return None

    try:
        print(f"Generating AI background via OpenAI for: '{prompt_text[:50]}...'")
        client = OpenAI(api_key=openai_key)
        
        # Optimize prompt to generate a highly intuitive, direct visual concept matching the title keywords.
        # Style is photorealistic (objects / scenery / texture), never illustration: the cover reads as a
        # real editorial photograph. Faces stay banned because AI faces look uncanny at card-news scale.
        is_english = prompt_text and any(c.isalpha() for c in prompt_text) and not any(ord(c) > 127 for c in prompt_text)

        # Shared style rules so both language branches produce the same photographic look.
        # The camera and light vary per image so the backgrounds don't all share
        # one recognizable "AI stock photo" look.
        PHOTO_STYLE = (
            "Photorealistic editorial photograph, "
            + random.choice(PHOTO_CAMERAS) + ", "
            + random.choice(PHOTO_LIGHTS) + ", "
            "realistic materials and surface texture, true-to-life colors, "
            "sharp focus on the main subject. "
        )
        # The cover title starts a little above the middle of the card, over a dark gradient,
        # so the subject belongs in the top part and everything below it must stay quiet.
        COMPOSITION = (
            "Place the subject in the top third of the frame; keep the middle and bottom of the frame simple, "
            "uncluttered and darker (plain surface, shadow, or soft bokeh) so overlaid text stays readable. "
        )
        NEGATIVES = (
            "Strictly NO text, NO letters, NO words, NO numbers, NO label overlays, NO signatures, NO watermarks, "
            "NO logos, NO human faces, NO people, NO illustration, NO cartoon, NO 3D render, NO CGI, "
            "NO digital painting, NO vector art, NO flat design. "
        )

        if is_english:
            prompt = (
                f"{prompt_text}. "
                + PHOTO_STYLE
                + COMPOSITION
                + NEGATIVES
                + "A premium, magazine-quality photo used as an Instagram card news background."
            )
        else:
            prompt = (
                f"A real photograph that clearly and directly represents the key subject of: '{prompt_text}'. "
                "Show it through concrete objects, scenery, architecture, or close-up texture that a "
                "photographer could actually capture -- no symbolic drawings or icons. "
                + PHOTO_STYLE
                + COMPOSITION
                + NEGATIVES
                + "A premium, magazine-quality photo used as an Instagram card news background."
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
        print(f"Error generating AI background via OpenAI: {e}. Drawing without a photo.")
        return None

def resize_to_cover(image: Image.Image, target_width: int, target_height: int,
                    anchor_y: float = 0.5) -> Image.Image:
    """
    Resizes and crops a PIL Image to cover the target dimensions (aspect ratio fill).
    `anchor_y` picks which part of a too-tall image survives the crop
    (0 = top, 0.5 = center, 1 = bottom).
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

    left = (new_w - target_width) // 2
    top = int((new_h - target_height) * anchor_y)
    right = left + target_width
    bottom = top + target_height

    return resized_img.crop((left, top, right, bottom))

def save_uploaded_photo(file_bytes: bytes, output_dir: str, filename: str) -> str:
    """
    Stores a user-uploaded photo for embedding at the top of a card. The photo is
    kept uncropped (only downscaled if huge) because draw_card_layout center-crops
    it to whatever band height that card's copy leaves free. Returns the path.
    """
    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(BytesIO(file_bytes)).convert("RGB")

    max_w = WIDTH * 2  # plenty of detail for a 920px-wide band, without bloating the post folder
    if img.width > max_w:
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.ANTIALIAS
        img = img.resize((max_w, int(img.height * (max_w / img.width))), resample_filter)

    filepath = os.path.join(output_dir, filename)
    img.save(filepath, "JPEG", quality=95)
    print(f"Saved uploaded photo: {filepath}")
    return filepath

def save_background_master(file_bytes: bytes, output_dir: str) -> str:
    """
    Stores a user-supplied photo as this post's photo, used instead of an
    AI-generated one, so attaching a photo also skips the paid image API call.
    The original is kept uncropped (each photo box crops it to its own shape,
    so a landscape photo works as well as a portrait one); the 4:5 master copy
    is the fallback for older code paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(BytesIO(file_bytes)).convert("RGB")
    cover = resize_to_cover(img, WIDTH, HEIGHT)

    filepath = os.path.join(output_dir, "background_master.png")
    cover.save(filepath, "PNG")
    img.save(os.path.join(output_dir, BACKGROUND_SOURCE), "JPEG", quality=95)
    print(f"Saved user-supplied background master: {filepath}")
    return filepath

def resolve_user_photo(slide: dict, photo_dir: str) -> Optional[str]:
    """Path of the photo attached to this slide, or None when there isn't one."""
    name = (slide.get("user_photo") or "").strip()
    if not name or not photo_dir:
        return None
    path = os.path.join(photo_dir, os.path.basename(name))
    return path if os.path.exists(path) else None


# --- Newspaper layout ---
# Every card is a newspaper page: off-white paper, a ruled "TODAY NEWS" header,
# dark ink copy with marker strokes in the theme color, photos over a theme-color block,
# and a bottom rule carrying the brand logo.
PAPER_COLOR = (240, 238, 233)
PAPER_INK = (26, 26, 28)
PAPER_BODY = (58, 58, 64)
PAPER_HEADER_LEFT = "TODAY NEWS"
PAPER_HEADER_RIGHT = "ALWAYS GOOD"
PAPER_TITLE_MAX_LINES = 4


def _mix(color_a: tuple, color_b: tuple, amount: float) -> tuple:
    """`amount` of color_a over color_b (RGB)."""
    return tuple(int(a * amount + b * (1 - amount)) for a, b in zip(color_a[:3], color_b[:3]))


def make_paper_background(width: int, height: int, seed: int) -> Image.Image:
    """
    Off-white newsprint: faint, out-of-focus columns of "text" showing through
    from the other side of the page, plus a little grain.
    """
    rng = random.Random(seed)
    base = Image.new("RGB", (width, height), PAPER_COLOR)

    ghost = Image.new("L", (width, height), 0)
    g_draw = ImageDraw.Draw(ghost)
    cols = 4 if width > height else 3
    gutter = 34
    col_w = (width - 80 - gutter * (cols - 1)) / cols
    for c in range(cols):
        cx0 = int(40 + c * (col_w + gutter))
        cx1 = int(cx0 + col_w)
        y = rng.randint(20, 40)
        while y < height - 20:
            if rng.random() < 0.08:  # paragraph break
                y += 26
                continue
            x = cx0
            line_end = cx1 if rng.random() > 0.12 else rng.randint(cx0 + 40, cx1)
            while x < line_end:
                word = rng.randint(18, 80)
                g_draw.rectangle([x, y, min(x + word, line_end), y + 10], fill=255)
                x += word + 11
            y += 25
    ghost = ghost.filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.07))
    base = Image.composite(Image.new("RGB", (width, height), (120, 118, 114)), base, ghost)

    grain = Image.effect_noise((width, height), 22).convert("RGB")
    return Image.blend(base, grain, 0.035)


def draw_brush_highlight(image: Image.Image, x0: int, y0: int, x1: int, y1: int,
                         color: tuple, rng: random.Random) -> None:
    """A rough marker stroke behind a line of copy: jagged edges, streaky ends."""
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    l_draw = ImageDraw.Draw(layer)
    fill = color + (255,)

    top = [(x, y0 + rng.randint(-3, 3)) for x in range(x0, x1, 14)] + [(x1, y0 + rng.randint(-3, 3))]
    bottom = [(x, y1 + rng.randint(-3, 3)) for x in range(x1, x0, -14)] + [(x0, y1 + rng.randint(-3, 3))]
    l_draw.polygon(top + bottom, fill=fill)

    # Dry-brush streaks trailing off both ends.
    band = y1 - y0
    for _ in range(9):
        sy = y0 + rng.randint(0, band)
        l_draw.rectangle([x1, sy, x1 + rng.randint(8, 55), sy + rng.randint(2, 6)], fill=fill)
        sy = y0 + rng.randint(0, band)
        l_draw.rectangle([x0 - rng.randint(4, 26), sy, x0, sy + rng.randint(2, 6)], fill=fill)

    layer = layer.filter(ImageFilter.GaussianBlur(0.8))
    image.alpha_composite(layer)


_LOGO_CACHE = {}


def ink_logo(size: int) -> Optional[Image.Image]:
    """The brand logo (stored white-on-transparent) recolored to ink for paper."""
    if size in _LOGO_CACHE:
        return _LOGO_CACHE[size]
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(workspace_root, "img", "alwaysgood_logo.png")
    try:
        alpha = Image.open(logo_path).convert("RGBA").split()[3]
    except Exception as e:
        print(f"Failed to load the logo: {e}")
        return None
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.ANTIALIAS
    logo = Image.new("RGBA", alpha.size, PAPER_INK + (255,))
    logo.putalpha(alpha)
    logo = logo.resize((size, size), resample_filter)
    _LOGO_CACHE[size] = logo
    return logo


def _highlight_marked(text: str) -> tuple:
    """
    Strips '**' markers and returns (clean text, set of character indices that
    were inside markers).
    """
    clean, marked, inside = [], set(), False
    i = 0
    while i < len(text):
        if text.startswith("**", i):
            inside = not inside
            i += 2
            continue
        if inside:
            marked.add(len(clean))
        clean.append(text[i])
        i += 1
    return "".join(clean), marked


def _ink_band(font, line_height: int) -> tuple:
    """Top/bottom of the glyphs inside a line box, padded for a marker stroke."""
    if hasattr(font, "getbbox"):
        _, top, _, bottom = font.getbbox("가Ag")
    else:
        top, bottom = 0, line_height
    pad = int(line_height * 0.09)
    return top - pad, bottom + pad


def _badge_text_color(key_color: tuple) -> tuple:
    """White on dark theme colors, ink on light ones (yellow)."""
    r, g, b = key_color[:3]
    return PAPER_INK + (255,) if 0.299 * r + 0.587 * g + 0.114 * b > 170 else (255, 255, 255, 255)


class PaperPage:
    """One newspaper card being drawn: the frame plus helpers for its parts."""

    def __init__(self, canvas: str, theme: str, seed: int):
        spec = get_canvas(canvas)
        self.W, self.H = spec["size"]
        self.margin = spec["margin"]
        self.p = spec["paper"]
        self.key = get_theme(theme)["key"]
        self.ink = PAPER_INK + (255,)
        self.highlight = _mix(self.key, PAPER_COLOR, 0.78)
        self.rng = random.Random(seed)
        self.image = make_paper_background(self.W, self.H, seed).convert("RGBA")
        # Wide canvases put the photo in a column beside the copy.
        self.side_photo = self.p["photo_box"][0] >= self.margin + self.p["title_wrap"]

    @property
    def draw(self) -> ImageDraw.ImageDraw:
        return ImageDraw.Draw(self.image)

    def frame(self, page_text: Optional[str] = None) -> None:
        """Header rules and labels, bottom rule, logo, optional page number."""
        draw, p, m = self.draw, self.p, self.margin
        x1 = self.W - m
        h_top, h_bot = p["header_top"], p["header_top"] + p["header_h"]
        draw.rectangle([m, h_top, x1, h_top + 2], fill=self.ink)
        draw.rectangle([m, h_bot, x1, h_bot + 2], fill=self.ink)
        header_font = get_system_font(p["header_font"], bold=True)
        label_y = h_top + (p["header_h"] - p["header_font"]) // 2
        draw.text((m, label_y), PAPER_HEADER_LEFT, fill=self.ink, font=header_font)
        draw.text((x1 - _text_width(header_font, PAPER_HEADER_RIGHT), label_y),
                  PAPER_HEADER_RIGHT, fill=self.ink, font=header_font)

        rule_y = p["rule_y"]
        draw.rectangle([m, rule_y, x1, rule_y + 2], fill=self.ink)
        if page_text:
            page_font = get_system_font(p["page_font"])
            draw.text((m, rule_y + 20), page_text, fill=(110, 110, 116, 255), font=page_font)

        # The logo sits on the right end of the rule, on a paper disc that
        # breaks the line behind it.
        size = p["logo"]
        cx, cy = x1 - size // 2 + 8, rule_y + 1
        r = size // 2 + 6
        # Paper tone sampled just above the rule, so the disc blends into the grain.
        disc = self.image.getpixel((cx - r - 4, max(0, cy - r - 4)))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=disc)
        logo = ink_logo(size)
        if logo is not None:
            self.image.alpha_composite(logo, (cx - size // 2, cy - size // 2))

    def badge(self, text: str, x: int, y: int) -> None:
        p = self.p
        font = get_system_font(p["badge_font"], bold=True)
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            tw, th = len(text) * 11, p["badge_font"]
        bh = p["badge_h"]
        self.draw.rectangle([x, y, x + tw + 44, y + bh], fill=self.key)
        self.draw.text((x + 22, y + (bh - th) // 2 - 2), text, fill=_badge_text_color(self.key), font=font)

    def lines(self, rows: list, x: int, y: int, line_height: int) -> int:
        """
        Draws rows of (text, font, color, (start, end) | None); the span gets a
        marker stroke behind it. Returns the y below the last row.
        """
        for text, font, color, span in rows:
            if span:
                band_top, band_bottom = _ink_band(font, line_height)
                sx0 = x + (_text_width(font, text[:span[0]]) if span[0] else 0)
                sx1 = x + _text_width(font, text[:span[1]])
                draw_brush_highlight(self.image, sx0 - 14, y + band_top, sx1 + 14, y + band_bottom,
                                     self.highlight, self.rng)
            draw_text_safe(self.draw, (x, y), text, fill=color, font=font)
            y += line_height
        return y

    def photo(self, photo: Image.Image, box: tuple, anchor: float = 0.5, whole: bool = False,
              align: tuple = (0.0, 0.0)) -> tuple:
        """
        The photo, in its original colors, over an offset block of the theme color.
        By default it fills `box`, cropped around `anchor`. With `whole` the
        entire photo is shown: it is scaled to fit inside `box` and the frame
        shrinks to the photo's own shape, placed by `align` (x, y: 0 = left/top,
        1 = right/bottom). Returns the frame actually drawn.
        """
        bx0, by0, bx1, by1 = box
        if whole:
            scale = min((bx1 - bx0) / photo.width, (by1 - by0) / photo.height)
            w, h = max(1, int(photo.width * scale)), max(1, int(photo.height * scale))
            bx0 += int(((bx1 - bx0) - w) * align[0])
            by0 += int(((by1 - by0) - h) * align[1])
            bx1, by1 = bx0 + w, by0 + h
            try:
                resample_filter = Image.Resampling.LANCZOS
            except AttributeError:
                resample_filter = Image.ANTIALIAS
            fitted = photo.resize((w, h), resample_filter)
        else:
            fitted = resize_to_cover(photo, bx1 - bx0, by1 - by0, anchor)
        off = self.p["shadow"]
        self.draw.rectangle([bx0 + off, by0 + off, bx1 + off, by1 + off], fill=self.key)
        self.image.paste(fitted.convert("RGB"), (bx0, by0))
        return bx0, by0, bx1, by1


def _headline_rows(title: str, steps, wrap: int, fits, default_last: bool) -> tuple:
    """
    Wraps a headline at the largest step that keeps it to four lines and makes
    `fits(line_count, step)` true; past the smallest step the fourth line ends
    in an ellipsis. '**' words get a marker stroke; without any, the last line
    does when `default_last` is set. Returns (rows, step).
    """
    title, marked = _highlight_marked(re.sub(r"\s+", " ", title))
    for step in steps:
        font = get_system_font(step[0], bold=True)
        lines = wrap_text(title, font, wrap)
        if len(lines) <= PAPER_TITLE_MAX_LINES and fits(len(lines), step):
            break
    if len(lines) > PAPER_TITLE_MAX_LINES:
        lines = lines[:PAPER_TITLE_MAX_LINES]
        last = lines[-1]
        while last and _text_width(font, last + "…") > wrap:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"

    rows, cursor = [], 0
    for idx, line in enumerate(lines):
        span = None
        pos = title.find(line.rstrip("…"), cursor)
        if marked and pos >= 0:
            hits = [i for i in range(len(line)) if pos + i in marked and line[i] != " "]
            if hits:
                span = (hits[0], hits[-1] + 1)
            cursor = pos + len(line)
        elif not marked and default_last and idx == len(lines) - 1:
            span = (0, len(line))
        rows.append((line, font, PAPER_INK + (255,), span))
    return rows, step


def _copy_rows(logical_lines: list, size: int, wrap: int, header_bold: bool = False) -> list:
    """
    Body copy rows. A line wrapped in '**' is the one to remember: bold with a
    marker stroke. Numbered lead-ins ("1.", "첫째") are bold ink when
    `header_bold` is set; everything else is regular body gray.
    """
    regular = get_system_font(size)
    bold = get_system_font(size, bold=True)
    rows = []
    for logical in logical_lines:
        if not logical.strip():
            continue
        clean, has_highlight = strip_highlight_markers(logical)
        clean = clean.strip()
        is_header = header_bold and bool(
            re.match(r'^\d+[\.\)]', clean)
            or re.match(r'^\d+단계', clean)
            or clean.startswith(("첫째", "둘째", "셋째", "넷째", "다섯째",
                                 "여섯째", "일곱째", "여덟째", "마지막"))
        )
        font = bold if (has_highlight or is_header) else regular
        color = PAPER_INK + (255,) if (has_highlight or is_header) else PAPER_BODY + (255,)
        for piece in wrap_text(clean, font, wrap):
            rows.append((piece, font, color, (0, len(piece)) if has_highlight else None))
    return rows


def _title_seed(text: str) -> int:
    return sum(ord(ch) for ch in (text or "")) or 1


def draw_paper_cover(slide: dict, hooking_title: str, photo: Optional[Image.Image],
                     article_title: str = None, theme: str = "orange", canvas: str = DEFAULT_CANVAS,
                     photo_anchor: Optional[float] = 0.5) -> Image.Image:
    """
    The carousel cover: a left-aligned headline of at most four lines with one
    marker-highlighted stretch, optional sub-copy, and the post's photo in a box
    that grows up to meet the headline.
    """
    title = remove_emojis((slide.get("main_text") or "").strip())
    if not title:
        title = remove_emojis((article_title or hooking_title or "").strip())
    page = PaperPage(canvas, theme, _title_seed(title))
    p, m = page.p, page.margin
    page.frame()

    sub_rows = []
    sub_font = get_system_font(p["sub_font"])
    sub_font_bold = get_system_font(p["sub_font"], bold=True)
    for logical in cover_sub_lines(slide.get("sub_text")):
        clean, has_highlight = strip_highlight_markers(logical)
        font = sub_font_bold if has_highlight else sub_font
        for piece in wrap_text(clean, font, p["sub_wrap"]):
            sub_rows.append((piece, font, (70, 70, 74, 255), None))

    def sub_height(count: int) -> int:
        return p["sub_gap"] + count * p["sub_line"] if count else 0

    zone = p["title_bottom"] - p["title_top"]
    rows, (_, line_height) = _headline_rows(
        title, p["title_steps"], p["title_wrap"],
        lambda n, step: n * step[1] + sub_height(len(sub_rows)) <= zone, default_last=True)
    while sub_rows and len(rows) * line_height + sub_height(len(sub_rows)) > zone:
        sub_rows.pop()

    y = page.lines(rows, m, p["title_top"], line_height)
    if sub_rows:
        y = page.lines(sub_rows, m, y + p["sub_gap"], p["sub_line"])

    bx0, by0, bx1, by1 = p["photo_box"]
    whole = photo_anchor is None
    if not page.side_photo:
        # A cropped photo fills the box, which grows up toward the headline. A
        # whole photo gets all the room under the headline and sits centered.
        by0 = y + 60 if whole else min(by0, max(p["photo_top_min"], y + 60))
    if photo is not None:
        page.photo(photo, (bx0, by0, bx1, by1), photo_anchor or 0.5, whole=whole,
                   align=(0.5, 0.5) if page.side_photo else (0.0, 0.5))
    else:
        page.draw.rectangle([bx0, by0, bx1, by1], fill=_mix(page.key, PAPER_COLOR, 0.55))
    return page.image


def draw_paper_card(slide: dict, total_pages: int, theme: str = "orange", canvas: str = DEFAULT_CANVAS,
                    photo_path: Optional[str] = None) -> Image.Image:
    """
    Cards 2..N: a "KEY POINT" (or "THANK YOU") label, then the copy in ink. A
    photo the user put on this card sits in a box under the label (beside the
    copy on wide canvases) and the copy shrinks to make room.
    """
    slide_type = slide.get("type", "content")
    page_num = slide.get("page", 1)
    main_text = remove_emojis(slide.get("main_text", "") or "")
    page = PaperPage(canvas, theme, _title_seed(main_text) + page_num)
    p, m, W = page.p, page.margin, page.W
    page.frame(f"{page_num} / {total_pages}" if total_pages > 1 else None)

    has_photo = photo_path is not None
    side = has_photo and page.side_photo
    wrap = p["title_wrap"] if side else p["card_wrap"]

    if slide_type == "cta":
        badge_text = "THANK YOU"
        size, line_height = p["cta_photo"] if has_photo else p["cta"]
        font = get_system_font(size, bold=True)
        clean, _ = strip_highlight_markers(main_text)
        rows = [(line, font, page.ink, None) for line in wrap_text(clean, font, wrap)]
    else:
        badge_text = f"KEY POINT {page_num - 1:02d}"
        size, line_height = p["body_photo"] if has_photo else p["body"]
        rows = _copy_rows(format_korean_line_breaks(main_text).split("\n"), size, wrap, header_bold=True)

    y = p["body_top"]
    bottom = p["body_bottom"]
    # The label rides directly on top of the copy, so it counts as part of it.
    label_h = p["badge_h"] + p["badge_gap"]

    if has_photo:
        photo = Image.open(photo_path).convert("RGB")
        # The user's own photo is always shown whole, never cropped.
        if side:
            page.photo(photo, p["photo_box"], whole=True, align=(0.5, 0.5))
        else:
            off = p["shadow"]
            text_h = label_h + len(rows) * line_height
            photo_h = max(p["photo_min"], min(bottom - y - off - p["photo_gap"] - text_h, p["photo_max"]))
            frame = page.photo(photo, (m, y, W - m, y + photo_h), whole=True)
            y = frame[3] + off + p["photo_gap"]

    # Squeeze the leading when the copy is long; center label + copy when there
    # is room (but keep them right under the photo when there is one).
    area = bottom - y - label_h
    if rows and len(rows) * line_height > area:
        line_height = max(p["min_line"], area // len(rows))
    if not has_photo or side:
        y += max(0, (area - len(rows) * line_height) // 2)
    page.badge(badge_text, m, y)
    page.lines(rows, m, y + label_h, line_height)
    return page.image


def draw_paper_single(slide: dict, hooking_title: str, photo: Optional[Image.Image],
                      article_title: str = None, theme: str = "orange", canvas: str = DEFAULT_CANVAS,
                      photo_anchor: Optional[float] = 0.5) -> Image.Image:
    """
    The one-card post: "오늘의 한 장" label, a headline of up to four lines, the
    photo box, and the body block (up to five lines, one highlighted) at the
    bottom. Wide canvases put the photo in a column beside the copy.
    """
    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    page = PaperPage(canvas, theme, _title_seed(headline))
    p, m = page.p, page.margin
    page.frame()

    body_text = remove_emojis((slide.get("sub_text") or "").strip())
    body_logical = [line for line in body_text.split("\n") if line.strip()][:SINGLE_BODY_MAX_LINES]

    y = p["body_top"]
    page.badge("오늘의 한 장", m, y)
    y += p["badge_h"] + p["badge_gap"]
    bottom = p["body_bottom"]
    title_gap, photo_gap = 36, p["photo_gap"]
    in_column = photo is not None and not page.side_photo
    photo_room = p["single_photo_min"] + p["shadow"] + photo_gap if in_column else 0
    wrap = p["title_wrap"] if page.side_photo else p["card_wrap"]

    def fits(count: int, step) -> bool:
        body_rows = _copy_rows(body_logical, step[2], wrap)
        return y + count * step[1] + title_gap + photo_room + len(body_rows) * step[3] <= bottom

    rows, step = _headline_rows(headline, p["single_steps"], wrap, fits, default_last=False)
    body_rows = _copy_rows(body_logical, step[2], wrap)
    y = page.lines(rows, m, y, step[1]) + title_gap

    if in_column:
        # Body anchored to the bottom; the photo takes everything in between.
        body_y = max(y + photo_room, bottom - len(body_rows) * step[3])
        page.photo(photo, (m, y, page.W - m, body_y - photo_gap - p["shadow"]), photo_anchor or 0.5,
                   whole=photo_anchor is None, align=(0.0, 0.5))
        page.lines(body_rows, m, body_y, step[3])
    else:
        if photo is not None:
            page.photo(photo, p["photo_box"], photo_anchor or 0.5,
                       whole=photo_anchor is None, align=(0.5, 0.5))
        page.lines(body_rows, m, y, step[3])
    return page.image


# --- Card 2: spotlight layout ---
# A one-card post on black: the photo inside a large circle (like a spotlight
# or lens), a black fade over the bottom, a small "always good" label top-left
# and the headline in white at the bottom. Only the headline is drawn.
SPOTLIGHT_BLACK = (8, 8, 10)
SPOTLIGHT_LABEL = "always good"
SPOTLIGHT_TITLE_MAX_LINES = 3
SPOTLIGHT_BODY_MAX_LINES = 2
SINGLE_DESIGNS = ("card1", "card2")


def _radial_mask(diameter: int, curve) -> Image.Image:
    """L mask of a disc whose value at radius fraction t (0 center, 1 edge) is curve(t)."""
    size = 512
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    half = size // 2
    for step in range(half, 0, -1):
        m_draw.ellipse([half - step, half - step, half + step, half + step],
                       fill=int(curve(step / half)))
    try:
        resample_filter = Image.Resampling.BICUBIC
    except AttributeError:
        resample_filter = Image.BICUBIC
    return mask.resize((diameter, diameter), resample_filter)


def draw_spotlight_single(slide: dict, hooking_title: str, photo: Optional[Image.Image],
                          article_title: str = None, theme: str = "orange",
                          canvas: str = DEFAULT_CANVAS,
                          photo_anchor: Optional[float] = 0.5) -> Image.Image:
    """Card 2: the photo in a circle on black, headline only at the bottom."""
    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    spec = get_canvas(canvas)
    W, H = spec["size"]
    s = spec["spotlight"]
    key = get_theme(theme)["key"][:3]
    image = Image.new("RGBA", (W, H), SPOTLIGHT_BLACK + (255,))

    cx, cy, r = s["circle"]
    d = r * 2
    disc = _radial_mask(d, lambda t: 255 if t < 0.995 else 0).filter(ImageFilter.GaussianBlur(2))
    if photo is not None:
        # The circle is filled edge to edge; an uncropped upload is still cropped
        # here, kept toward the top where faces and subjects usually are.
        fitted = resize_to_cover(photo, d, d, 0.3 if photo_anchor is None else photo_anchor)
        image.paste(fitted.convert("RGB"), (cx - r, cy - r), disc)
        # Darken toward the rim, like a lens vignette.
        shade = _radial_mask(d, lambda t: 0 if t < 0.62 else 175 * ((t - 0.62) / 0.38) ** 2)
        image.paste(Image.new("RGB", (d, d), SPOTLIGHT_BLACK), (cx - r, cy - r), shade)
    else:
        image.paste(Image.new("RGB", (d, d), _mix(key, SPOTLIGHT_BLACK, 0.35)), (cx - r, cy - r), disc)

    # A soft glow of the theme color along the rim.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - r, cy - r, cx + r, cy + r], outline=key + (150,), width=10)
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))

    # Black fade over the bottom, fully black by fade_end.
    fade_top, fade_end = s["fade"]
    column = Image.new("L", (1, H), 0)
    for y in range(fade_top, H):
        t = min(1.0, (y - fade_top) / max(1, fade_end - fade_top))
        column.putpixel((0, y), int(255 * t ** 1.4))
    image.paste(Image.new("RGB", (W, H), SPOTLIGHT_BLACK), (0, 0), column.resize((W, H)))

    draw = ImageDraw.Draw(image)
    lx, ly, lsize = s["label"]
    draw.text((lx, ly), SPOTLIGHT_LABEL, fill=(255, 255, 255, 220), font=get_system_font(lsize))

    # Headline: the biggest step that fits in two lines, else in three. It and
    # the small body lines under it are centered and anchored to the bottom.
    title, _ = _highlight_marked(re.sub(r"\s+", " ", headline))
    fitted_lines = None
    for max_lines in (2, SPOTLIGHT_TITLE_MAX_LINES):
        for size, line_height in s["title_steps"]:
            font = get_system_font(size, bold=True)
            lines = wrap_text(title, font, s["title_wrap"])
            if len(lines) <= max_lines:
                fitted_lines = lines
                break
        if fitted_lines:
            break
    lines = _cap_rows(lines, SPOTLIGHT_TITLE_MAX_LINES, font, s["title_wrap"])

    # Body: up to two short lines in the regular weight; a '**' line is bold white.
    body_size, body_line = s["body"]
    body_rows = []
    for logical in cover_sub_lines(remove_emojis(slide.get("sub_text") or ""), SPOTLIGHT_BODY_MAX_LINES):
        clean, has_highlight = strip_highlight_markers(logical)
        body_font = get_system_font(body_size, bold=has_highlight)
        color = (255, 255, 255, 255) if has_highlight else (215, 215, 220, 255)
        body_rows += [(piece, body_font, color) for piece in wrap_text(clean.strip(), body_font, s["title_wrap"])]
    if len(body_rows) > SPOTLIGHT_BODY_MAX_LINES:
        body_rows = body_rows[:SPOTLIGHT_BODY_MAX_LINES]
        text, body_font, color = body_rows[-1]
        body_rows[-1] = (_ellipsize(text, body_font, s["title_wrap"]), body_font, color)

    # Lay out the block centered on the canvas, then draw it over a soft shadow
    # so it stays readable on a bright part of the photo.
    title_h = (len(lines) - 1) * line_height + size
    body_h = (len(body_rows) - 1) * body_line + body_size + s["body_gap"] if body_rows else 0
    y = s["center_y"] - (title_h + body_h) // 2
    placed = []
    for line in lines:
        placed.append(((W - _text_width(font, line)) // 2, y, line, font, (255, 255, 255, 255)))
        y += line_height
    y += size - line_height + s["body_gap"]
    for text, body_font, color in body_rows:
        placed.append(((W - _text_width(body_font, text)) // 2, y, text, body_font, color))
        y += body_line

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    for x, ty, text, text_font, _ in placed:
        s_draw.text((x, ty + 4), text, fill=(0, 0, 0, 200), font=text_font)
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(image)
    for x, ty, text, text_font, color in placed:
        draw_text_safe(draw, (x, ty), text, fill=color, font=text_font)
    return image


def _cap_rows(lines: list, max_lines: int, font, wrap: int) -> list:
    """Keeps at most `max_lines` rows, ending the last kept one in an ellipsis."""
    if len(lines) <= max_lines:
        return lines
    return lines[:max_lines - 1] + [_ellipsize(lines[max_lines - 1], font, wrap)]


def _ellipsize(text: str, font, wrap: int) -> str:
    """`text` cut short enough to end in '…' within `wrap` pixels."""
    while text and _text_width(font, text + "…") > wrap:
        text = text[:-1]
    return text.rstrip() + "…"


def draw_card_layout(slide: dict, total_pages: int, hooking_title: str, article_title: str = None,
                     theme: str = "orange", photo_dir: str = None, canvas: str = DEFAULT_CANVAS,
                     post_photo: Optional[Image.Image] = None,
                     photo_anchor: Optional[float] = 0.5) -> Image.Image:
    """
    Draws one card as a newspaper page. `canvas` picks the shape ("portrait"
    4:5 Instagram, "landscape" 16:9 YouTube, "story" 9:16 Shorts). `post_photo`
    is the post's photo (the user's upload or the AI background) shown on the
    cover and the one-card post, cropped around `photo_anchor` (0 = top), or
    shown whole when it is None (the user's upload). A photo the user put on
    a content card is looked up in `photo_dir` and is always shown whole.
    """
    slide_type = slide.get("type", "content")
    if slide_type == "cover":
        return draw_paper_cover(slide, hooking_title, post_photo, article_title=article_title,
                                theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    if slide_type == "single" and slide.get("design") == "card2":
        return draw_spotlight_single(slide, hooking_title, post_photo, article_title=article_title,
                                     theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    if slide_type == "single":
        return draw_paper_single(slide, hooking_title, post_photo, article_title=article_title,
                                 theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    return draw_paper_card(slide, total_pages, theme=theme, canvas=canvas,
                           photo_path=resolve_user_photo(slide, photo_dir))



def generate_carousel_images(plan: dict, output_dir: str, reuse_background: bool = False, article_title: str = None,
                             allow_paid_background: bool = True, canvas: str = DEFAULT_CANVAS,
                             filename_prefix: str = "slide") -> list:
    """
    Generates all slide images based on the plan and saves them to output_dir.
    Returns a list of generated file paths.

    `canvas` selects the card shape ("portrait" for the 4:5 Instagram carousel,
    "landscape" for 16:9 YouTube frames, "story" for 9:16 Shorts) and
    `filename_prefix` keeps the sets side by side in the same post folder.
    """
    os.makedirs(output_dir, exist_ok=True)
    spec = get_canvas(canvas)
    canvas_w, canvas_h = spec["size"]
    total_pages = plan.get("total_pages", 4)
    hooking_title = plan.get("hooking_title", "Trending")
    image_prompt = plan.get("image_prompt", hooking_title)
    slides = plan.get("slides", [])
    theme = plan.get("theme", DEFAULT_THEME)  # randomly assigned color theme for this carousel
    print(f"Using color theme: {theme}")
    
    # The post's photo goes in the cover / one-card photo box: the user's
    # original upload when there is one, else the AI background (generated
    # once and archived as the master, so re-renders never pay again).
    master_bg_path = os.path.join(output_dir, "background_master.png")
    source_path = os.path.join(output_dir, BACKGROUND_SOURCE)
    post_photo, photo_anchor = None, 0.5
    try:
        if reuse_background and os.path.exists(source_path):
            # The user's own photo is shown whole, never cropped.
            post_photo, photo_anchor = Image.open(source_path).convert("RGB"), None
        elif reuse_background and os.path.exists(master_bg_path):
            print(f"Reusing existing background master image: {master_bg_path}")
            # The AI prompt puts the subject in the upper third.
            post_photo, photo_anchor = Image.open(master_bg_path).convert("RGB"), 0.2
    except Exception as e:
        print(f"Failed to load the post photo: {e}")

    if post_photo is None and not allow_paid_background:
        # Editing an existing post (photo added/removed): never spend money on a
        # new background. Missing master -> the photo box is a flat theme tint.
        print("No background master available; drawing without a photo (no API call).")

    if post_photo is None and allow_paid_background:
        raw_bg = generate_dalle_background(image_prompt)
        if raw_bg is not None:
            post_photo, photo_anchor = resize_to_cover(raw_bg, WIDTH, HEIGHT), 0.2
            try:
                post_photo.save(master_bg_path, "PNG")
                print(f"Saved background master image to: {master_bg_path}")
                # A user photo from an earlier run of this post no longer applies.
                if os.path.exists(source_path):
                    os.remove(source_path)
            except Exception as e:
                print(f"Failed to save background master image: {e}")

    image_paths = []
    for slide in slides:
        page_num = slide.get("page", 1)
        img = draw_card_layout(slide, total_pages, hooking_title, article_title=article_title,
                               theme=theme, photo_dir=output_dir, canvas=canvas,
                               post_photo=post_photo, photo_anchor=photo_anchor)

        filename = f"{filename_prefix}_{page_num:02d}.jpg"
        filepath = os.path.join(output_dir, filename)
        
        # Save as JPEG (Quality: 95)
        img.convert("RGB").save(filepath, "JPEG", quality=95)
        image_paths.append(filepath)
        print(f"Generated and saved: {filepath}")
        
    return image_paths

if __name__ == "__main__":
    # Test layout generation
    test_plan = {
        "total_pages": 2,
        "theme": "blue",
        "hooking_title": "테스트 카드뉴스",
        "slides": [
            {"page": 1, "type": "cover", "main_text": "인스타 자동화로\n돈 버는 비밀 공개"},
            {"page": 2, "type": "content", "main_text": "1. 제주 장마 시작 🌧️\n올해 제주 장마는 6월 30일에 시작됐어요.\n**역대 3번째로 늦은 기록입니다** 📈"}
        ]
    }
    generate_carousel_images(test_plan, "./test_output")
