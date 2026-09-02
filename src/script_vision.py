import os
import re
import requests
import urllib.parse
from io import BytesIO
from typing import Optional
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define Dimensions for 4:5 Instagram Post
WIDTH = 1080
HEIGHT = 1350

# Card canvases. "portrait" is the Instagram carousel card and its numbers are
# exactly the ones this layout was tuned with. "landscape" redraws the same
# content on a 16:9 frame for YouTube, so the video fills the screen instead of
# sitting between blurred pillarbox bars. Every position the layout code needs
# lives here, so the two shapes share one code path.
CANVASES = {
    "portrait": {
        "size": (WIDTH, HEIGHT),
        "margin": 80,
        "watermark_pos": (50, 50),
        "watermark_width": 160,
        "bar_from_bottom": (35, 31),   # accent bar: top/bottom offsets from H
        "page_from_bottom": 92,        # page indicator: centered, just above the bar
        "page_font": 26,
        "cover": {
            "grad_start": 500,
            "badge_box": (80, 650, 390, 695),
            "badge_font": 22,
            "title_top": 730,
            "title_wrap": 920,
            "title_steps": ((84, 110), (74, 98), (64, 86), (56, 76)),
            # Optional sub-copy typed under the title from the dashboard
            # (up to COVER_SUB_MAX_LINES lines). Absent on a fresh post.
            "sub_font": 30,
            "sub_line": 46,
            "sub_gap": 30,
            "sub_wrap": 900,
            "teaser_from_bottom": 143,
            "teaser_clear": 150,
            "teaser_font": 26,
            # The carousel is swiped, so it keeps the swipe prompt. A video has
            # nothing to swipe, so `teaser_text_video` signs off with the brand
            # name instead (see the `for_video` flag).
            "teaser_text": "옆으로 넘겨서 보기 ▶",
            "teaser_text_video": "always good",
        },
        # The one-card post: headline plus a short body block, both sitting on
        # the darkened lower half of the photo. It carries more copy than a
        # cover, so its gradient starts higher and reaches full strength sooner.
        "single": {
            "grad_start": 260,
            "grad_full": 620,
            "grad_alpha": 232,
            "badge_text": "오늘의 한장 이슈",
            "badge_font": 22,
            "badge_h": 45,
            "badge_gap": 30,          # badge bottom -> headline top
            "title_wrap": 920,
            "body_wrap": 880,
            "title_body_gap": 38,
            # (headline size, headline line height, body size, body line height)
            "steps": ((80, 104, 40, 62), (70, 92, 36, 56), (62, 82, 33, 51), (54, 72, 30, 46)),
            "block_bottom": 168,      # bottom edge of the text block, from H
            "block_top_min": 430,     # never push the block higher (keeps the photo visible)
            "sign_from_bottom": 118,
            "sign_font": 26,
            "sign_text": "always good",
        },
        "card": {
            "box": (80, 240, 1000, 1130),
            "wrap": 820,
            "badge_top": 280,
            "text_top": 360,
            "body": 43, "line": 70,
            "body_photo": 34, "line_photo": 54,
            "cta": 46, "cta_line": 80,
            "cta_photo": 36, "cta_line_photo": 56,
            "photo_min": 340, "photo_max": 640,
            "min_line": 50, "min_line_photo": 40,
            "badge_h": 45,
        },
    },
    "landscape": {
        # 1920x1080 is YouTube's recommended long-form size. All text is drawn
        # natively at this size, so it stays crisp when the video step scales
        # the frame down to 1280x720.
        "size": (1920, 1080),
        "margin": 140,
        "watermark_pos": (60, 55),
        "watermark_width": 190,
        "bar_from_bottom": (30, 26),
        "page_from_bottom": 74,
        "page_font": 28,
        "cover": {
            "grad_start": 340,
            "badge_box": (140, 470, 470, 518),
            "badge_font": 26,
            "title_top": 560,
            "title_wrap": 1250,
            "title_steps": ((96, 128), (86, 116), (76, 102), (66, 90)),
            "sub_font": 34,
            "sub_line": 52,
            "sub_gap": 32,
            "sub_wrap": 1230,
            "teaser_from_bottom": 118,
            "teaser_clear": 130,
            "teaser_font": 30,
            # This canvas only ever feeds the YouTube video, so there is no
            # swipe-prompt variant to choose between.
            "teaser_text": "always good",
        },
        "single": {
            "grad_start": 150,
            "grad_full": 430,
            "grad_alpha": 232,
            "badge_text": "오늘의 한장 이슈",
            "badge_font": 26,
            "badge_h": 48,
            "badge_gap": 28,
            "title_wrap": 1350,
            "body_wrap": 1300,
            "title_body_gap": 34,
            "steps": ((88, 116, 44, 68), (78, 102, 40, 62), (68, 90, 36, 56), (60, 80, 32, 50)),
            "block_bottom": 150,
            "block_top_min": 250,
            "sign_from_bottom": 100,
            "sign_font": 30,
            "sign_text": "always good",
        },
        "card": {
            # Kept well inside the frame: a card spanning the full 1920 would
            # push lines past a comfortable reading length.
            "box": (300, 130, 1620, 930),
            "wrap": 1100,
            "badge_top": 175,
            "text_top": 265,
            "body": 44, "line": 68,
            "body_photo": 36, "line_photo": 56,
            "cta": 50, "cta_line": 84,
            "cta_photo": 40, "cta_line_photo": 62,
            "photo_min": 220, "photo_max": 430,
            "min_line": 48, "min_line_photo": 40,
            "badge_h": 48,
        },
    },
    "story": {
        # 9:16 for a Shorts/Reels cut. Drawn at 1080x1920 and scaled down by the
        # video step, so the card fills the phone screen with nothing cropped and
        # no blurred bands. The bottom 480px (25% of the frame) is left empty:
        # that band is where the Shorts player stacks its title, handle and
        # buttons, so nothing of the card may sit there. The logo starts 120px
        # down for the same reason: YouTube draws its own top bar over the first
        # ~100px of the frame.
        "size": (1080, 1920),
        "margin": 80,
        "watermark_pos": (50, 120),
        "watermark_width": 160,
        "bar_from_bottom": (480, 476),
        "page_from_bottom": 536,
        "page_font": 26,
        "cover": {
            "grad_start": 710,
            "badge_box": (80, 900, 390, 945),
            "badge_font": 22,
            "title_top": 980,
            "title_wrap": 920,
            "title_steps": ((84, 110), (74, 98), (64, 86), (56, 76)),
            "sub_font": 27,
            "sub_line": 42,
            "sub_gap": 26,
            "sub_wrap": 900,
            "teaser_from_bottom": 590,
            "teaser_clear": 600,
            "teaser_font": 26,
            "teaser_text": "옆으로 넘겨서 보기 ▶",
            "teaser_text_video": "always good",
        },
        "single": {
            "grad_start": 330,
            "grad_full": 750,
            "grad_alpha": 232,
            "badge_text": "오늘의 한장 이슈",
            "badge_font": 22,
            "badge_h": 45,
            "badge_gap": 30,
            "title_wrap": 920,
            "body_wrap": 880,
            "title_body_gap": 38,
            "steps": ((80, 104, 40, 62), (70, 92, 36, 56), (62, 82, 33, 51), (54, 72, 30, 46)),
            "block_bottom": 630,
            "block_top_min": 500,
            "sign_from_bottom": 570,
            "sign_font": 26,
            "sign_text": "always good",
        },
        "card": {
            "box": (80, 290, 1000, 1290),
            "wrap": 820,
            "badge_top": 330,
            "text_top": 410,
            "body": 43, "line": 70,
            "body_photo": 34, "line_photo": 54,
            "cta": 46, "cta_line": 80,
            "cta_photo": 36, "cta_line_photo": 56,
            "photo_min": 340, "photo_max": 700,
            "min_line": 50, "min_line_photo": 40,
            "badge_h": 45,
        },
    },
}
DEFAULT_CANVAS = "portrait"


