from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.audio import load_wav, spectral_features, mono
from app.config import config
from app.models import FormatId, QualityId, VisualSettings
from app.backgrounds import load_cover
from app.logos import load_logo
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


def _stop(proc: subprocess.Popen) -> None:
    """Kill ffmpeg and reap it so a cancelled render leaves no zombie."""
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def clamp_fades(duration: float, fade_in: float, fade_out: float) -> tuple[float, float]:
    duration = max(0.0, float(duration))
    fade_in = float(np.clip(fade_in, 0.0, duration))
    fade_out = float(np.clip(fade_out, 0.0, duration))
    return fade_in, fade_out


def fade_gain(t: float, duration: float, fade_in: float, fade_out: float) -> float:
    """0–1 envelope: fade in at start, fade out at end, independent (may overlap)."""
    if duration <= 0:
        return 0.0
    g = 1.0
    fade_in, fade_out = clamp_fades(duration, fade_in, fade_out)
    if fade_in > 1e-4 and t < fade_in:
        g *= max(0.0, t / fade_in)
    remaining = duration - t
    if fade_out > 1e-4 and remaining < fade_out:
        g *= max(0.0, remaining / fade_out)
    return float(np.clip(g, 0.0, 1.0))


def render_clip(
    wav_path: Path,
    out_path: Path,
    start: float,
    end: float,
    settings: VisualSettings,
    on_progress: ProgressFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fmt: FormatId = "reels",
    quality: QualityId = "standard",
    fps: int = 30,
) -> dict:
    data, sr = load_wav(wav_path)
    duration = max(0.5, end - start)
    track_dur = data.shape[0] / sr
    if start >= track_dur:
        raise RenderError("Clip start is past the end of the track")
    end = min(end, track_dur)
    duration = end - start
    fps = int(fps)
    w, h = output_size(fmt, quality)
    spec = spectral_features(mono(data), sr, fps=fps)
    bg = load_cover(settings.background_id, w, h)
    logo = load_logo(settings.logo_id)
    engine = VisualEngine(data, sr, spec, settings, w, h, start, background=bg, logo=logo)
    n_frames = max(1, int(round(duration * fps)))
    fade_in, fade_out = clamp_fades(duration, fade_in, fade_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg_bin()
    crf = QUALITY_CRF.get(quality, 19)
    preset = QUALITY_PRESET.get(quality, "veryfast")
    af = []
    if fade_in > 1e-4:
        af.append(f"afade=t=in:st=0:d={fade_in:.4f}")
    if fade_out > 1e-4:
        af.append(f"afade=t=out:st={max(0.0, duration - fade_out):.4f}:d={fade_out:.4f}")
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
    ]
    if af:
        cmd.extend(["-af", ",".join(af)])
    cmd.append(str(out_path))
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
                _stop(proc)
                raise RenderError("Cancelled")
            frame = engine.render_frame(i, fps)
            if frame.shape != (h, w, 3):
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
            if fade_in > 1e-4 or fade_out > 1e-4:
                t = i / float(fps)
                g = fade_gain(t, duration, fade_in, fade_out)
                if g < 0.999:
                    frame = np.clip(frame.astype(np.float32) * g, 0, 255).astype(np.uint8)
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            if on_progress and (i % 5 == 0 or i == n_frames - 1):
                on_progress((i + 1) / n_frames, f"frame {i + 1}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError as exc:
        _stop(proc)
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
        _stop(proc)
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
