def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_presets(client):
    r = client.get("/api/presets")
    assert r.status_code == 200
    body = r.json()
    assert len(body["genres"]) >= 8
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


def test_rejects_non_wav(client):
    r = client.post("/api/tracks", files={"file": ("x.mp3", b"not a wav", "audio/mpeg")})
    assert r.status_code == 400


def test_demo_track(client):
    r = client.post("/api/tracks/demo")
    assert r.status_code == 200, r.text
    meta = r.json()
    assert meta["duration"] > 10
    assert meta["suggestions"]
    assert client.get(f"/api/tracks/{meta['id']}/audio").status_code == 200
