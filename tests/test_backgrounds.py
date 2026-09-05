from pathlib import Path

from PIL import Image

from app.backgrounds import cover_fit
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


def test_background_id_validation():
    s = VisualSettings(background_id="")
    assert s.background_id == ""
    s = VisualSettings(background_id="ab" * 8)
    assert s.background_id == "ab" * 8
