import os
import glob
import shutil
import tempfile
import subprocess
from PIL import Image, ImageFilter, ImageEnhance
import imageio_ffmpeg

# Instagram Reels: 9:16 full-screen vertical video
REEL_W, REEL_H = 1080, 1920
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

    dur = max(0.2, float(seconds_per_card))
    fade = max(0.0, float(fade_seconds))

    # Compose each 9:16 frame to a temp JPG one at a time (tiny peak memory),
    # then let ffmpeg read the files and do all the encoding itself. This keeps
    # Python's memory footprint minimal, which matters on small hosts (Render
    # free tier = 512MB) where streaming hundreds of raw frames can OOM/crash.
    tmp_dir = tempfile.mkdtemp(prefix="reel_frames_")
    try:
        frame_files = []
        for i, p in enumerate(paths):
            frame = _compose_frame(p)
            fp = os.path.join(tmp_dir, f"frame_{i:03d}.jpg")
            frame.save(fp, "JPEG", quality=92)
            frame.close()
            frame_files.append(fp)

        n = len(frame_files)

        cmd = [ffmpeg, "-y"]
        for fp in frame_files:
            cmd += ["-loop", "1", "-t", f"{dur}", "-i", fp]

        # Normalize every input, then either cross-fade or hard-cut between them.
        parts = [f"[{i}:v]format=yuv420p,setsar=1[v{i}]" for i in range(n)]
        if n == 1:
            parts.append("[v0]copy[vout]")
        elif fade <= 0:
            labels = "".join(f"[v{i}]" for i in range(n))
            parts.append(f"{labels}concat=n={n}:v=1:a=0[vout]")
        else:
            step = dur - fade  # solo time each card gets before the next fade
            prev = "[v0]"
            for i in range(1, n):
                offset = round(i * step, 3)
                out_label = "[vout]" if i == n - 1 else f"[vc{i}]"
                parts.append(
                    f"{prev}[v{i}]xfade=transition=fade:duration={fade}:offset={offset}{out_label}"
                )
                prev = out_label
        filter_complex = ";".join(parts)

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-r", str(FPS),
            "-c:v", "libx264",
            "-preset", "veryfast",
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

    print(f"Reel video created at: {out_path}")
    return out_path


if __name__ == "__main__":
    # Quick self-test against whatever slides exist in ./test_output
    test_dir = "./test_output"
    out = create_reel_video([], test_dir)
    print("Test reel:", out, "-", os.path.getsize(out), "bytes")
