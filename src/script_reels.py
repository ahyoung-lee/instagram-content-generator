import os
import glob
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

    composed = [_compose_frame(p) for p in paths]

    hold_frames = max(1, int(round(FPS * seconds_per_card)))
    fade_frames = max(0, int(round(FPS * fade_seconds)))

    out_path = os.path.join(output_dir, "reel.mp4")

    # imageio-ffmpeg streams raw RGB frames into a bundled ffmpeg encoder.
    writer = imageio_ffmpeg.write_frames(
        out_path,
        (REEL_W, REEL_H),
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        macro_block_size=1,  # keep exact 1080x1920 (both are even, valid for yuv420p)
        output_params=["-movflags", "+faststart", "-preset", "veryfast", "-crf", "23"],
    )
    writer.send(None)  # seed the generator

    try:
        n = len(composed)
        for i, frame in enumerate(composed):
            is_last = (i == n - 1)
            # Non-final cards give up some hold time to their outgoing fade so
            # each card occupies roughly `seconds_per_card` overall.
            this_hold = hold_frames if is_last else max(1, hold_frames - fade_frames)
            fb = frame.tobytes()
            for _ in range(this_hold):
                writer.send(fb)

            if not is_last and fade_frames > 0:
                nxt = composed[i + 1]
                for f in range(1, fade_frames + 1):
                    alpha = f / (fade_frames + 1)
                    writer.send(Image.blend(frame, nxt, alpha).tobytes())
    finally:
        writer.close()

    print(f"Reel video created at: {out_path}")
    return out_path


if __name__ == "__main__":
    # Quick self-test against whatever slides exist in ./test_output
    test_dir = "./test_output"
    out = create_reel_video([], test_dir)
    print("Test reel:", out, "-", os.path.getsize(out), "bytes")
