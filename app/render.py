from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from app.audio import load_wav, spectral_features, mono
from app.config import config
from app.models import VisualSettings
from app.backgrounds import load_cover
from app.presets import QUALITY_CRF, QUALITY_PRESET, output_size
from app.viz import VisualEngine

log = logging.getLogger("noiseviz.render")

ProgressFn = Callable[[float, str], None]


class RenderError(RuntimeError):
    pass


def _ffmpeg_bin() -> str:
    path = shutil.which(config.ffmpeg) or shutil.which("ffmpeg")
    if not path:
        raise RenderError("ffmpeg not found on PATH. Install ffmpeg or set FFMPEG=/path/to/ffmpeg")
    return path


def render_clip(
    wav_path: Path,
    out_path: Path,
    start: float,
    end: float,
    settings: VisualSettings,
    on_progress: ProgressFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    data, sr = load_wav(wav_path)
    duration = max(0.5, end - start)
    track_dur = data.shape[0] / sr
    if start >= track_dur:
        raise RenderError("Clip start is past the end of the track")
    end = min(end, track_dur)
    duration = end - start
    fps = int(settings.fps)
    w, h = output_size(settings.format, settings.quality)
    spec = spectral_features(mono(data), sr, fps=fps)
    bg = load_cover(settings.background_id, w, h)
    engine = VisualEngine(data, sr, spec, settings, w, h, start, background=bg)
    n_frames = max(1, int(round(duration * fps)))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg_bin()
    crf = QUALITY_CRF.get(settings.quality, 19)
    preset = QUALITY_PRESET.get(settings.quality, "veryfast")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-ss",
        f"{start:.4f}",
        "-t",
        f"{duration:.4f}",
        "-i",
        str(wav_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-tune",
        "grain",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    log.info("ffmpeg %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    err_chunks: list[bytes] = []

    def _drain() -> None:
        assert proc.stderr is not None
        while True:
            chunk = proc.stderr.read(4096)
            if not chunk:
                break
            err_chunks.append(chunk)

    drainer = threading.Thread(target=_drain, daemon=True)
    drainer.start()

    assert proc.stdin is not None
    try:
        for i in range(n_frames):
            if should_cancel and should_cancel():
                proc.kill()
                raise RenderError("Cancelled")
            frame = engine.render_frame(i, fps)
            if frame.shape != (h, w, 3):
                frame = np.resize(frame, (h, w, 3))
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            if on_progress and (i % 5 == 0 or i == n_frames - 1):
                on_progress((i + 1) / n_frames, f"frame {i + 1}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError as exc:
        proc.kill()
        drainer.join(timeout=2)
        err = b"".join(err_chunks).decode("utf-8", "replace")
        raise RenderError(f"ffmpeg pipe broke: {err or exc}") from exc
    except RenderError:
        try:
            proc.stdin.close()
        except Exception:
            pass
        raise
    except Exception:
        proc.kill()
        raise

    code = proc.wait(timeout=120)
    drainer.join(timeout=2)
    if code != 0:
        err = b"".join(err_chunks).decode("utf-8", "replace")
        raise RenderError(f"ffmpeg failed ({code}): {err[-2000:]}")
    if not out_path.is_file() or out_path.stat().st_size < 1000:
        raise RenderError("ffmpeg produced an empty file")
    return {
        "path": out_path,
        "width": w,
        "height": h,
        "frames": n_frames,
        "fps": fps,
        "bytes": out_path.stat().st_size,
    }
