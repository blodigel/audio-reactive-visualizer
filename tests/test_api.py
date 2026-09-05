from app.jobs import clip_output_name
from app.models import VisualSettings


def test_clip_output_name():
    s = VisualSettings(text="FOG MARGINS", subtext="Rope")
    assert clip_output_name(1, s, "song.wav") == "FOG MARGINS – Rope – 01.mp4"
    s2 = VisualSettings(text="", subtext="")
    assert clip_output_name(2, s2, "demo.wav") == "demo – 02.mp4"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_presets(client):
    r = client.get("/api/presets")
    assert r.status_code == 200
    body = r.json()
    assert len(body["palettes"]) >= 6
    assert body["formats"]


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"NOISE" in r.content


def test_upload_and_suggest(client, wav_path):
    with wav_path.open("rb") as f:
        r = client.post("/api/tracks", files={"file": ("song.wav", f, "audio/wav")})
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["id"]
    assert meta["duration"] > 7
    tid = meta["id"]
    r = client.get(f"/api/tracks/{tid}")
    assert r.status_code == 200
    r = client.get(f"/api/tracks/{tid}/audio")
    assert r.status_code == 200
    r = client.post(
        f"/api/tracks/{tid}/suggest",
        json={"count": 2, "length": 2.0},
    )
    assert r.status_code == 200
    assert len(r.json()["suggestions"]) >= 1


def test_rejects_unknown_extension(client):
    r = client.post("/api/tracks", files={"file": ("x.txt", b"not audio", "text/plain")})
    assert r.status_code == 400


def test_rejects_garbage_audio(client):
    r = client.post("/api/tracks", files={"file": ("x.mp3", b"not a real mp3", "audio/mpeg")})
    assert r.status_code == 400


def test_upload_mp3_and_flac(client, wav_path, tmp_path):
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg required for audio ingest tests"
    mp3 = tmp_path / "song.mp3"
    flac = tmp_path / "song.flac"
    subprocess.check_call(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-q:a", "6", str(mp3)]
    )
    subprocess.check_call(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path), str(flac)]
    )
    with mp3.open("rb") as f:
        r = client.post("/api/tracks", files={"file": ("Fog Margins.mp3", f, "audio/mpeg")})
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["filename"] == "Fog Margins.mp3"
    assert meta["duration"] > 7
    assert client.get(f"/api/tracks/{meta['id']}/audio").status_code == 200
    with flac.open("rb") as f:
        r = client.post("/api/tracks", files={"file": ("Rope.flac", f, "audio/flac")})
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "Rope.flac"


def test_demo_track(client):
    r = client.post("/api/tracks/demo")
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["duration"] > 10
    assert meta["suggestions"]
    assert client.get(f"/api/tracks/{meta['id']}/audio").status_code == 200


def test_jobs_list_and_persist(client, wav_path, tmp_path):
    from app.jobs import JobManager
    from app.config import config

    with wav_path.open("rb") as f:
        r = client.post("/api/tracks", files={"file": ("song.wav", f, "audio/wav")})
    tid = r.json()["id"]
    body = {
        "track_id": tid,
        "format": "square",
        "quality": "draft",
        "fps": 12,
        "clips": [{"start": 1.0, "end": 1.6, "settings": {"scene": "bars", "text": "FOG MARGINS"}}],
    }
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["format"] == "square" and job["quality"] == "draft"
    r = client.get("/api/jobs")
    assert r.status_code == 200
    ids = [j["id"] for j in r.json()["jobs"]]
    assert job["id"] in ids
    # job.json is on disk right after submit
    assert (config.jobs_dir / job["id"] / "job.json").is_file()
    # a fresh manager (simulating a restart) sees the job and flags an unfinished one
    fresh = JobManager(start_worker=False)
    loaded = fresh.get(job["id"])
    assert loaded is not None
    assert loaded.status in ("done", "error", "running", "cancelled") or loaded.status == "error"
    if loaded.status == "error":
        assert loaded.error == "Interrupted by restart"


def test_render_request_ignores_format_inside_settings():
    from app.models import RenderRequest

    req = RenderRequest(
        track_id="a" * 12,
        clips=[{"start": 0, "end": 2, "settings": {"format": "square", "quality": "high"}}],
        settings={"format": "landscape"},
    )
    assert req.format == "reels"
    assert req.quality == "standard"
    assert not hasattr(req.clips[0].settings, "format")


def test_prune_old(tmp_path, monkeypatch):
    import os
    import time

    from app.config import config
    from app.storage import prune_old

    monkeypatch.setattr(config, "data_dir", tmp_path / "data")
    config.ensure_dirs()
    old = config.tracks_dir / ("a" * 12)
    new = config.tracks_dir / ("b" * 12)
    old.mkdir()
    new.mkdir()
    (old / "meta.json").write_text("{}")
    (new / "meta.json").write_text("{}")
    stale = time.time() - 40 * 86400
    os.utime(old, (stale, stale))
    os.utime(old / "meta.json", (stale, stale))
    removed = prune_old(retention_days=30)
    assert old in removed
    assert not old.exists()
    assert new.exists()
    assert prune_old(retention_days=0) == []
