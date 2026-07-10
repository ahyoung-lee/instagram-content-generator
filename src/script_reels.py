import os
import glob
import shutil
import tempfile
import subprocess
from PIL import Image, ImageFilter, ImageEnhance
import imageio_ffmpeg

# Instagram Reels: 9:16 full-screen vertical video.
# 720x1280 (still a valid, Instagram-accepted Reels size) keeps the libx264
# encoder's memory low enough to run on small hosts (Render free tier = 512MB).
REEL_W, REEL_H = 720, 1280
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


def _compose_frame(card_path: str) -> Image.Image:
    """
    Composes one 9:16 Reels frame from a 4:5 card image:
      - a blurred, darkened copy of the card fills the full 1080x1920 canvas
      - the sharp card is fitted to the full width and centered vertically
    """
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.ANTIALIAS

    card = Image.open(card_path).convert("RGB")

    # Blurred background fills the vertical letterbox area behind the card.
    # Blur on a downscaled copy (cheap) then upscale — visually identical to a
    # heavy full-res blur but far faster.
    small = _resize_cover(card, REEL_W // 4, REEL_H // 4).filter(ImageFilter.GaussianBlur(12))
    bg = small.resize((REEL_W, REEL_H), resample)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)

    # Sharp card fitted to the full frame width, centered vertically.
    cw, ch = card.size
    new_w = REEL_W
    new_h = int(ch * (REEL_W / cw))
    if new_h > REEL_H:  # extremely tall card safety
        new_h = REEL_H
        new_w = int(cw * (REEL_H / ch))
    card_resized = card.resize((new_w, new_h), resample)
    x = (REEL_W - new_w) // 2
    y = (REEL_H - new_h) // 2
    bg.paste(card_resized, (x, y))
    return bg


def create_reel_video(image_paths: list, output_dir: str,
                      seconds_per_card: float = 2.5, fade_seconds: float = 0.5) -> str:
    """
    Stitches the given card images into an Instagram-Reels-ready MP4
    (1080x1920, H.264/yuv420p) with a smooth cross-fade between cards.
    Each card is held for `seconds_per_card`, and consecutive cards blend
    over `fade_seconds`. Returns the output file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Prefer the explicit list, but fall back to the slides on disk for robustness.
    paths = [p for p in (image_paths or []) if p and os.path.exists(p)]
    if not paths:
        paths = sorted(glob.glob(os.path.join(output_dir, "slide_*.jpg")))
    if not paths:
        raise ValueError("릴스로 만들 카드 이미지를 찾을 수 없습니다.")

    out_path = os.path.join(output_dir, "reel.mp4")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    per = max(0.2, float(seconds_per_card))
    fade = max(0.0, float(fade_seconds))
    n = len(paths)
    blend_count = int(round(fade * FPS)) if fade > 0 else 0

    # Pre-render EVERY frame (holds + cross-fade blends) to disk one at a time,
    # then let ffmpeg's concat demuxer read the images sequentially. Both Python
    # and ffmpeg only ever hold a frame or two in memory, which is essential on
    # small hosts (Render free tier = 512MB) where the xfade filter graph would
    # buffer too many 1080x1920 frames and get OOM-killed.
    print(f"[reel] composing frames for {n} cards (9:16)...", flush=True)
    tmp_dir = tempfile.mkdtemp(prefix="reel_frames_")
    try:
        entries = []  # (absolute_path, duration_seconds)
        counter = {"i": 0}

        def write_img(img):
            fp = os.path.join(tmp_dir, f"f{counter['i']:05d}.jpg")
            img.save(fp, "JPEG", quality=90)
            counter["i"] += 1
            return fp

        current = _compose_frame(paths[0])
        for i in range(n):
            is_last = (i == n - 1)
            # Each non-final card holds for (per - fade) then blends for `fade`,
            # so it occupies ~`per` seconds overall; the final card holds `per`.
            hold = per if is_last else max(0.05, per - fade)
            entries.append((write_img(current), hold))

            if not is_last:
                nxt = _compose_frame(paths[i + 1])
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
    out = create_reel_video([], test_dir)
    print("Test reel:", out, "-", os.path.getsize(out), "bytes")
