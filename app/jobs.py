from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from app.config import config
from app.models import JobFileOut, JobOut, RenderRequest, VisualSettings
from app.render import RenderError, render_clip

log = logging.getLogger("noiseviz.jobs")


@dataclass
class Job:
    id: str
    track_id: str
    wav_path: Path
    request: RenderRequest
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    error: str | None = None
    outputs: list[JobFileOut] = field(default_factory=list)
    cancel: bool = False


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._q: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="renderer")
        self._thread.start()

    def submit(self, track_id: str, wav_path: Path, request: RenderRequest) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            track_id=track_id,
            wav_path=wav_path,
            request=request,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._q.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.cancel = True
            if job.status == "queued":
                job.status = "cancelled"
                job.message = "Cancelled"
            return job

    def public(self, job: Job) -> JobOut:
        return JobOut(
            id=job.id,
            status=job.status,
            progress=round(job.progress, 4),
            message=job.message,
            track_id=job.track_id,
            outputs=list(job.outputs),
            error=job.error,
        )

    def output_path(self, job: Job, name: str) -> Path | None:
        safe = Path(name).name
        path = config.jobs_dir / job.id / safe
        if path.is_file():
            return path
        return None

    def _loop(self) -> None:
        while True:
            job_id = self._q.get()
            try:
                self._run(job_id)
            except Exception:
                log.exception("job %s crashed", job_id)

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job or job.status == "cancelled":
            return
        job.status = "running"
        job.message = "Starting"
        clips = job.request.clips
        n = len(clips)
        out_dir = config.jobs_dir / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        settings: VisualSettings = job.request.settings

        for i, clip in enumerate(clips):
            if job.cancel:
                job.status = "cancelled"
                job.message = "Cancelled"
                return
            label = f"clip {i + 1}/{n}"
            job.message = f"Rendering {label}"
            name = f"clip-{i + 1:02d}.mp4"
            dest = out_dir / name

            def on_progress(p: float, msg: str, i=i, label=label) -> None:
                job.progress = (i + p) / n
                job.message = f"{label} · {msg}"

            def should_cancel() -> bool:
                return job.cancel

            try:
                info = render_clip(
                    wav_path=job.wav_path,
                    out_path=dest,
                    start=clip.start,
                    end=clip.end,
                    settings=settings,
                    on_progress=on_progress,
                    should_cancel=should_cancel,
                )
            except RenderError as exc:
                if job.cancel:
                    job.status = "cancelled"
                    job.message = "Cancelled"
                    return
                job.status = "error"
                job.error = str(exc)
                job.message = "Failed"
                log.warning("job %s failed: %s", job.id, exc)
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
            job.progress = (i + 1) / n

        job.status = "done"
        job.progress = 1.0
        job.message = f"Done · {len(job.outputs)} clip{'s' if len(job.outputs) != 1 else ''}"


manager = JobManager()
