from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.audio import AUDIO_EXT, AudioError, analyze_file, ingest_audio
from app.backgrounds import ALLOWED_EXT, BackgroundError, save_upload
from app.clips import suggest_clips
from app.config import config
from app.demo import write_demo_wav
from app.fonts import ALLOWED_FONT_EXT, FontError, MAX_FONT_BYTES, custom_path, save_font
from app.jobs import manager
from app.logos import ALLOWED_LOGO_EXT, LogoError, save_logo
from app.models import RenderRequest, SuggestIn
from app.presets import public_catalog
from app.storage import prune_old
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
    mimetypes.add_type("font/ttf", ".ttf")
    mimetypes.add_type("font/otf", ".otf")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        prune_old()
    except Exception:
        log.exception("startup prune failed")
    app = FastAPI(title="NOISE/VIZ", version="1.1.0")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "service": "audio-reactive-visualizer"}

    @app.get("/api/presets")
    def presets() -> dict:
        return public_catalog()

    @app.post("/api/tracks")
    async def upload_track(file: UploadFile = File(...)) -> dict:
        name = file.filename or "upload.wav"
        ext = Path(name).suffix.lower()
        if ext not in AUDIO_EXT:
            raise HTTPException(
                400, "Use WAV, MP3, FLAC, AIFF, M4A, AAC or OGG"
            )
        track_id = uuid.uuid4().hex[:16]
        dest_dir = _track_dir(track_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        raw = dest_dir / f"upload{ext}"
        dest = dest_dir / "source.wav"
        limit = config.max_upload_mb * 1024 * 1024
        written = 0
        try:
            with raw.open("wb") as out:
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
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise
        finally:
            await file.close()
        if written < 64:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise HTTPException(400, "File is empty")
        try:
            ingest_audio(raw, dest)
            meta = analyze_file(dest, filename=name, track_id=track_id)
        except AudioError as exc:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise HTTPException(400, str(exc)) from exc
        if raw.resolve() != dest.resolve():
            raw.unlink(missing_ok=True)
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

    @app.post("/api/backgrounds")
    async def upload_background(file: UploadFile = File(...)) -> dict:
        name = file.filename or "background.png"
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, "Use a PNG, JPEG or WebP image")
        bg_id = uuid.uuid4().hex[:16]
        raw = config.backgrounds_dir / f"{bg_id}.src{ext}"
        dest = config.backgrounds_dir / f"{bg_id}.png"
        limit = 25 * 1024 * 1024
        written = 0
        try:
            with raw.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        raise HTTPException(413, "Image is larger than 25 MB")
                    out.write(chunk)
        except HTTPException:
            raw.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        if written < 32:
            raw.unlink(missing_ok=True)
            raise HTTPException(400, "File is empty")
        try:
            save_upload(raw, dest)
        except BackgroundError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(exc)) from exc
        finally:
            raw.unlink(missing_ok=True)
        return {"id": bg_id, "filename": name, "url": f"/api/backgrounds/{bg_id}"}

    @app.get("/api/backgrounds/{bg_id}")
    def get_background(bg_id: str) -> FileResponse:
        _check_id(bg_id)
        path = config.backgrounds_dir / f"{bg_id}.png"
        if not path.is_file():
            raise HTTPException(404, "Background not found")
        return FileResponse(path, media_type="image/png", filename="background.png")

    @app.post("/api/fonts")
    async def upload_font(file: UploadFile = File(...)) -> dict:
        name = file.filename or "custom.ttf"
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_FONT_EXT:
            raise HTTPException(400, "Use a TTF or OTF font")
        font_id = uuid.uuid4().hex[:16]
        raw = config.fonts_dir / f"{font_id}.src{ext}"
        dest = config.fonts_dir / f"{font_id}{ext}"
        written = 0
        try:
            with raw.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_FONT_BYTES:
                        raise HTTPException(413, "Font is larger than 8 MB")
                    out.write(chunk)
        except HTTPException:
            raw.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        if written < 64:
            raw.unlink(missing_ok=True)
            raise HTTPException(400, "File is empty")
        try:
            family = save_font(raw, dest)
        except FontError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(exc)) from exc
        finally:
            raw.unlink(missing_ok=True)
        media = "font/otf" if ext == ".otf" else "font/ttf"
        return {
            "id": font_id,
            "filename": name,
            "family": family,
            "url": f"/api/fonts/{font_id}",
            "media_type": media,
        }

    @app.get("/api/fonts/{font_id}")
    def get_font(font_id: str) -> FileResponse:
        _check_id(font_id)
        path = custom_path(font_id)
        if not path:
            raise HTTPException(404, "Font not found")
        media = "font/otf" if path.suffix.lower() == ".otf" else "font/ttf"
        return FileResponse(path, media_type=media, filename=path.name)

    @app.post("/api/logos")
    async def upload_logo(file: UploadFile = File(...)) -> dict:
        name = file.filename or "logo.png"
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_LOGO_EXT:
            raise HTTPException(400, "Use a PNG, JPEG or WebP logo")
        logo_id = uuid.uuid4().hex[:16]
        raw = config.logos_dir / f"{logo_id}.src{ext}"
        dest = config.logos_dir / f"{logo_id}.png"
        limit = 12 * 1024 * 1024
        written = 0
        try:
            with raw.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        raise HTTPException(413, "Logo is larger than 12 MB")
                    out.write(chunk)
        except HTTPException:
            raw.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        if written < 32:
            raw.unlink(missing_ok=True)
            raise HTTPException(400, "File is empty")
        try:
            save_logo(raw, dest)
        except LogoError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(exc)) from exc
        finally:
            raw.unlink(missing_ok=True)
        return {"id": logo_id, "filename": name, "url": f"/api/logos/{logo_id}"}

    @app.get("/api/logos/{logo_id}")
    def get_logo(logo_id: str) -> FileResponse:
        _check_id(logo_id)
        path = config.logos_dir / f"{logo_id}.png"
        if not path.is_file():
            raise HTTPException(404, "Logo not found")
        return FileResponse(path, media_type="image/png", filename="logo.png")

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

    @app.get("/api/jobs")
    def list_jobs(limit: int = 20) -> dict:
        limit = max(1, min(limit, 100))
        return {"jobs": [manager.public(j).model_dump() for j in manager.recent(limit)]}

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
