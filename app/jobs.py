from __future__ import annotations

import json
import logging
import multiprocessing as mp
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import config
from app.models import JobFileOut, JobOut, RenderRequest, VisualSettings
from app.render_worker import default_workers, render_clip_process
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

        # Output names are decided up front so clip order is stable in the list.
        names: list[str] = []
        used: set[str] = set()
        for i, clip in enumerate(clips):
            name = clip_output_name(i + 1, clip.settings or settings, track_name)
            if name in used:
                name = f"{Path(name).stem}-{i + 1}{Path(name).suffix}"
            used.add(name)
            names.append(name)

        # Frames inside a clip are sequential (trail and particles carry state),
        # but clips are independent, so each clip renders in its own process.
        lengths = [max(0.5, c.end - c.start) for c in clips]
        total_len = sum(lengths) or 1.0
        progress = [0.0] * n
        results: dict[int, int] = {}
        failure: tuple[str, str] | None = None
        workers = max(1, min(default_workers(), n))
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        cancel = ctx.Event()
        pending = list(range(n))
        running: dict[int, mp.process.BaseProcess] = {}
        last_save = 0.0

        def publish() -> None:
            nonlocal last_save
            job.progress = sum(p * L for p, L in zip(progress, lengths, strict=True)) / total_len
            active = sorted(running)
            if active:
                label = ", ".join(f"clip {i + 1}" for i in active)
                job.message = f"Rendering {label} of {n}"
            now = time.time()
            if now - last_save > 2.0:
                last_save = now
                self._save(job)

        def start_next() -> None:
            i = pending.pop(0)
            clip = clips[i]
            proc = ctx.Process(
                target=render_clip_process,
                name=f"render-{job.id}-{i + 1}",
                args=(
                    i,
                    job.wav_path,
                    out_dir / names[i],
                    clip.start,
                    clip.end,
                    clip.settings or settings,
                    clip.fade_in,
                    clip.fade_out,
                    request.format,
                    request.quality,
                    request.fps,
                    q,
                    cancel,
                ),
                daemon=True,
            )
            proc.start()
            running[i] = proc

        try:
            while pending or running:
                while pending and len(running) < workers and not failure and not job.cancel:
                    start_next()
                    publish()
                if job.cancel:
                    cancel.set()
                try:
                    msg = q.get(timeout=0.25)
                except queue.Empty:
                    msg = None
                if msg:
                    kind, i = msg[0], msg[1]
                    if kind == "progress":
                        progress[i] = msg[2]
                    elif kind == "done":
                        progress[i] = 1.0
                        results[i] = msg[2]
                    elif kind in ("cancelled", "error"):
                        if failure is None and not job.cancel:
                            failure = (kind, msg[2])
                            cancel.set()
                            pending.clear()
                    publish()
                # reap exited processes; a silent death counts as an error
                for i, proc in list(running.items()):
                    if proc.is_alive():
                        continue
                    proc.join(timeout=0)
                    del running[i]
                    if i not in results and failure is None and not job.cancel:
                        if proc.exitcode not in (0, None):
                            failure = ("error", f"Render process for clip {i + 1} exited with code {proc.exitcode}")
                            cancel.set()
                            pending.clear()
                if job.cancel:
                    pending.clear()
        finally:
            # drain anything still in flight so a late "done" is not lost
            deadline = time.time() + 5.0
            while any(p.is_alive() for p in running.values()) and time.time() < deadline:
                try:
                    msg = q.get(timeout=0.1)
                    if msg[0] == "done":
                        results[msg[1]] = msg[2]
                except queue.Empty:
                    pass
            for proc in running.values():
                if proc.is_alive():
                    proc.terminate()
                proc.join(timeout=2)
            q.close()

        for i in sorted(results):
            job.outputs.append(
                JobFileOut(
                    name=names[i],
                    clip_index=i,
                    start=clips[i].start,
                    end=clips[i].end,
                    bytes=int(results[i]),
                )
            )

        if job.cancel:
            job.status = "cancelled"
            job.message = "Cancelled"
        elif failure:
            kind, reason = failure
            job.status = "error"
            job.error = reason
            job.message = "Failed"
            log.warning("job %s failed: %s", job.id, reason)
        else:
            job.status = "done"
            job.progress = 1.0
            job.message = f"Done · {len(job.outputs)} clip{'s' if len(job.outputs) != 1 else ''}"
        self._save(job)

manager = JobManager()
