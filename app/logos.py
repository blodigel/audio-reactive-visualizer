from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.config import config

ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_EDGE = 1600


class LogoError(ValueError):
    pass


def save_logo(src: Path, dest: Path) -> None:
    try:
        with Image.open(src) as raw:
            raw.load()
            image = raw.convert("RGBA")
    except Exception as exc:
        raise LogoError(f"Could not read logo: {exc}") from exc
    if image.size[0] < 2 or image.size[1] < 2:
        raise LogoError("Logo has no pixels")
    if max(image.size) > MAX_EDGE:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)


def load_logo(logo_id: str | None) -> Image.Image | None:
    if not logo_id:
        return None
    path = config.logos_dir / f"{logo_id}.png"
    if not path.is_file():
        return None
    with Image.open(path) as raw:
        return raw.convert("RGBA")


def logo_xy(
    frame_w: int,
    frame_h: int,
    logo_w: int,
    logo_h: int,
    position: str,
    text_position: str,
) -> tuple[int, int]:
    mx = int(frame_w * 0.055)
    my = int(frame_h * 0.045)
    if position == "top-left":
        return mx, my
    if position == "top-right":
        return frame_w - logo_w - mx, my
    if position == "lower-left":
        return mx, frame_h - logo_h - my
    if position == "lower-right":
        return frame_w - logo_w - mx, frame_h - logo_h - my
    # above-text: centered, sitting just above the title block
    x = (frame_w - logo_w) // 2
    if text_position == "top":
        y = max(my, int(frame_h * 0.08) - logo_h - int(frame_h * 0.02))
    elif text_position == "center":
        y = max(my, int(frame_h * 0.40) - logo_h - int(frame_h * 0.025))
    else:
        y = max(my, int(frame_h * 0.68) - logo_h - int(frame_h * 0.025))
    y = min(y, frame_h - logo_h - my)
    return x, y


def apply_logo(
    img: np.ndarray,
    logo: Image.Image,
    position: str,
    size: float,
    opacity: float,
    text_position: str,
) -> None:
    h, w = img.shape[:2]
    size = float(np.clip(size, 0.06, 0.55))
    opacity = float(np.clip(opacity, 0.0, 1.0))
    if opacity <= 0.01:
        return
    target_w = max(12, int(w * size))
    iw, ih = logo.size
    if iw < 1 or ih < 1:
        return
    target_h = max(12, int(round(target_w * ih / iw)))
    if target_h > int(h * 0.42):
        target_h = int(h * 0.42)
        target_w = max(12, int(round(target_h * iw / ih)))
    fitted = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    x, y = logo_xy(w, h, target_w, target_h, position, text_position)
    arr = np.asarray(fitted, dtype=np.float32) / 255.0
    alpha = arr[:, :, 3:4] * opacity
    rgb = arr[:, :, :3]
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(w, x + target_w)
    y1 = min(h, y + target_h)
    if x1 <= x0 or y1 <= y0:
        return
    sx0 = x0 - x
    sy0 = y0 - y
    dest = img[y0:y1, x0:x1]
    a = alpha[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
    src = rgb[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
    dest *= 1.0 - a
    dest += src * a