def get_canvas(name: str) -> dict:
    return CANVASES.get(name or DEFAULT_CANVAS, CANVASES[DEFAULT_CANVAS])

# Color themes. The creative agent assigns a theme name at random (independent of
# the article topic); the renderer maps it to a palette. Each theme defines the
# key/accent color plus the gradient fallback used when no AI background image is available.
THEMES = {
    "orange": {"key": (255, 102, 0, 255),  "grad_start": (24, 20, 16), "grad_end": (48, 22, 8)},
    "blue":   {"key": (10, 132, 255, 255), "grad_start": (12, 16, 30), "grad_end": (10, 28, 54)},
    "green":  {"key": (34, 197, 94, 255),  "grad_start": (12, 24, 18), "grad_end": (8, 38, 26)},
    "purple": {"key": (149, 97, 246, 255), "grad_start": (22, 16, 34), "grad_end": (34, 16, 50)},
    "pink":   {"key": (244, 63, 94, 255),  "grad_start": (30, 14, 20), "grad_end": (48, 14, 28)},
    "teal":   {"key": (20, 184, 166, 255), "grad_start": (10, 26, 26), "grad_end": (8, 38, 38)},
    "yellow": {"key": (250, 204, 21, 255), "grad_start": (26, 22, 8),  "grad_end": (44, 34, 6)},
    "red":    {"key": (255, 59, 48, 255),  "grad_start": (28, 12, 12), "grad_end": (50, 12, 10)},
}
DEFAULT_THEME = "orange"

