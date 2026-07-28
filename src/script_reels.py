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
    # `seconds` is how long each card is held. 2.5s was too quick to finish
    # reading a card of Korean copy; YouTube gets a longer hold still, since
    # viewers watch it rather than swiping past.
    "vertical":   {"size": (720, 1280), "filename": "reel.mp4",      "label": "9:16", "seconds": 4.5},
    "horizontal": {"size": (1280, 720), "filename": "reel_wide.mp4", "label": "16:9", "seconds": 7.0},
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


def create_reel_video(image_paths: list, output_dir: str,
                      seconds_per_card: float = None, fade_seconds: float = 0.5,
                      orientation: str = "vertical") -> str:
    """
    Stitches the given card images into an H.264/yuv420p MP4 with a smooth
    cross-fade between cards. `orientation` picks the shape: "vertical" for a
    9:16 Instagram Reel, "horizontal" for a 16:9 YouTube video. Each card is
    held for `seconds_per_card` (defaulting to the orientation's own pace), and
    consecutive cards blend over `fade_seconds`. Returns the output file path.
    """
    preset = PRESETS.get(orientation)
    if preset is None:
        raise ValueError(f"알 수 없는 영상 비율입니다: {orientation}")
    frame_w, frame_h = preset["size"]
    if seconds_per_card is None:
        seconds_per_card = preset["seconds"]

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
    fade = max(0.0, float(fade_seconds))
    n = len(paths)
    blend_count = int(round(fade * FPS)) if fade > 0 else 0

    # Pre-render EVERY frame (holds + cross-fade blends) to disk one at a time,
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
            # Each non-final card holds for (per - fade) then blends for `fade`,
            # so it occupies ~`per` seconds overall; the final card holds `per`.
            hold = per if is_last else max(0.05, per - fade)
            entries.append((write_img(current), hold))

            if not is_last:
                nxt = _compose_frame(paths[i + 1], frame_w, frame_h)
                for k in range(1, blend_count + 1):
                    alpha = k / (blend_count + 1)
                    entries.append((write_img(Image.blend(current, nxt, alpha)), 1.0 / FPS))
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
