import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from app.backgrounds import cover_fit, open_background
from app.models import VisualSettings


def test_cover_fit_size():
    src = Image.new("RGB", (200, 100), (20, 10, 10))
    out = cover_fit(src, 80, 80)
    assert out.size == (80, 80)


def test_save_and_upload_api(client, tmp_path: Path):
    img_path = tmp_path / "bg.jpg"
    Image.new("RGB", (64, 96), (180, 40, 30)).save(img_path, "JPEG")
    with img_path.open("rb") as f:
        r = client.post("/api/backgrounds", files={"file": ("still.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    got = client.get(body["url"])
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/")


def test_rejects_non_image(client):
    r = client.post("/api/backgrounds", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_video_background_loops_frames(client, tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    src = tmp_path / "bg.mp4"
    subprocess.check_call(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=10:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(src),
        ]
    )
    with src.open("rb") as f:
        r = client.post("/api/backgrounds", files={"file": ("clip.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "video"
    assert body["video_url"]
    meta = client.get(f"/api/backgrounds/{body['id']}/meta")
    assert meta.status_code == 200
    assert meta.json()["kind"] == "video"
    assert meta.json()["duration"] > 0.5
    vid = client.get(body["video_url"])
    assert vid.status_code == 200
    assert vid.headers["content-type"].startswith("video/")
    poster = client.get(body["url"])
    assert poster.status_code == 200
    assert poster.headers["content-type"].startswith("image/")
    source = open_background(body["id"], 80, 96)
    assert source is not None
    try:
        a = source.frame(0.0)
        b = source.frame(1.0)
        again = source.frame(0.0)
    finally:
        source.close()
    assert a.shape == (96, 80, 3)
    assert float(np.abs(a - b).mean()) > 0.01
    assert float(np.abs(a - again).mean()) < 0.05


def test_background_id_validation():
    s = VisualSettings(background_id="")
    assert s.background_id == ""
    s = VisualSettings(background_id="ab" * 8)
    assert s.background_id == "ab" * 8
