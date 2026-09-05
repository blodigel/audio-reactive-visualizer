from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.config import config

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_EDGE = 2560


class BackgroundError(ValueError):
    pass


def cover_fit(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    iw, ih = image.size
    if iw < 1 or ih < 1:
        raise BackgroundError("Image has no pixels")
    scale = max(width / iw, height / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def save_upload(src: Path, dest: Path) -> None:
    try:
        with Image.open(src) as raw:
            raw.load()
            image = raw.convert("RGB")
    except Exception as exc:
        raise BackgroundError(f"Could not read image: {exc}") from exc
    if max(image.size) > MAX_EDGE:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)


def load_cover(background_id: str | None, width: int, height: int) -> np.ndarray | None:
    if not background_id:
        return None
    path = config.backgrounds_dir / f"{background_id}.png"
    if not path.is_file():
        return None
    with Image.open(path) as raw:
        fitted = cover_fit(raw, width, height)
    arr = np.asarray(fitted, dtype=np.float32) / 255.0
    return arr
