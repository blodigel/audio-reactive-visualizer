from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.fonts import BUNDLED_DIR, public_fonts, resolve_font
from app.models import VisualSettings
from app.viz import VisualEngine
from app.audio import load_wav, mono, spectral_features


def test_bundled_fonts_in_catalog(client):
    r = client.get("/api/presets")
    assert r.status_code == 200
    fonts = r.json()["fonts"]
    ids = {f["id"] for f in fonts}
    assert {"archivo", "bebas", "glitch", "rocker"} <= ids
    assert len(public_fonts()) >= 6


def test_upload_font_and_serve(client):
    src = BUNDLED_DIR / "ArchivoBlack-Regular.ttf"
    with src.open("rb") as f:
        r = client.post("/api/fonts", files={"file": ("band.ttf", f, "font/ttf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert "Archivo" in body["family"]
    got = client.get(body["url"])
    assert got.status_code == 200
    assert len(got.content) > 1000


def test_rejects_non_font(client):
    r = client.post("/api/fonts", files={"file": ("x.txt", b"not a font", "text/plain")})
    assert r.status_code == 400


def test_upload_logo_keeps_alpha(client, tmp_path: Path):
    img = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((8, 8, 72, 32), fill=(200, 40, 30, 255))
    path = tmp_path / "logo.png"
    img.save(path, "PNG")
    with path.open("rb") as f:
        r = client.post("/api/logos", files={"file": ("mark.png", f, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    got = client.get(body["url"])
    assert got.status_code == 200
    from io import BytesIO

    loaded = Image.open(BytesIO(got.content)).convert("RGBA")
    assert loaded.mode == "RGBA"
    # corner stays transparent
    assert loaded.getpixel((0, 0))[3] == 0


def test_font_and_logo_on_frame(client, wav_path, tmp_path: Path):
    src = BUNDLED_DIR / "NewRocker-Regular.ttf"
    with src.open("rb") as f:
        font = client.post("/api/fonts", files={"file": ("rock.ttf", f, "font/ttf")}).json()
    logo_img = Image.new("RGBA", (64, 64), (40, 180, 200, 255))
    lp = tmp_path / "l.png"
    logo_img.save(lp, "PNG")
    with lp.open("rb") as f:
        logo = client.post("/api/logos", files={"file": ("l.png", f, "image/png")}).json()

    with wav_path.open("rb") as f:
        track = client.post("/api/tracks", files={"file": ("song.wav", f, "audio/wav")}).json()
    settings = VisualSettings(
        scene="oscilloscope",
        text="FOG MARGINS",
        subtext="Rope",
        font="custom",
        font_id=font["id"],
        logo_id=logo["id"],
        logo_position="top-left",
        logo_size=0.22,
    )
    r = client.post(
        "/api/jobs",
        json={
            "track_id": track["id"],
            "format": "square",
            "quality": "draft",
            "fps": 24,
            "clips": [{"start": 0.5, "end": 1.2, "settings": settings.model_dump()}],
            "settings": settings.model_dump(),
        },
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    # jobs run on a thread; poll
    import time

    body = None
    for _ in range(40):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"done", "error", "cancelled"}:
            break
        time.sleep(0.15)
    assert body and body["status"] == "done", body
    assert body["outputs"]


def test_resolve_bundled_font():
    path, tracking = resolve_font("glitch", "")
    assert path is not None
    assert path.name.startswith("RubikGlitch")
    assert tracking == 0.04
    ImageFont.truetype(str(path), 24)


def test_engine_draws_text_and_logo(wav_path, tmp_path: Path):
    data, sr = load_wav(wav_path)
    spec = spectral_features(mono(data), sr, fps=24)
    logo = Image.new("RGBA", (40, 20), (0, 255, 180, 255))
    settings = VisualSettings(
        scene="bars",
        text="FOG MARGINS",
        font="bebas",
        logo_position="top-right",
        logo_size=0.25,
    )
    engine = VisualEngine(data, sr, spec, settings, 120, 120, 0.5, logo=logo)
    frame = engine.render_frame(0, 24)
    assert frame.shape == (120, 120, 3)
    patch = frame[2:22, 88:118]
    assert patch[:, :, 1].mean() > 60


def test_text_and_logo_fx_change_pixels(wav_path):
    data, sr = load_wav(wav_path)
    spec = spectral_features(mono(data), sr, fps=24)
    logo = Image.new("RGBA", (48, 24), (0, 255, 180, 255))
    base = dict(
        scene="bars",
        text="FOG MARGINS",
        subtext="Rope",
        font="archivo",
        logo_position="top-left",
        logo_size=0.28,
    )
    plain = VisualEngine(data, sr, spec, VisualSettings(**base), 160, 160, 0.5, logo=logo)
    fx = VisualEngine(
        data,
        sr,
        spec,
        VisualSettings(
            **base,
            text_glitch=1,
            text_chroma=1,
            text_glow=0.8,
            text_jitter=0.9,
            logo_glitch=1,
            logo_chroma=1,
            logo_glow=0.8,
            logo_jitter=0.9,
        ),
        160,
        160,
        0.5,
        logo=logo,
    )
    a = plain.render_frame(3, 24)
    b = fx.render_frame(3, 24)
    assert a.shape == b.shape
    assert int(np.abs(a.astype(np.int16) - b.astype(np.int16)).sum()) > 500
