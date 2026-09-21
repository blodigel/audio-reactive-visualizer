from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.config import config

log = logging.getLogger("noiseviz")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_EXT = IMAGE_EXT | VIDEO_EXT
MAX_EDGE = 2560
MAX_VIDEO_SECONDS = 60


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


def _ffmpeg_bin() -> str:
    path = shutil.which(config.ffmpeg) or shutil.which("ffmpeg")
    if not path:
        raise BackgroundError("ffmpeg not found on PATH")
    return path


def _run_ffmpeg(cmd: list[str], dest: Path) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise BackgroundError("Video transcode timed out. Try a shorter file.") from exc
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 32:
        dest.unlink(missing_ok=True)
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        hint = err[-400:] if err else "unreadable file"
        raise BackgroundError(f"Could not read video ({hint})")


def media_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            proc = None
        if proc is not None and proc.returncode == 0:
            try:
                dur = float(proc.stdout.strip())
            except ValueError:
                dur = 0.0
            if dur > 0:
                return dur
    cap = cv2.VideoCapture(str(path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    finally:
        cap.release()
    if fps > 1 and n > 0:
        return n / fps
    return 0.0


def save_video(src: Path, dest_mp4: Path, poster: Path) -> float:
    """Transcode to a muted H.264 that loops cleanly, plus a still of the first frame."""
    dest_mp4.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()
    _run_ffmpeg(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-an",
            "-t",
            str(MAX_VIDEO_SECONDS),
            "-vf",
            "scale='min(1920,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease,"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            str(dest_mp4),
        ],
        dest_mp4,
    )
    try:
        _run_ffmpeg(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(dest_mp4),
                "-frames:v",
                "1",
                str(poster),
            ],
            poster,
        )
    except BackgroundError:
        dest_mp4.unlink(missing_ok=True)
        raise
    return media_duration(dest_mp4)


def meta_path(background_id: str) -> Path:
    return config.backgrounds_dir / f"{background_id}.json"


def write_meta(background_id: str, payload: dict) -> None:
    meta_path(background_id).write_text(json.dumps(payload))


def read_meta(background_id: str) -> dict | None:
    path = meta_path(background_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class StillSource:
    def __init__(self, arr: np.ndarray):
        self.arr = arr

    def frame(self, _t: float) -> np.ndarray:
        return self.arr

    def close(self) -> None:
        return None


def _cover_bgr(bgr: np.ndarray, width: int, height: int) -> np.ndarray:
    ih, iw = bgr.shape[:2]
    if iw < 1 or ih < 1:
        return np.zeros((height, width, 3), dtype=np.float32)
    scale = max(width / iw, height / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(bgr, (nw, nh), interpolation=interp)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    crop = resized[top : top + height, left : left + width]
    if crop.shape[0] != height or crop.shape[1] != width:
        crop = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return rgb.astype(np.float32) / 255.0


class VideoSource:
    """Cover-cropped frames from a transcoded background. Time loops from the clip start."""

    def __init__(self, path: Path, width: int, height: int):
        self.path = path
        self.w = width
        self.h = height
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise BackgroundError(f"Could not open video {path.name}")
        fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = fps if fps > 1 else 30.0
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._idx = -1
        self._cached: np.ndarray | None = None

    def frame(self, t: float) -> np.ndarray:
        if self.cap is None or self.n <= 0:
            return self._blank()
        dur = self.n / self.fps
        tt = float(t) % dur if dur > 0 else 0.0
        idx = min(self.n - 1, max(0, int(tt * self.fps)))
        if idx == self._idx and self._cached is not None:
            return self._cached
        got = self._read_at(idx)
        if got is None:
            return self._cached if self._cached is not None else self._blank()
        self._cached = got
        return got

    def _blank(self) -> np.ndarray:
        return np.zeros((self.h, self.w, 3), dtype=np.float32)

    def _read_at(self, idx: int) -> np.ndarray | None:
        if self.cap is None:
            return None
        bgr = None
        if self._idx >= 0 and 0 < idx - self._idx <= 5:
            while self._idx < idx:
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    bgr = None
                    break
                bgr = frame
                self._idx += 1
            if bgr is not None and self._idx == idx:
                return _cover_bgr(bgr, self.w, self.h)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, bgr = self.cap.read()
        self._idx = idx
        if not ok or bgr is None:
            return None
        return _cover_bgr(bgr, self.w, self.h)

    def close(self) -> None:
        cap = self.cap
        self.cap = None
        if cap is not None:
            cap.release()


def background_kind(background_id: str) -> str:
    meta = read_meta(background_id) or {}
    kind = str(meta.get("kind") or "")
    if kind in {"image", "video"}:
        return kind
    if (config.backgrounds_dir / f"{background_id}.mp4").is_file():
        return "video"
    return "image"


def open_background(background_id: str | None, width: int, height: int) -> StillSource | VideoSource | None:
    if not background_id:
        return None
    if background_kind(background_id) == "video":
        path = config.backgrounds_dir / f"{background_id}.mp4"
        if path.is_file():
            try:
                return VideoSource(path, width, height)
            except BackgroundError as exc:
                log.warning("video background %s fell back to poster: %s", background_id, exc)
    arr = load_cover(background_id, width, height)
    if arr is None:
        return None
    return StillSource(arr)