def get_theme(name: str) -> dict:
    """Resolves a theme name to its palette, falling back to the default theme."""
    if isinstance(name, str):
        key = name.strip().lower()
        if key in THEMES:
            return THEMES[key]
    return THEMES[DEFAULT_THEME]

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

def break_after_commas(text: str) -> str:
    """
    Starts a new line after every comma, so a card never carries a clause past a
    pause. The comma stays at the end of the line it ends.

    A comma sitting between two digits ("1,000원") is a thousands separator, not
    a pause, so it is left alone. Each source line is processed on its own, which
    keeps a line that ends in a comma from producing an empty line.
    """
    if not text:
        return text

    SEPARATOR = "\x00"  # stands in for thousands separators while we split
    lines = []
    for line in text.split("\n"):
        protected = re.sub(r'(?<=\d),(?=\d)', SEPARATOR, line)
        broken = re.sub(r',[ \t]*', ',\n', protected)
        lines.append(broken.replace(SEPARATOR, ",").rstrip())
    return "\n".join(lines)


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

def draw_logo_watermark(image: Image.Image, opacity: float = 0.45,
                        pos: tuple = (50, 50), target_width: int = 160):
    """
    Loads 'img/alwaysgood_logo.png', resizes it to a suitable size,
    adjusts its opacity, and pastes it in the top-left corner of the image.
    `pos`/`target_width` scale it to whichever canvas is being drawn.
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
        
        # Place in the top-LEFT corner with padding: the right side is covered by
        # Instagram's action icons on Reels, and the bottom by the caption
        # preview, so the top-left is the one corner that always stays visible.
        # It sits clear of the content card, which starts lower down.
        x, y = pos

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
        
        # Optimize prompt to generate a highly intuitive, direct visual concept matching the title keywords.
        # Style is photorealistic (objects / scenery / texture), never illustration: the cover reads as a
        # real editorial photograph. Faces stay banned because AI faces look uncanny at card-news scale.
        is_english = prompt_text and any(c.isalpha() for c in prompt_text) and not any(ord(c) > 127 for c in prompt_text)

        # Shared style rules so both language branches produce the same photographic look.
        PHOTO_STYLE = (
            "Photorealistic editorial photograph, shot on a full-frame DSLR with a 50mm prime lens, "
            "natural directional lighting, shallow depth of field, realistic materials and surface texture, "
            "true-to-life colors, subtle film grain, high dynamic range, sharp focus on the main subject. "
        )
        # The cover title sits over a dark bottom gradient, so the lower third must stay visually quiet.
        COMPOSITION = (
            "Center the subject in the upper two thirds of the frame; keep the bottom third simple, "
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
    Stores a user-supplied photo as this post's background master, cropped to the
    4:5 card size. Every card is then drawn over that photo instead of over an
    AI-generated one, so attaching a photo also skips the paid image API call.
    """
    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(BytesIO(file_bytes)).convert("RGB")
    cover = resize_to_cover(img, WIDTH, HEIGHT)

    filepath = os.path.join(output_dir, "background_master.png")
    cover.save(filepath, "PNG")
    print(f"Saved user-supplied background master: {filepath}")
    return filepath

def resolve_user_photo(slide: dict, photo_dir: str) -> Optional[str]:
    """Path of the photo attached to this slide, or None when there isn't one."""
    name = (slide.get("user_photo") or "").strip()
    if not name or not photo_dir:
        return None
    path = os.path.join(photo_dir, os.path.basename(name))
    return path if os.path.exists(path) else None


