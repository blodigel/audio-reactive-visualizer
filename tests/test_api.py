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
