import os
import glob
import shutil
import tempfile
import subprocess
from PIL import Image, ImageFilter, ImageEnhance
import imageio_ffmpeg

# Two output shapes from the same cards:
#   vertical   -> 9:16 Instagram Reels
#   horizontal -> 16:9 YouTube
# 720p-class frames (same pixel count either way) keep the libx264 encoder's
# memory low enough to run on small hosts (Render free tier = 512MB).
PRESETS = {
    # `seconds` is how long each card is held. `first_seconds` (optional) gives
    # the cover its own pace: it carries one short hook, so it needs less time on
    # screen than the cards of copy that follow. Without it the cover uses
    # `seconds` like every other card.
    "vertical":   {"size": (720, 1280), "filename": "reel.mp4",      "label": "9:16",
                   "seconds": 2.0, "first_seconds": 1.4},
    "horizontal": {"size": (1280, 720), "filename": "reel_wide.mp4", "label": "16:9",
                   "seconds": 2.0},
    # Shorts cut of a one-card post: the card is redrawn on a native 9:16 canvas
    # (see the "story" canvas), so it fills the frame with no blurred bands, and
    # it holds for the three seconds a Shorts clip needs.
    "shorts":     {"size": (720, 1280), "filename": "shorts.mp4",   "label": "9:16 쇼츠",
                   "seconds": 3.0, "first_seconds": 3.0},
}
FPS = 30