def paste_slide_photo(image: Image.Image, photo_path: str, x0: int, y0: int, x1: int,
                      photo_h: int, radius: int = 35) -> None:
    """
    Draws a user photo across the top of the content card, center-cropped to fill
    the card width. Only the top corners are rounded so the photo sits flush
    against the card body holding the copy underneath.
    """
    box_w = x1 - x0
    photo = resize_to_cover(Image.open(photo_path).convert("RGB"), box_w, photo_h)

    mask = Image.new("L", (box_w, photo_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, box_w - 1, photo_h - 1], radius=radius, fill=255)
    # Square off the bottom corners: they meet the text area, not the card edge.
    mask_draw.rectangle([0, photo_h - radius - 1, box_w - 1, photo_h - 1], fill=255)

    image.paste(photo, (x0, y0), mask)


def apply_dark_gradient(image: Image.Image, width: int, height: int, start_y: int,
                        max_alpha: int, full_y: int = None) -> Image.Image:
    """
    Darkens an image from `start_y` downwards so white copy stays readable on top
    of a photo. The overlay fades in linearly and reaches `max_alpha` at `full_y`
    (the bottom edge by default), holding it from there down.
    """
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(overlay)
    span = max(1, (full_y or height) - start_y)
    for y in range(start_y, height):
        alpha = min(max_alpha, int(max_alpha * (y - start_y) / span))
        g_draw.line([(0, y), (width, y)], fill=(10, 10, 15, alpha))
    return Image.alpha_composite(image, overlay)


