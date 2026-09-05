from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.config import config

log = logging.getLogger("noiseviz.storage")


def _newest_mtime(folder: Path) -> float:
    newest = folder.stat().st_mtime
    for child in folder.iterdir():
        try:
            newest = max(newest, child.stat().st_mtime)
        except OSError:
            continue
    return newest


def prune_old(retention_days: int | None = None, now: float | None = None) -> list[Path]:
    """Delete track and job folders untouched for longer than the retention window.

    Returns the removed paths. ``retention_days <= 0`` disables pruning.
    """
    days = config.retention_days if retention_days is None else retention_days
    if days <= 0:
        return []
    cutoff = (now if now is not None else time.time()) - days * 86400
    removed: list[Path] = []
    for root in (config.tracks_dir, config.jobs_dir):
        if not root.is_dir():
            continue
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            try:
                if _newest_mtime(folder) < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
                    removed.append(folder)
            except OSError as exc:
                log.warning("prune skipped %s: %s", folder, exc)
    if removed:
        log.info("pruned %d folder(s) older than %d days", len(removed), days)
    return removed
