from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import config
from app.models import JobFileOut, JobOut, RenderRequest, VisualSettings
from app.render import RenderError, render_clip
from app.storage import prune_old

log = logging.getLogger("noiseviz.jobs")

JOB_FILE = "job.json"


def clip_output_name(index: int, settings: VisualSettings, track_filename: str) -> str:
    def slug(raw: str, limit: int = 48) -> str:
        cleaned = re.sub(r"[^\w\s.\-–—']+", "", raw or "", flags=re.UNICODE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned[:limit].strip()

    title = slug(settings.text)
    sub = slug(settings.subtext)
    if not title:
        stem = Path(track_filename or "clip").stem
        title = slug(stem) or "clip"
    parts = [title]
    if sub:
        parts.append(sub)
    parts.append(f"{index:02d}")
    name = " – ".join(parts) + ".mp4"
    return name or f"clip-{index:02d}.mp4"


def track_display_name(track_id: str) -> str:
    meta_path = config.tracks_dir / track_id / "meta.json"
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text()).get("filename") or ""
        except Exception:
            return ""
    return ""


@dataclass
class Job:
    id: str
    track_id: str
    wav_path: Path
    request: RenderRequest | None
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    error: str | None = None
    outputs: list[JobFileOut] = field(default_factory=list)
    cancel: bool = False
    created: float = field(default_factory=time.time)
    track_name: str = ""
    format: str = "reels"
    quality: str = "standard"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "track_id": self.track_id,
            "track_name": self.track_name,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "error": self.error,
            "created": self.created,
            "format": self.format,
            "quality": self.quality,
            "outputs": [o.model_dump() for o in self.outputs],
        }

    @classmethod
    def from_json(cls, data: dict) -> Job:
        job = cls(
            id=str(data["id"]),
            track_id=str(data.get("track_id", "")),
            wav_path=config.tracks_dir / str(data.get("track_id", "")) / "source.wav",
            request=None,
            status=str(data.get("status", "error")),
            progress=float(data.get("progress", 0.0)),
            message=str(data.get("message", "")),
            error=data.get("error"),
            created=float(data.get("created", 0.0)),
            track_name=str(data.get("track_name", "")),
            format=str(data.get("format", "reels")),
            quality=str(data.get("quality", "standard")),
        )
        job.outputs = [JobFileOut(**o) for o in data.get("outputs", [])]
        return job