def draw_card_layout(slide: dict, total_pages: int, hooking_title: str, bg_image: Image.Image = None, article_title: str = None, theme: str = "orange", photo_dir: str = None, canvas: str = DEFAULT_CANVAS, for_video: bool = False) -> Image.Image:
    """
    Generates a single image slide based on its content and type.
    Uses a premium glassmorphic card news layout structure for content/CTA,
    and a bold bottom-gradient layout for the cover to make the title pop.
    The accent/key color and gradient fallback are driven by the chosen theme.
    `canvas` picks the shape: "portrait" (4:5 Instagram) or "landscape" (16:9
    YouTube); the layout numbers for each live in CANVASES. `for_video` marks a
    card that will end up in a video rather than in the swipeable carousel, which
    swaps the cover's swipe prompt for the brand sign-off.
    """
    slide_type = slide.get("type", "content")
    theme_data = get_theme(theme)
    key_color = theme_data["key"]  # theme accent color

    spec = get_canvas(canvas)
    W, H = spec["size"]
    margin = spec["margin"]
    cover_spec = spec["cover"]
    card_spec = spec["card"]

    # The cover and the one-card post both write straight onto the photo, so they
    # keep it crisp and darken it from a gradient instead of blurring it.
    full_bleed = slide_type in ("cover", "single")
    single_spec = spec["single"]

    if bg_image is not None:
        # We make a copy of the pre-resized cover image
        image = bg_image.copy()

        # Ensure RGBA mode
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        if not full_bleed:
            # Light blur on content slides: enough to keep the copy card readable
            # while the photo behind it stays recognizable (a 15px blur turned it
            # into an unreadable smear).
            image = image.filter(ImageFilter.GaussianBlur(7))
            # Draw standard transparent overlay for content slides
            overlay = Image.new("RGBA", (W, H), (10, 10, 15, 70)) # ~27% opacity
            image = Image.alpha_composite(image, overlay)
        elif slide_type == "single":
            image = apply_dark_gradient(image, W, H, single_spec["grad_start"],
                                        single_spec["grad_alpha"], single_spec["grad_full"])
        else:
            # For Cover Slide: Crisp background with bottom-up dark gradient shadow
            image = apply_dark_gradient(image, W, H, cover_spec["grad_start"], 240)
    else:
        # Fallback to premium gradient (theme-tinted) if bg_image is None
        color_start = theme_data["grad_start"]
        color_end = theme_data["grad_end"]
        image = draw_gradient_background(W, H, color_start, color_end)
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Still apply the bottom gradient overlay for consistency on fallback
        if slide_type == "single":
            image = apply_dark_gradient(image, W, H, single_spec["grad_start"],
                                        single_spec["grad_alpha"], single_spec["grad_full"])
        elif slide_type == "cover":
            image = apply_dark_gradient(image, W, H, cover_spec["grad_start"], 220)

    draw = ImageDraw.Draw(image)

    # Bottom key color brand accent bar (drawn on all pages)
    bar_top, bar_bottom = spec["bar_from_bottom"]
    draw.rectangle([margin, H - bar_top, W - margin, H - bar_bottom], fill=key_color)

    # Page indicator, centered at the bottom of every card just above the accent
    # bar. It sits outside the content card, so drawing it here (before the card
    # is composited on top) is safe for every slide type. A one-card post has no
    # pages to count, so it is skipped there.
    page_num = slide.get("page", 1)
    if total_pages > 1:
        page_text = f"{page_num} / {total_pages}"
        page_font = get_system_font(spec["page_font"])
        page_w = _text_width(page_font, page_text)
        draw.text(((W - page_w) // 2, H - spec["page_from_bottom"]), page_text,
                  fill=(180, 180, 180, 220), font=page_font)

    if slide_type == "cover":
        # Cover Page Layout (No card, text drawn directly on bottom gradient)

        # Draw cover top badge
        bx0, by0, bx1, by1 = cover_spec["badge_box"]
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=15, fill=key_color)
        badge_font = get_system_font(cover_spec["badge_font"])
        draw.text((bx0 + 30, by0 + 10), "TRENDING INSIGHT", fill=(255, 255, 255, 255), font=badge_font)
        
        # Draw Main Title (Bold & Large)
        # Prefer the AI-generated cover hook (punchy, engaging) over the raw
        # scraped article title. Fall back to the article/hooking title only
        # when the cover copy is missing (e.g. legacy plans).
        title_text = (slide.get("main_text") or "").strip()
        if not title_text:
            title_text = (article_title or hooking_title or "").strip()

        title_text, _ = strip_highlight_markers(title_text)
        title_text = remove_emojis(title_text)
        title_text = break_after_commas(title_text)

        # Sub-copy under the title: up to three lines the user types in the
        # dashboard. A freshly generated post has none, so a cover without
        # sub-copy is drawn exactly as before.
        sub_font = get_system_font(cover_spec["sub_font"])
        sub_font_bold = get_system_font(cover_spec["sub_font"], bold=True)
        sub_line_h = cover_spec["sub_line"]
        sub_gap = cover_spec["sub_gap"]

        # Each typed line carries its own '**highlight**' state and may still
        # wrap if it runs wider than the card.
        sub_lines = []
        for logical in cover_sub_lines(slide.get("sub_text")):
            clean, has_highlight = strip_highlight_markers(logical)
            line_font = sub_font_bold if has_highlight else sub_font
            line_color = key_color if has_highlight else (226, 228, 234, 255)
            for piece in wrap_text(clean, line_font, cover_spec["sub_wrap"]):
                sub_lines.append((piece, line_font, line_color))

        def sub_block_height(count: int) -> int:
            return sub_gap + count * sub_line_h if count else 0

        # Fit the hook: start at a large size and step down if it wraps to many
        # lines, so the title never overflows into the teaser instead of being
        # hard-truncated with an ellipsis. The sub-copy shares that budget, so a
        # cover carrying one gets a slightly smaller title.
        y_start = cover_spec["title_top"]
        teaser_top = H - cover_spec["teaser_clear"]  # keep clear of the bottom teaser text
        title_font = None
        lines = []
        for font_size, line_height in cover_spec["title_steps"]:
            title_font = get_system_font(font_size, bold=True)
            lines = wrap_text(title_text, title_font, cover_spec["title_wrap"])
            if y_start + len(lines) * line_height + sub_block_height(len(sub_lines)) <= teaser_top:
                break

        # Both blocks long even at the smallest step: drop sub-copy lines from
        # the end rather than letting the text run over the teaser.
        while sub_lines and y_start + len(lines) * line_height + sub_block_height(len(sub_lines)) > teaser_top:
            sub_lines.pop()

        y_cursor = y_start
        for line in lines:
            # Draw a subtle drop shadow (semi-transparent dark gray) at (3, 3) offset
            draw_text_safe(draw, (margin + 3, y_cursor + 3), line, fill=(10, 10, 15, 200), font=title_font, stroke_width=0)
            # Set stroke_width to 0 for maximum clarity, avoiding fat/bloated rendering
            draw_text_safe(draw, (margin, y_cursor), line, fill=(255, 255, 255, 255), font=title_font, stroke_width=0)
            y_cursor += line_height

        if sub_lines:
            y_cursor += sub_gap
            for text, line_font, line_color in sub_lines:
                draw_text_safe(draw, (margin + 2, y_cursor + 2), text, fill=(10, 10, 15, 190), font=line_font)
                draw_text_safe(draw, (margin, y_cursor), text, fill=line_color, font=line_font)
                y_cursor += sub_line_h

        # Draw teaser text at the bottom. The logo moved to the top-left corner,
        # so the teaser reclaims the full-width left margin used by the title.
        teaser_text = cover_spec["teaser_text"]
        if for_video:
            teaser_text = cover_spec.get("teaser_text_video", teaser_text)
        teaser_font = get_system_font(cover_spec["teaser_font"])
        draw.text((margin, H - cover_spec["teaser_from_bottom"]), teaser_text, fill=key_color, font=teaser_font)

    elif slide_type == "single":
        # One-card post: the whole story lives on this single image, so the
        # headline (main_text) is followed by a short body block (sub_text)
        # instead of continuing onto a next card.
        headline = (slide.get("main_text") or "").strip()
        if not headline:
            headline = (article_title or hooking_title or "").strip()
        headline, _ = strip_highlight_markers(headline)
        headline = remove_emojis(headline)
        headline = break_after_commas(headline)

        body_text = break_after_commas(remove_emojis((slide.get("sub_text") or "").strip()))
        # Three to five typed lines carry the story. Anything past the cap is
        # dropped rather than allowed to push the block up over the photo.
        body_logical = [line for line in body_text.split("\n") if line.strip()][:SINGLE_BODY_MAX_LINES]

        badge_h = single_spec["badge_h"]
        block_bottom = H - single_spec["block_bottom"]
        block_top_min = single_spec["block_top_min"]

        # Step the type down until headline + body fit above the sign-off line;
        # the smallest step is the floor, so very long copy just gets tighter.
        for title_size, title_line, body_size, body_line in single_spec["steps"]:
            title_font = get_system_font(title_size, bold=True)
            body_font = get_system_font(body_size)
            body_font_bold = get_system_font(body_size, bold=True)

            title_lines = wrap_text(headline, title_font, single_spec["title_wrap"])

            # One line of the body is wrapped in **...**: that is the sentence the
            # reader should remember, so it gets the theme's key color.
            body_lines = []
            for logical in body_logical:
                clean, has_highlight = strip_highlight_markers(logical)
                line_font = body_font_bold if has_highlight else body_font
                line_color = key_color if has_highlight else (226, 228, 234, 255)
                for sub in wrap_text(clean.strip(), line_font, single_spec["body_wrap"]):
                    body_lines.append((sub, line_font, line_color))

            block_height = badge_h + single_spec["badge_gap"] + len(title_lines) * title_line
            if body_lines:
                block_height += single_spec["title_body_gap"] + len(body_lines) * body_line
            if block_bottom - block_height >= block_top_min:
                break

        # Anchor the block to the bottom, growing upwards as the copy gets longer.
        y_cursor = max(block_top_min, block_bottom - block_height)

        # Badge pill, left aligned with the copy below it
        badge_text = single_spec["badge_text"]
        badge_font = get_system_font(single_spec["badge_font"], bold=True)
        if hasattr(badge_font, "getbbox"):
            bbox = badge_font.getbbox(badge_text)
            badge_text_w, badge_text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            badge_text_w, badge_text_h = len(badge_text) * 11, single_spec["badge_font"]
        draw.rounded_rectangle([margin, y_cursor, margin + badge_text_w + 60, y_cursor + badge_h],
                               radius=15, fill=key_color)
        draw.text((margin + 30, y_cursor + (badge_h - badge_text_h) // 2 - 2), badge_text,
                  fill=(255, 255, 255, 255), font=badge_font)
        y_cursor += badge_h + single_spec["badge_gap"]

        for line in title_lines:
            draw_text_safe(draw, (margin + 3, y_cursor + 3), line, fill=(10, 10, 15, 200), font=title_font)
            draw_text_safe(draw, (margin, y_cursor), line, fill=(255, 255, 255, 255), font=title_font)
            y_cursor += title_line

        if body_lines:
            y_cursor += single_spec["title_body_gap"]
            for text, line_font, line_color in body_lines:
                draw_text_safe(draw, (margin + 2, y_cursor + 2), text, fill=(10, 10, 15, 170), font=line_font)
                draw_text_safe(draw, (margin, y_cursor), text, fill=line_color, font=line_font)
                y_cursor += body_line

        # No next card to tease, so the card signs off with the brand name.
        sign_font = get_system_font(single_spec["sign_font"])
        draw.text((margin, H - single_spec["sign_from_bottom"]), single_spec["sign_text"],
                  fill=key_color, font=sign_font)

    else:
        # Define layout dimensions for content/CTA cards
        card_x0, card_y0, card_x1, card_y1 = card_spec["box"]

        # Create card overlay layer for premium glassmorphism
        card_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        
        # Choose card fill and border color based on slide type
        if slide_type == "cta":
            card_fill = (12, 12, 20, 215)  # Slightly higher opacity for final slide contrast
            card_border = (key_color[0], key_color[1], key_color[2], 90)  # Subtle themed highlight border
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

        # A user-inserted photo, when present, fills the top of the card and the
        # copy shrinks and moves underneath it. Without one the layout is
        # unchanged: badge at the top of the card, copy centered in the body.
        photo_path = resolve_user_photo(slide, photo_dir)
        has_photo = photo_path is not None

        # --- Build the text lines first: the photo gets whatever vertical room
        #     the copy leaves over, so long copy is never squeezed out.
        # Type scale for cards 2..N. These are deliberately smaller than the
        # cover: the cover has one short hook, while these cards carry several
        # sentences, so smaller copy leaves more breathing room inside the card.
        if slide_type == "cta":
            badge_text = "THANK YOU"
            content_font_bold = get_system_font(
                card_spec["cta_photo"] if has_photo else card_spec["cta"], bold=True)
            line_height = card_spec["cta_line_photo"] if has_photo else card_spec["cta_line"]
            main_text = slide.get("main_text", "")
            main_text, _ = strip_highlight_markers(main_text)
            main_text = remove_emojis(main_text)
            main_text = break_after_commas(main_text)
            render_lines = [(line, content_font_bold, key_color)
                            for line in wrap_text(main_text, content_font_bold, card_spec["wrap"])]
        else:
            badge_text = f"KEY POINT 0{page_num - 1}" if page_num < 10 else f"KEY POINT {page_num - 1}"
            body_size = card_spec["body_photo"] if has_photo else card_spec["body"]
            content_font = get_system_font(body_size)
            content_font_bold = get_system_font(body_size, bold=True)
            line_height = card_spec["line_photo"] if has_photo else card_spec["line"]
            main_text = slide.get("main_text", "")
            main_text = remove_emojis(main_text)
            main_text = format_korean_line_breaks(main_text)
            main_text = break_after_commas(main_text)

            # Visual hierarchy for a clean, premium look:
            #  - Header line (e.g. "1. 소제목")  -> bold, near-white
            #  - Emphasized sentence (**...**)   -> bold, theme key color (the one pop of color)
            #  - Body text                        -> regular, light gray
            header_color = (250, 250, 252, 255)
            body_color = (226, 228, 234, 255)

            render_lines = []  # (text, font, color) after width-wrapping
            for logical in main_text.split("\n"):
                if not logical.strip():
                    continue
                clean, has_highlight = strip_highlight_markers(logical)
                cleaned = clean.strip()
                is_header = bool(
                    re.match(r'^\d+[\.\)]', cleaned)
                    or re.match(r'^\d+단계', cleaned)
                    or cleaned.startswith(("첫째", "둘째", "셋째", "넷째", "다섯째",
                                            "여섯째", "일곱째", "여덟째", "마지막"))
                )
                if is_header:
                    line_font, line_color = content_font_bold, header_color
                elif has_highlight:
                    line_font, line_color = content_font_bold, key_color
                else:
                    line_font, line_color = content_font, body_color

                for sub in wrap_text(clean, line_font, card_spec["wrap"]):
                    render_lines.append((sub, line_font, line_color))

        # --- Place the photo, then the badge row, then the copy ---
        BADGE_H = card_spec["badge_h"]
        badge_top = card_spec["badge_top"]   # default badge row, just inside the card top
        text_top = card_spec["text_top"]     # default copy start

        if has_photo:
            # Reserve badge row + gap + copy + bottom padding; the photo takes the rest.
            text_block = BADGE_H + 35 + len(render_lines) * line_height + 30
            photo_h = max(card_spec["photo_min"],
                          min((card_y1 - card_y0) - text_block, card_spec["photo_max"]))
            paste_slide_photo(image, photo_path, card_x0, card_y0, card_x1, photo_h)
            draw = ImageDraw.Draw(image)
            badge_top = card_y0 + photo_h + 30
            text_top = badge_top + BADGE_H + 35

        # Draw the badge pill (centered)
        badge_font = get_system_font(22, bold=True)
        if hasattr(badge_font, "getbbox"):
            bbox = badge_font.getbbox(badge_text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            text_w = len(badge_text) * 11
            text_h = 22
        box_w = text_w + 60
        x0 = (W - box_w) // 2
        x1 = x0 + box_w
        y0, y1 = badge_top, badge_top + BADGE_H

        draw.rounded_rectangle([x0, y0, x1, y1], radius=15, fill=key_color)
        text_x = x0 + (box_w - text_w) // 2
        text_y = y0 + (y1 - y0 - text_h) // 2 - 2
        draw.text((text_x, text_y), badge_text, fill=(255, 255, 255, 255), font=badge_font)

        # Center the copy in the remaining card body, compressing line height if
        # there are many lines so the text never overflows the card.
        card_content_height = card_y1 - text_top
        if render_lines and len(render_lines) * line_height > card_content_height:
            min_line = card_spec["min_line_photo"] if has_photo else card_spec["min_line"]
            line_height = max(min_line, card_content_height // len(render_lines))

        total_text_height = len(render_lines) * line_height
        y_cursor = text_top + max(0, (card_content_height - total_text_height) // 2)

        for text, line_font, line_color in render_lines:
            w = _text_width(line_font, text)
            x_pos = (W - w) // 2
            draw_text_safe(draw, (x_pos, y_cursor), text, fill=line_color, font=line_font)
            y_cursor += line_height


    # Apply logo watermark to the top-left corner (outside the card)
    draw_logo_watermark(image, pos=spec["watermark_pos"], target_width=spec["watermark_width"])

    return image

def generate_carousel_images(plan: dict, output_dir: str, reuse_background: bool = False, article_title: str = None,
                             allow_paid_background: bool = True, canvas: str = DEFAULT_CANVAS,
                             filename_prefix: str = "slide", for_video: bool = False) -> list:
    """
    Generates all slide images based on the plan and saves them to output_dir.
    Returns a list of generated file paths.

    `canvas` selects the card shape ("portrait" for the 4:5 Instagram carousel,
    "landscape" for 16:9 YouTube frames) and `filename_prefix` keeps the sets
    side by side in the same post folder. `for_video` renders the video wording
    of the cover instead of the carousel's swipe prompt.
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
    
    master_bg_path = os.path.join(output_dir, "background_master.png")
    bg_image = None
    
    if reuse_background and os.path.exists(master_bg_path):
        print(f"Reusing existing background master image: {master_bg_path}")
        try:
            bg_image = Image.open(master_bg_path)
            bg_image.load()
            # The master is stored at the portrait size, so re-cover it for
            # whichever canvas is being drawn (a no-op for portrait itself).
            if bg_image.size != (canvas_w, canvas_h):
                bg_image = resize_to_cover(bg_image, canvas_w, canvas_h)
        except Exception as e:
            print(f"Failed to load existing master background: {e}. Generating new one.")
            bg_image = None
            
    if bg_image is None and not allow_paid_background:
        # Editing an existing post (photo added/removed): never spend money on a
        # new background. Missing master -> the theme gradient fallback is used.
        print("No background master available; falling back to the theme gradient (no API call).")

    if bg_image is None and allow_paid_background:
        # Generate DALL-E master background using the detailed image_prompt
        raw_bg = generate_dalle_background(image_prompt)
        if raw_bg is not None:
            # Always archive the master at the portrait size so a later
            # landscape render can re-cover it without paying for a new image.
            bg_image = resize_to_cover(raw_bg, WIDTH, HEIGHT)
            try:
                bg_image.save(master_bg_path, "PNG")
                print(f"Saved background master image to: {master_bg_path}")
            except Exception as e:
                print(f"Failed to save background master image: {e}")
            if (canvas_w, canvas_h) != (WIDTH, HEIGHT):
                bg_image = resize_to_cover(raw_bg, canvas_w, canvas_h)

    image_paths = []
    for slide in slides:
        page_num = slide.get("page", 1)
        img = draw_card_layout(slide, total_pages, hooking_title, bg_image, article_title=article_title,
                               theme=theme, photo_dir=output_dir, canvas=canvas, for_video=for_video)

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
