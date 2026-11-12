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
            "single_photo_min": 440,
        },
        # Card 2 (gradient): the copy block starts at the canvas margin and its
        # bottom sits `bottom` px above the card's bottom edge. Wrap width, the
        # "always good" pill font size, the gaps pill-headline and
        # headline-sub-copy, sub-copy (size, line height), headline steps.
        "gradient": {
            "bottom": 110, "wrap": 920, "label": 32, "label_gap": 40,
            "sub": (34, 50), "sub_gap": 52,
            "title_steps": ((112, 124), (102, 114), (94, 106), (86, 98), (78, 90)),
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
        "gradient": {
            "bottom": 90, "wrap": 1320, "label": 32, "label_gap": 36,
            "sub": (36, 52), "sub_gap": 46,
            "title_steps": ((112, 124), (102, 114), (94, 106), (86, 98), (78, 90)),
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
            "single_photo_min": 520,
        },
        # The copy stays clear of the Shorts UI at the bottom (~350px).
        "gradient": {
            "bottom": 380, "wrap": 920, "label": 32, "label_gap": 40,
            "sub": (36, 52), "sub_gap": 52,
            "title_steps": ((112, 124), (102, 114), (94, 106), (86, 98), (78, 90)),
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
# Every one of these is covered by the NanumSquare Round brand fonts, so they
# draw in the card's own typeface instead of falling back to an emoji font.
# U+2764 (❤) is deliberately absent: the brand fonts have no glyph for it, so it
# would render as a tofu box. The outline/solid hearts ♡ ♥ cover the CTA.
_EMOJI_KEEP = {"▶", "◀", "♡", "♥"}  # ▶ ◀ ♡ ♥

def remove_emojis(text: str) -> str:
    """
    Strips pictographic emoji from text (they have no glyph in the brand fonts
    and render as tofu). Intentional design glyphs like the teaser arrow ▶ and
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

# The one-card post (Card 1) shows a three-line body block under the headline;
# the renderer also caps the wrapped rows at three.
SINGLE_BODY_MAX_LINES = 3


def cover_sub_lines(text: Optional[str], max_lines: int = COVER_SUB_MAX_LINES) -> list:
    """
    Cleans typed sub-copy into at most `max_lines` lines.

    Blank lines are dropped so a stray newline from the dashboard textarea does
    not eat one of the slots. Each surviving line keeps its own '**...**'
    markers, which the renderer paints in the theme's key color.

    The cover keeps the default cap; the one-card body passes
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


_PAPER_CACHE = {}


def make_paper_background(width: int, height: int, seed: int) -> Image.Image:
    """
    Off-white newsprint: faint, out-of-focus columns of "text" showing through
    from the other side of the page, plus a little grain. The last page made is
    kept, since the typing frames of a Shorts cut redraw the same page.
    """
    key = (width, height, seed)
    if key not in _PAPER_CACHE:
        _PAPER_CACHE.clear()
        _PAPER_CACHE[key] = _make_paper_background(width, height, seed)
    return _PAPER_CACHE[key].copy()


def _make_paper_background(width: int, height: int, seed: int) -> Image.Image:
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

    def single_frame(self) -> int:
        """
        Card 1's header: "ALWAYS GOOD" on the left and the brand logo (full
        size) on the right, between two rules spaced wide enough for the logo.
        There is no bottom rule. Returns how much taller this header is than
        the regular one, so the page below can move down by that much.
        """
        draw, p, m = self.draw, self.p, self.margin
        x1 = self.W - m
        size = p["logo"]
        header_h = max(p["header_h"], size + 24)
        h_top, h_bot = p["header_top"], p["header_top"] + header_h
        draw.rectangle([m, h_top, x1, h_top + 2], fill=self.ink)
        draw.rectangle([m, h_bot, x1, h_bot + 2], fill=self.ink)
        header_font = get_system_font(p["header_font"], bold=True)
        label_y = h_top + (header_h - p["header_font"]) // 2
        draw.text((m, label_y), PAPER_HEADER_RIGHT, fill=self.ink, font=header_font)
        logo = ink_logo(size)
        if logo is not None:
            self.image.alpha_composite(logo, (x1 - size, h_top + 2 + (header_h - size) // 2))
        return header_h - p["header_h"]

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


def _reveal_counts(lines: list, reveal: Optional[int]) -> list:
    """
    How many characters of each headline line are typed so far, for the typing
    effect of the Shorts cut: `reveal` counts the non-space characters typed
    (None = the whole headline). Spaces show up with the letter after them.
    """
    if reveal is None:
        return [len(line) for line in lines]
    counts, left = [], max(0, reveal)
    for line in lines:
        shown = 0
        for i, ch in enumerate(line):
            if ch != " ":
                if left == 0:
                    break
                left -= 1
                shown = i + 1
        counts.append(shown)
    return counts


def headline_char_count(slide: dict, hooking_title: str = "", article_title: str = None) -> int:
    """Non-space characters in a one-card headline: the typing effect's step count."""
    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    clean, _ = _highlight_marked(_headline_text(headline))
    return sum(1 for ch in clean if not ch.isspace())


def _headline_text(title: str) -> str:
    """
    Collapses whitespace in a headline, except that a typed '<br>' (also
    '<br/>', '<br />') becomes a forced line break.
    """
    parts = re.split(r"\s*<br\s*/?>\s*", title or "", flags=re.IGNORECASE)
    return "\n".join(re.sub(r"\s+", " ", part).strip() for part in parts).strip("\n")


def _headline_rows(title: str, steps, wrap: int, fits, default_last: bool) -> tuple:
    """
    Wraps a headline at the largest step that keeps it to four lines and makes
    `fits(line_count, step)` true; past the smallest step the fourth line ends
    in an ellipsis. '**' words get a marker stroke; without any, the last line
    does when `default_last` is set. Returns (rows, step).
    """
    title, marked = _highlight_marked(_headline_text(title))
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
    body block (about four lines, one highlighted) right under it, and the
    photo filling the rest of the page down to the bottom. Wide canvases put
    the photo in a column beside the copy.
    """
    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    page = PaperPage(canvas, theme, _title_seed(headline))
    p, m = page.p, page.margin
    extra = page.single_frame()

    body_text = remove_emojis((slide.get("sub_text") or "").strip())
    body_logical = [line for line in body_text.split("\n") if line.strip()][:SINGLE_BODY_MAX_LINES]

    y = p["body_top"] + extra
    page.badge("오늘의 한 장", m, y)
    y += p["badge_h"] + p["badge_gap"]
    # No bottom rule on this page, so the photo runs down to where it was.
    bottom = p["rule_y"]
    in_column = photo is not None and not page.side_photo
    # Tighter gaps when the photo sits under the copy, so it gets the room.
    title_gap, photo_gap = (30, 34) if in_column else (36, p["photo_gap"])
    photo_room = p["single_photo_min"] + p["shadow"] + photo_gap if in_column else 0
    wrap = p["title_wrap"] if page.side_photo else p["card_wrap"]

    def fits(count: int, step) -> bool:
        body_rows = _single_body_rows(body_logical, step[2], wrap)
        return y + count * step[1] + title_gap + photo_room + len(body_rows) * step[3] <= bottom

    rows, step = _headline_rows(headline, p["single_steps"], wrap, fits, default_last=False)
    body_rows = _single_body_rows(body_logical, step[2], wrap)
    # Typing effect: only the typed part of the headline is drawn, and a marker
    # stroke appears once its words are fully typed.
    typed_rows = []
    shown_counts = _reveal_counts([r[0] for r in rows], slide.get("_reveal"))
    for (text, font, color, span), shown in zip(rows, shown_counts):
        typed_rows.append((text[:shown], font, color, span if span and shown >= span[1] else None))
    y = page.lines(typed_rows, m, y, step[1]) + title_gap

    if in_column:
        # Body right under the headline; the photo takes everything below it,
        # down to the bottom of the page.
        body_end = page.lines(body_rows, m, y, step[3])
        photo_top = body_end + photo_gap
        page.photo(photo, (m, photo_top, page.W - m, bottom - p["shadow"]), photo_anchor or 0.5,
                   whole=photo_anchor is None, align=(0.5, 1.0))
    else:
        if photo is not None:
            page.photo(photo, p["photo_box"], photo_anchor or 0.5,
                       whole=photo_anchor is None, align=(0.5, 0.5))
        page.lines(body_rows, m, y, step[3])
    return page.image


def _single_body_rows(body_logical: list, size: int, wrap: int) -> list:
    """Card 1's body: at most three rows, with no marker stroke behind any."""
    rows = [(text, font, color, None) for text, font, color, _ in _copy_rows(body_logical, size, wrap)]
    if len(rows) > SINGLE_BODY_MAX_LINES:
        rows = rows[:SINGLE_BODY_MAX_LINES]
        text, font, color, _ = rows[-1]
        rows[-1] = (_ellipsize(text, font, wrap), font, color, None)
    return rows


# --- Card 2: gradient layout ---
# A one-card post: the photo fills the whole card and a color gradient rises
# from the bottom over it. On the solid part sit, left-aligned, a small
# "always good" pill, the headline in an extra-heavy weight and up to two
# small sub-copy lines. The gradient color is the slide's title_color
# (yellow by default), changed from the dashboard.
SPOTLIGHT_LABEL = "always good"
SPOTLIGHT_TITLE_MAX_LINES = 3
SPOTLIGHT_BODY_MAX_LINES = 2
SINGLE_DESIGNS = ("card1", "card2", "card3")
CARD2_DEFAULT_GRADIENT = "yellow"
CARD2_YELLOW = (240, 252, 28)  # the default gradient, a bright lemon-lime
CARD2_INK = (12, 12, 12, 255)


def _card2_gradient_color(name: Optional[str]) -> tuple:
    """RGB of the Card 2 gradient: white, the default yellow or a theme color."""
    name = name or CARD2_DEFAULT_GRADIENT
    if name == "white":
        return (255, 255, 255)
    if name == CARD2_DEFAULT_GRADIENT:
        return CARD2_YELLOW
    return THEMES.get(name, THEMES[CARD2_DEFAULT_GRADIENT])["key"][:3]


def _font_band(font, sample: str = "가Ag") -> tuple:
    """(top, bottom) of the glyph band drawn at y = 0, for vertical placement."""
    if hasattr(font, "getbbox"):
        _, top, _, bottom = font.getbbox(sample)
        return top, bottom
    return 0, getattr(font, "size", 20)


def draw_gradient_single(slide: dict, hooking_title: str, photo: Optional[Image.Image],
                         article_title: str = None, theme: str = "orange",
                         canvas: str = DEFAULT_CANVAS,
                         photo_anchor: Optional[float] = 0.5) -> Image.Image:
    """Card 2: full photo, a color gradient up from the bottom, copy on top of it."""
    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    spec = get_canvas(canvas)
    W, H = spec["size"]
    g = spec["gradient"]
    margin = spec["margin"]
    color = _card2_gradient_color(slide.get("title_color"))
    light = _badge_text_color(color) != (255, 255, 255, 255)
    ink = CARD2_INK if light else (255, 255, 255, 255)
    sub_color = (62, 62, 62, 255) if light else (236, 236, 240, 255)

    if photo is not None:
        # Edge to edge; an uncropped upload is kept toward the top, where
        # faces usually are, since the gradient covers the bottom anyway.
        fitted = resize_to_cover(photo, W, H, 0.3 if photo_anchor is None else photo_anchor)
        image = fitted.convert("RGBA")
    else:
        image = Image.new("RGBA", (W, H), _mix(color, (225, 225, 228), 0.5) + (255,))

    # Headline: the biggest step that fits in two lines, else three. A stroke
    # in the same color thickens the heavy weight further.
    title, _ = _highlight_marked(_headline_text(headline))
    lines = None
    for max_lines in (2, SPOTLIGHT_TITLE_MAX_LINES):
        for size, line_height in g["title_steps"]:
            font = get_system_font(size, bold=True)
            stroke = max(2, size // 30)
            candidate = wrap_text(title, font, g["wrap"] - stroke * 2)
            if len(candidate) <= max_lines:
                lines = candidate
                break
        if lines:
            break
    if not lines:
        lines = _cap_rows(candidate, SPOTLIGHT_TITLE_MAX_LINES, font, g["wrap"] - stroke * 2)

    # Sub-copy: up to two small lines in the regular weight ('**' = bold).
    sub_size, sub_line = g["sub"]
    sub_rows = []
    for logical in cover_sub_lines(remove_emojis(slide.get("sub_text") or ""), SPOTLIGHT_BODY_MAX_LINES):
        clean, bold = strip_highlight_markers(logical)
        sub_font = get_system_font(sub_size, bold=bold)
        sub_rows += [(piece, sub_font) for piece in wrap_text(clean.strip(), sub_font, g["wrap"])]
    if len(sub_rows) > SPOTLIGHT_BODY_MAX_LINES:
        sub_rows = sub_rows[:SPOTLIGHT_BODY_MAX_LINES]
        text, sub_font = sub_rows[-1]
        sub_rows[-1] = (_ellipsize(text, sub_font, g["wrap"]), sub_font)

    # Stack the block up from the bottom: pill, headline, sub-copy.
    label_font = get_system_font(g["label"])
    l_top, l_bottom = _font_band(label_font, SPOTLIGHT_LABEL)
    pad_x, pad_y = int(g["label"] * 0.75), int(g["label"] * 0.42)
    pill_w = _text_width(label_font, SPOTLIGHT_LABEL) + pad_x * 2
    pill_h = (l_bottom - l_top) + pad_y * 2
    t_top, t_bottom = _font_band(font)
    title_h = (len(lines) - 1) * line_height + (t_bottom - t_top) + stroke * 2
    s_top, s_bottom = _font_band(get_system_font(sub_size))
    sub_h = ((len(sub_rows) - 1) * sub_line + (s_bottom - s_top) + g["sub_gap"]) if sub_rows else 0
    block_top = H - g["bottom"] - sub_h - title_h - g["label_gap"] - pill_h
    title_top = block_top + pill_h + g["label_gap"]

    # The gradient: clear well above the block, solid from the headline's
    # middle down, on an eased ramp so the photo melts into the color.
    fade_top = max(0, block_top - int(H * 0.30))
    fade_full = min(H, title_top + title_h // 2)
    column = Image.new("L", (1, H), 0)
    for y in range(fade_top, H):
        t = min(1.0, (y - fade_top) / max(1, fade_full - fade_top))
        column.putpixel((0, y), int(255 * (t * t * (3 - 2 * t))))
    image.paste(Image.new("RGB", (W, H), color), (0, 0), column.resize((W, H)))

    draw = ImageDraw.Draw(image)
    # "always good" pill: dark on light gradients, white on dark ones.
    pill_fill = (24, 24, 24, 255) if light else (255, 255, 255, 255)
    pill_ink = (255, 255, 255, 255) if light else CARD2_INK
    draw.rounded_rectangle([margin, block_top, margin + pill_w, block_top + pill_h],
                           radius=pill_h // 2, fill=pill_fill)
    draw.text((margin + pad_x, block_top + pad_y - l_top), SPOTLIGHT_LABEL, fill=pill_ink, font=label_font)

    # Headline, typed in line by line for the Shorts cut.
    y = title_top + stroke - t_top
    for line, shown in zip(lines, _reveal_counts(lines, slide.get("_reveal"))):
        if shown:
            draw_text_safe(draw, (margin + stroke, y), line[:shown], fill=ink, font=font,
                           stroke_width=stroke, stroke_fill=ink)
        y += line_height

    y = title_top + title_h + g["sub_gap"] - s_top
    for text, sub_font in sub_rows:
        draw_text_safe(draw, (margin, y), text, fill=sub_color, font=sub_font)
        y += sub_line
    return image


# --- Card 3: full-photo layout ---
# The photo fills the whole 4:5 card; an "always good" tag sits top-left (white
# on black) and the headline is left-aligned near the bottom in black type on
# solid color bars, one bar per line. The bar color is the slide's title_color
# (yellow by default). On the 9:16 Shorts canvas the 4:5 card sits in the
# middle with white above and below.
CARD3_TITLE_MAX_LINES = 3
CARD3_DEFAULT_BAR = "yellow"
CARD3_INK = (12, 12, 12, 255)


CARD3_BRIGHT_YELLOW = (255, 236, 0, 255)  # the default bar, brighter than the theme yellow


def _card3_bar_color(name: Optional[str]) -> tuple:
    if name == "white":
        return (255, 255, 255, 255)
    if (name or CARD3_DEFAULT_BAR) == CARD3_DEFAULT_BAR:
        return CARD3_BRIGHT_YELLOW
    return THEMES.get(name or CARD3_DEFAULT_BAR, THEMES[CARD3_DEFAULT_BAR])["key"][:3] + (255,)


# The carousel ("Generate") is drawn in the Card 3 look too: the cover is Card 3
# as is, and cards 2..N put their copy on the same bars in a smaller size.
CARD3_TITLE_STEPS = (92, 84, 76, 68, 60)
CARD3_BODY_STEPS = (58, 54, 50, 46, 42)
CARD3_BODY_MAX_LINES = 7


def _card3_body_lines(text: str, font, wrap: int) -> list:
    """A content card's copy as bar rows: each '\\n' line wrapped, '**' markers dropped."""
    rows = []
    for logical in format_korean_line_breaks(text).split("\n"):
        clean, _ = strip_highlight_markers(logical)
        if clean.strip():
            rows += wrap_text(clean.strip(), font, wrap)
    return rows


def draw_photo_single(slide: dict, hooking_title: str, photo: Optional[Image.Image],
                      article_title: str = None, theme: str = "orange",
                      canvas: str = DEFAULT_CANVAS,
                      photo_anchor: Optional[float] = 0.5,
                      compact: bool = False) -> Image.Image:
    """
    Card 3: full-bleed photo, headline on color bars at the bottom left.
    `compact` draws a carousel content card instead: its whole copy on the
    same bars, in a smaller size.
    """
    if canvas == "story":
        # Shorts: the 4:5 card centered on a white 9:16 frame.
        card = draw_photo_single(slide, hooking_title, photo, article_title=article_title,
                                 theme=theme, canvas=DEFAULT_CANVAS, photo_anchor=photo_anchor,
                                 compact=compact)
        W, H = get_canvas("story")["size"]
        frame = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        frame.paste(card, ((W - card.width) // 2, (H - card.height) // 2))
        return frame

    headline = remove_emojis((slide.get("main_text") or "").strip())
    if not headline and not compact:
        headline = remove_emojis((article_title or hooking_title or "").strip())
    W, H = get_canvas(canvas)["size"]
    unit = W / 1080 if W <= H else H / 1350  # scale for the wide canvas
    margin = int(80 * unit)

    if photo is not None:
        # Fill the card edge to edge (top, bottom, left, right). The crop is
        # centered, so a tall photo loses as much at the top as at the bottom.
        fitted = resize_to_cover(photo, W, H, 0.5)
        image = fitted.convert("RGBA")
    else:
        image = Image.new("RGBA", (W, H), _mix(get_theme(theme)["key"][:3], (235, 235, 235), 0.55) + (255,))
    draw = ImageDraw.Draw(image)

    # "always good" tag, top-left: white letters on a black box.
    tag_font = get_system_font(int(30 * unit), bold=True)
    tag_pad_x, tag_pad_y = int(18 * unit), int(10 * unit)
    tx, ty = margin, int(70 * unit)
    if hasattr(tag_font, "getbbox"):
        _, t_top, _, t_bottom = tag_font.getbbox(SPOTLIGHT_LABEL)
    else:
        t_top, t_bottom = 0, int(30 * unit)
    tag_w = _text_width(tag_font, SPOTLIGHT_LABEL)
    draw.rectangle([tx, ty, tx + tag_w + tag_pad_x * 2, ty + (t_bottom - t_top) + tag_pad_y * 2],
                   fill=(0, 0, 0, 255))
    draw.text((tx + tag_pad_x, ty + tag_pad_y - t_top), SPOTLIGHT_LABEL,
              fill=(255, 255, 255, 255), font=tag_font)

    wrap = W - margin * 2 - int(40 * unit)
    lines, font = None, None
    if compact:
        # Content card: the biggest small size that keeps the copy within
        # CARD3_BODY_MAX_LINES bars, else the smallest one, cut short.
        for size in (int(v * unit) for v in CARD3_BODY_STEPS):
            font = get_system_font(size, bold=True)
            candidate = _card3_body_lines(headline, font, wrap)
            if len(candidate) <= CARD3_BODY_MAX_LINES:
                lines = candidate
                break
        if lines is None:
            lines = _cap_rows(candidate, CARD3_BODY_MAX_LINES, font, wrap)
    else:
        # Headline: the biggest size that fits in two lines, else three.
        title, _ = _highlight_marked(_headline_text(headline))
        steps = [int(v * unit) for v in CARD3_TITLE_STEPS]
        for max_lines in (2, CARD3_TITLE_MAX_LINES):
            for size in steps:
                font = get_system_font(size, bold=True)
                candidate = wrap_text(title, font, wrap)
                if len(candidate) <= max_lines:
                    lines = candidate
                    break
            if lines:
                break
        if not lines:
            lines = _cap_rows(candidate, CARD3_TITLE_MAX_LINES, font, wrap)

    # One bar per line, hugging its text, stacked without a gap and anchored
    # to the bottom of the card.
    bar = _card3_bar_color(slide.get("title_color"))
    # Black type on light bars (yellow, white), white type on dark ones.
    ink = CARD3_INK if _badge_text_color(bar) != (255, 255, 255, 255) else (255, 255, 255, 255)
    if hasattr(font, "getbbox"):
        _, g_top, _, g_bottom = font.getbbox("가Ag%")
    else:
        g_top, g_bottom = 0, font.size
    pad_x, pad_y = int(14 * unit), int((12 if compact else 16) * unit)
    bar_h = (g_bottom - g_top) + pad_y * 2
    bottom = H - int(185 * unit)
    y = bottom - bar_h * len(lines)
    for line, shown in zip(lines, _reveal_counts(lines, slide.get("_reveal"))):
        # Typing effect: each bar grows with its typed text.
        line = line[:shown]
        if not line:
            y += bar_h
            continue
        line_w = _text_width(font, line)
        draw.rectangle([margin, y, margin + line_w + pad_x * 2, y + bar_h], fill=bar)
        draw_text_safe(draw, (margin + pad_x, y + pad_y - g_top), line, fill=ink, font=font)
        y += bar_h
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
    if slide.get("design") == "card3":
        # Card 3 look (the one-card post, and every card of a carousel made in
        # it). A photo the user put on this card replaces the post photo here.
        own = resolve_user_photo(slide, photo_dir)
        if own:
            post_photo, photo_anchor = Image.open(own).convert("RGB"), None
        return draw_photo_single(slide, hooking_title, post_photo, article_title=article_title,
                                 theme=theme, canvas=canvas, photo_anchor=photo_anchor,
                                 compact=slide_type not in ("cover", "single"))
    if slide_type == "cover":
        return draw_paper_cover(slide, hooking_title, post_photo, article_title=article_title,
                                theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    if slide_type == "single" and slide.get("design") == "card2":
        return draw_gradient_single(slide, hooking_title, post_photo, article_title=article_title,
                                    theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    if slide_type == "single":
        return draw_paper_single(slide, hooking_title, post_photo, article_title=article_title,
                                 theme=theme, canvas=canvas, photo_anchor=photo_anchor)
    return draw_paper_card(slide, total_pages, theme=theme, canvas=canvas,
                           photo_path=resolve_user_photo(slide, photo_dir))



def load_post_photo(output_dir: str) -> tuple:
    """
    The post's saved photo and its crop anchor: the user's upload (shown whole,
    anchor None), else the AI background master (anchor 0.2), else (None, 0.5).
    """
    source_path = os.path.join(output_dir, BACKGROUND_SOURCE)
    master_bg_path = os.path.join(output_dir, "background_master.png")
    try:
        if os.path.exists(source_path):
            return Image.open(source_path).convert("RGB"), None
        if os.path.exists(master_bg_path):
            print(f"Reusing existing background master image: {master_bg_path}")
            # The AI prompt puts the subject in the upper third.
            return Image.open(master_bg_path).convert("RGB"), 0.2
    except Exception as e:
        print(f"Failed to load the post photo: {e}")
    return None, 0.5


def render_typing_frames(plan: dict, output_dir: str, frames_dir: str,
                         canvas: str = "story", article_title: str = None) -> list:
    """
    The typing effect of a one-card post's Shorts cut: the card drawn once per
    typed headline character, from an empty headline (frame 0) to the whole
    one. Uses the saved photo only (no API call). Returns the frame paths, or
    [] when the plan has no one-card slide.
    """
    single = next((s for s in plan.get("slides", []) if s.get("type") == "single"), None)
    if single is None:
        return []
    os.makedirs(frames_dir, exist_ok=True)
    post_photo, photo_anchor = load_post_photo(output_dir)
    hooking_title = plan.get("hooking_title", "")
    theme = plan.get("theme", DEFAULT_THEME)
    total = headline_char_count(single, hooking_title, article_title)
    paths = []
    for typed in range(total + 1):
        img = draw_card_layout(dict(single, _reveal=typed), plan.get("total_pages", 1), hooking_title,
                               article_title=article_title, theme=theme, photo_dir=output_dir,
                               canvas=canvas, post_photo=post_photo, photo_anchor=photo_anchor)
        path = os.path.join(frames_dir, f"type_{typed:03d}.jpg")
        img.convert("RGB").save(path, "JPEG", quality=92)
        paths.append(path)
    return paths


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
    if reuse_background:
        # The user's own photo is shown whole, never cropped.
        post_photo, photo_anchor = load_post_photo(output_dir)

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
