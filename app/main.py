from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.audio import AudioError, analyze_file
from app.clips import suggest_clips
from app.config import config
from app.demo import write_demo_wav
from app.jobs import manager
from app.models import RenderRequest, SuggestIn
from app.presets import public_catalog
import numpy as np

log = logging.getLogger("noiseviz")
STATIC = Path(__file__).resolve().parent / "static"
ID_RE = re.compile(r"^[a-f0-9]{12,32}$")


def _check_id(value: str) -> str:
    if not ID_RE.match(value):
        raise HTTPException(404, "Not found")
    return value


def _track_dir(track_id: str) -> Path:
    return config.tracks_dir / track_id


def _load_meta(track_id: str) -> dict:
    path = _track_dir(track_id) / "meta.json"
    if not path.is_file():
        raise HTTPException(404, "Track not found")
    return json.loads(path.read_text())


def create_app() -> FastAPI:
    config.ensure_dirs()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="Noise Visualizer", version="1.0.0")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "service": "noise-visualizer"}

    @app.get("/api/presets")
    def presets() -> dict:
        return public_catalog()

    @app.post("/api/tracks")
    async def upload_track(file: UploadFile = File(...)) -> dict:
        name = file.filename or "upload.wav"
        lower = name.lower()
        if not (lower.endswith(".wav") or lower.endswith(".wave")):
            raise HTTPException(400, "Please upload a WAV file")
        track_id = uuid.uuid4().hex[:16]
        dest_dir = _track_dir(track_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "source.wav"
        limit = config.max_upload_mb * 1024 * 1024
        written = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        raise HTTPException(
                            413, f"File is larger than {config.max_upload_mb} MB"
                        )
                    out.write(chunk)
        except HTTPException:
            dest.unlink(missing_ok=True)
            dest_dir.rmdir()
            raise
        finally:
            await file.close()
        if written < 64:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "File is empty")
        try:
            meta = analyze_file(dest, filename=name, track_id=track_id)
        except AudioError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(exc)) from exc
        (dest_dir / "meta.json").write_text(json.dumps(meta))
        return meta

    @app.post("/api/tracks/demo")
    def demo_track() -> dict:
        track_id = uuid.uuid4().hex[:16]
        dest_dir = _track_dir(track_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "source.wav"
        write_demo_wav(dest)
        try:
            meta = analyze_file(
                dest, filename="demo.wav", track_id=track_id, clip_length=8.0, clip_count=3
            )
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from exc
        (dest_dir / "meta.json").write_text(json.dumps(meta))
        return meta

    @app.get("/api/tracks/{track_id}")
    def get_track(track_id: str) -> dict:
        return _load_meta(_check_id(track_id))

    @app.get("/api/tracks/{track_id}/audio")
    def get_audio(track_id: str) -> FileResponse:
        _check_id(track_id)
        path = _track_dir(track_id) / "source.wav"
        if not path.is_file():
            raise HTTPException(404, "Audio missing")
        return FileResponse(path, media_type="audio/wav", filename="source.wav")

    @app.post("/api/tracks/{track_id}/suggest")
    def resuggest(track_id: str, body: SuggestIn) -> dict:
        meta = _load_meta(_check_id(track_id))
        env = meta["envelope"]
        suggestions = suggest_clips(
            duration=float(meta["duration"]),
            env_times=np.asarray(env["times"], dtype=np.float64),
            env_rms=np.asarray(env["rms"], dtype=np.float64),
            onset_times=np.asarray(meta.get("onsets") or [], dtype=np.float64),
            clip_len=body.length,
            count=body.count,
        )
        meta["suggestions"] = suggestions
        (_track_dir(track_id) / "meta.json").write_text(json.dumps(meta))
        return {"suggestions": suggestions}

    @app.post("/api/jobs")
    def start_job(body: RenderRequest) -> dict:
        track_id = _check_id(body.track_id)
        meta = _load_meta(track_id)
        duration = float(meta["duration"])
        wav = _track_dir(track_id) / "source.wav"
        if not wav.is_file():
            raise HTTPException(404, "Audio missing")
        for clip in body.clips:
            if clip.end > duration + 0.05:
                raise HTTPException(400, "A clip extends past the end of the track")
        job = manager.submit(track_id, wav, body)
        return manager.public(job).model_dump()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = manager.get(_check_id(job_id))
        if not job:
            raise HTTPException(404, "Job not found")
        return manager.public(job).model_dump()

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        job = manager.cancel(_check_id(job_id))
        if not job:
            raise HTTPException(404, "Job not found")
        return manager.public(job).model_dump()

    @app.get("/api/jobs/{job_id}/files/{name}")
    def download(job_id: str, name: str) -> FileResponse:
        job = manager.get(_check_id(job_id))
        if not job:
            raise HTTPException(404, "Job not found")
        path = manager.output_path(job, name)
        if not path:
            raise HTTPException(404, "File not found")
        return FileResponse(path, media_type="video/mp4", filename=name)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