def _resize_cover(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resizes and center-crops an image to completely cover the target size."""
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.ANTIALIAS

    iw, ih = image.size
    target_ratio = target_w / target_h
    img_ratio = iw / ih
    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(iw * (target_h / ih))
    else:
        new_w = target_w
        new_h = int(ih * (target_w / iw))
    resized = image.resize((new_w, new_h), resample)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _compose_frame(card_path: str, frame_w: int, frame_h: int) -> Image.Image:
    """
    Composes one video frame from a 4:5 card image:
      - a blurred, darkened copy of the card fills the whole canvas
      - the sharp card is scaled to *fit inside* the frame and centered, so no
        part of the card is ever cropped. A 9:16 frame leaves blurred bands
        above and below the card; a 16:9 frame leaves them left and right.
    """
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.ANTIALIAS

    card = Image.open(card_path).convert("RGB")

    # Blurred background fills the letterbox/pillarbox area behind the card.
    # Blur on a downscaled copy (cheap) then upscale — visually identical to a
    # heavy full-res blur but far faster.
    small = _resize_cover(card, frame_w // 4, frame_h // 4).filter(ImageFilter.GaussianBlur(12))
    bg = small.resize((frame_w, frame_h), resample)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)

    # Sharp card scaled by whichever axis runs out first, then centered.
    cw, ch = card.size
    scale = min(frame_w / cw, frame_h / ch)
    new_w = max(1, int(cw * scale))
    new_h = max(1, int(ch * scale))
    card_resized = card.resize((new_w, new_h), resample)
    bg.paste(card_resized, ((frame_w - new_w) // 2, (frame_h - new_h) // 2))
    return bg


def _slide_frame(current: Image.Image, nxt: Image.Image, offset: int) -> Image.Image:
    """
    One frame of the swipe transition: `current` has slid `offset` pixels off the
    left edge and `nxt` follows it in from the right, so the pair moves as a
    single strip — the same feel as swiping a carousel.
    """
    frame_w, frame_h = current.size
    frame = Image.new("RGB", (frame_w, frame_h))
    frame.paste(current, (-offset, 0))
    frame.paste(nxt, (frame_w - offset, 0))
    return frame


def create_reel_video(image_paths: list, output_dir: str,
                      seconds_per_card: float = None, transition_seconds: float = 0.25,
                      orientation: str = "vertical", first_card_seconds: float = None) -> str:
    """
    Stitches the given card images into an H.264/yuv420p MP4 where each card
    slides in from the right as the previous one slides off to the left.
    `orientation` picks the shape: "vertical" for a 9:16 Instagram Reel,
    "horizontal" for a 16:9 YouTube video. Each card occupies
    `seconds_per_card` (defaulting to the orientation's own pace) with the first
    card using `first_card_seconds`, and the swipe between two cards takes
    `transition_seconds`. Returns the output file path.
    """
    preset = PRESETS.get(orientation)
    if preset is None:
        raise ValueError(f"알 수 없는 영상 비율입니다: {orientation}")
    frame_w, frame_h = preset["size"]
    if seconds_per_card is None:
        seconds_per_card = preset["seconds"]
    if first_card_seconds is None:
        first_card_seconds = preset.get("first_seconds", seconds_per_card)

    os.makedirs(output_dir, exist_ok=True)

    # Prefer the explicit list, but fall back to the slides on disk for robustness.
    paths = [p for p in (image_paths or []) if p and os.path.exists(p)]
    if not paths:
        paths = sorted(glob.glob(os.path.join(output_dir, "slide_*.jpg")))
    if not paths:
        raise ValueError("영상으로 만들 카드 이미지를 찾을 수 없습니다.")

    out_path = os.path.join(output_dir, preset["filename"])
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    per = max(0.2, float(seconds_per_card))
    first = max(0.2, float(first_card_seconds))
    slide = max(0.0, float(transition_seconds))
    n = len(paths)
    slide_count = int(round(slide * FPS)) if slide > 0 else 0

    # Pre-render EVERY frame (holds + swipe steps) to disk one at a time,
    # then let ffmpeg's concat demuxer read the images sequentially. Both Python
    # and ffmpeg only ever hold a frame or two in memory, which is essential on
    # small hosts (Render free tier = 512MB) where the xfade filter graph would
    # buffer too many full-size frames and get OOM-killed.
    print(f"[reel] composing frames for {n} cards ({preset['label']})...", flush=True)
    tmp_dir = tempfile.mkdtemp(prefix="reel_frames_")
    try:
        entries = []  # (absolute_path, duration_seconds)
        counter = {"i": 0}

        def write_img(img):
            fp = os.path.join(tmp_dir, f"f{counter['i']:05d}.jpg")
            img.save(fp, "JPEG", quality=90)
            counter["i"] += 1
            return fp

        current = _compose_frame(paths[0], frame_w, frame_h)
        for i in range(n):
            is_last = (i == n - 1)
            # Each non-final card holds still, then spends `slide` seconds
            # swiping away, so it occupies its full slot overall; the final card
            # simply holds.
            slot = first if i == 0 else per
            hold = slot if is_last else max(0.05, slot - slide)
            entries.append((write_img(current), hold))

            if not is_last:
                nxt = _compose_frame(paths[i + 1], frame_w, frame_h)
                for k in range(1, slide_count + 1):
                    # Smoothstep easing: the swipe starts and ends gently instead
                    # of jerking at a constant speed.
                    t = k / (slide_count + 1)
                    eased = t * t * (3 - 2 * t)
                    entries.append((write_img(_slide_frame(current, nxt, int(frame_w * eased))),
                                    1.0 / FPS))
                current.close()
                current = nxt
        current.close()

        # Build the concat demuxer playlist (durations control timing).
        list_path = os.path.join(tmp_dir, "list.txt")
        with open(list_path, "w") as lf:
            lf.write("ffconcat version 1.0\n")
            for fp, d in entries:
                lf.write(f"file '{fp}'\n")
                lf.write(f"duration {d:.4f}\n")
            # The concat demuxer ignores the final entry's duration unless the
            # last image is listed once more.
            lf.write(f"file '{entries[-1][0]}'\n")

        print(f"[reel] {len(entries)} frames ready. Encoding with ffmpeg...", flush=True)
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-r", str(FPS),
            "-c:v", "libx264",
            "-preset", "ultrafast",  # lowest encoder memory footprint
            "-threads", "1",          # avoid per-thread buffer duplication
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(out_path):
            tail = (proc.stderr or "")[-1500:]
            raise RuntimeError(f"ffmpeg 인코딩 실패 (code {proc.returncode}): {tail}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"[reel] created: {out_path}", flush=True)
    return out_path


if __name__ == "__main__":
    # Quick self-test against whatever slides exist in ./test_output
    test_dir = "./test_output"
    for orient in PRESETS:
        out = create_reel_video([], test_dir, orientation=orient)
        print(f"Test {orient}:", out, "-", os.path.getsize(out), "bytes")
