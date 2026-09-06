"""Entry point for the per-clip render process.

Kept free of app.jobs so a spawned child does not construct a JobManager or
start a worker thread of its own when it imports this module.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.config import config
from app.models import FormatId, QualityId, VisualSettings
from app.render import RenderError, render_clip


def default_workers() -> int:
    """Clips rendered at once. RENDER_WORKERS (config.render_workers) overrides;
    otherwise half the cores, clamped to 1..4."""
    if config.render_workers > 0:
        return int(config.render_workers)
    cores = os.cpu_count() or 2
    return max(1, min(4, cores // 2))


def render_clip_process(
    idx: int,
    wav_path: Path,
    out_path: Path,
    start: float,
    end: float,
    settings: VisualSettings,
    fade_in: float,
    fade_out: float,
    fmt: FormatId,
    quality: QualityId,
    fps: int,
    queue,
    cancel,
) -> None:
    """Render one clip and report over `queue`:
    ("progress", idx, fraction, message) / ("done", idx, bytes) /
    ("cancelled", idx, reason) / ("error", idx, reason)."""
    logging.basicConfig(level=logging.WARNING)

    def on_progress(p: float, msg: str) -> None:
        queue.put(("progress", idx, float(p), msg))

    try:
        info = render_clip(
            wav_path=wav_path,
            out_path=out_path,
            start=start,
            end=end,
            settings=settings,
            on_progress=on_progress,
            should_cancel=cancel.is_set,
            fade_in=fade_in,
            fade_out=fade_out,
            fmt=fmt,
            quality=quality,
            fps=fps,
        )
        queue.put(("done", idx, int(info["bytes"])))
    except RenderError as exc:
        Path(out_path).unlink(missing_ok=True)
        queue.put(("cancelled" if cancel.is_set() else "error", idx, str(exc)))
    except Exception as exc:  # noqa: BLE001 - report anything to the parent
        Path(out_path).unlink(missing_ok=True)
        queue.put(("error", idx, f"{type(exc).__name__}: {exc}"))