class JobManager:
    """Single render worker. Job state is mirrored to data/jobs/<id>/job.json so
    finished renders survive a restart and can be listed again."""

    def __init__(self, start_worker: bool = True) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._q: queue.Queue[str] = queue.Queue()
        self._load_from_disk()
        if start_worker:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="renderer")
            self._thread.start()

    # ---- persistence -----------------------------------------------------

    def _job_dir(self, job_id: str) -> Path:
        return config.jobs_dir / job_id

    def _save(self, job: Job) -> None:
        try:
            folder = self._job_dir(job.id)
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / (JOB_FILE + ".tmp")
            tmp.write_text(json.dumps(job.to_json()))
            tmp.replace(folder / JOB_FILE)
        except OSError as exc:
            log.warning("could not persist job %s: %s", job.id, exc)

    def _load_from_disk(self) -> None:
        root = config.jobs_dir
        if not root.is_dir():
            return
        for folder in root.iterdir():
            path = folder / JOB_FILE
            if not path.is_file():
                continue
            try:
                job = Job.from_json(json.loads(path.read_text()))
            except Exception as exc:
                log.warning("skipping unreadable %s: %s", path, exc)
                continue
            if job.status in ("queued", "running"):
                job.status = "error"
                job.error = "Interrupted by restart"
                job.message = "Interrupted"
                self._save(job)
            # drop outputs whose file disappeared
            job.outputs = [o for o in job.outputs if (folder / Path(o.name).name).is_file()]
            self._jobs[job.id] = job

    # ---- public API ------------------------------------------------------

    def submit(self, track_id: str, wav_path: Path, request: RenderRequest) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            track_id=track_id,
            wav_path=wav_path,
            request=request,
            track_name=track_display_name(track_id),
            format=request.format,
            quality=request.quality,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)
        self._q.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created, reverse=True)
        return jobs[: max(0, limit)]

    def cancel(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.cancel = True
            if job.status == "queued":
                job.status = "cancelled"
                job.message = "Cancelled"
        if job:
            self._save(job)
        return job

    def public(self, job: Job) -> JobOut:
        return JobOut(
            id=job.id,
            status=job.status,
            progress=round(job.progress, 4),
            message=job.message,
            track_id=job.track_id,
            track_name=job.track_name,
            format=job.format,  # type: ignore[arg-type]
            quality=job.quality,  # type: ignore[arg-type]
            created=job.created,
            outputs=list(job.outputs),
            error=job.error,
        )

    def output_path(self, job: Job, name: str) -> Path | None:
        safe = Path(name).name
        path = self._job_dir(job.id) / safe
        if path.is_file():
            return path
        return None

    # ---- worker ----------------------------------------------------------

    def _loop(self) -> None:
        while True:
            job_id = self._q.get()
            try:
                self._run(job_id)
            except Exception:
                log.exception("job %s crashed", job_id)
                job = self.get(job_id)
                if job and job.status not in ("done", "cancelled"):
                    job.status = "error"
                    job.error = "Renderer crashed, see server log"
                    job.message = "Failed"
                    self._save(job)
            try:
                prune_old()
            except Exception:
                log.exception("prune failed")

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job or job.status == "cancelled" or job.request is None:
            return
        job.status = "running"
        job.message = "Starting"
        self._save(job)
        request = job.request
        clips = request.clips
        n = len(clips)
        out_dir = self._job_dir(job.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        settings: VisualSettings = request.settings
        track_name = job.track_name or "clip"
        used_names: set[str] = set()

        # progress weighted by seconds of video, not by clip count
        lengths = [max(0.5, c.end - c.start) for c in clips]
        total_len = sum(lengths) or 1.0
        done_len = 0.0
        last_save = 0.0

        for i, clip in enumerate(clips):
            if job.cancel:
                job.status = "cancelled"
                job.message = "Cancelled"
                self._save(job)
                return
            label = f"clip {i + 1}/{n}"
            job.message = f"Rendering {label}"
            clip_settings = clip.settings or settings
            name = clip_output_name(i + 1, clip_settings, track_name)
            if name in used_names:
                name = f"{Path(name).stem}-{i + 1}{Path(name).suffix}"
            used_names.add(name)
            dest = out_dir / name
            clip_len = lengths[i]

            def on_progress(p: float, msg: str, label=label, clip_len=clip_len) -> None:
                nonlocal last_save
                job.progress = (done_len + p * clip_len) / total_len
                job.message = f"{label} · {msg}"
                now = time.time()
                if now - last_save > 2.0:
                    last_save = now
                    self._save(job)

            def should_cancel() -> bool:
                return job.cancel

            try:
                info = render_clip(
                    wav_path=job.wav_path,
                    out_path=dest,
                    start=clip.start,
                    end=clip.end,
                    settings=clip_settings,
                    on_progress=on_progress,
                    should_cancel=should_cancel,
                    fade_in=clip.fade_in,
                    fade_out=clip.fade_out,
                    fmt=request.format,
                    quality=request.quality,
                    fps=request.fps,
                )
            except RenderError as exc:
                if job.cancel:
                    job.status = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.status = "error"
                    job.error = str(exc)
                    job.message = "Failed"
                    log.warning("job %s failed: %s", job.id, exc)
                self._save(job)
                return

            job.outputs.append(
                JobFileOut(
                    name=name,
                    clip_index=i,
                    start=clip.start,
                    end=clip.end,
                    bytes=int(info["bytes"]),
                )
            )
            done_len += clip_len
            job.progress = done_len / total_len
            self._save(job)

        job.status = "done"
        job.progress = 1.0
        job.message = f"Done · {len(job.outputs)} clip{'s' if len(job.outputs) != 1 else ''}"
        self._save(job)


manager = JobManager()
