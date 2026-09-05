from app.models import ClipIn, VisualSettings
from app.presets import (
    COLOR_PRESETS,
    normalize_hex,
    output_size,
    palette_from_settings,
    public_catalog,
    resolved_scene,
)


def test_catalog_complete():
    cat = public_catalog()
    assert {p["id"] for p in cat["palettes"]} == {p["id"] for p in COLOR_PRESETS}
    assert any(s["id"] == "mixed" for s in cat["scenes"])
    assert any(f["id"] == "reels" for f in cat["formats"])
    assert "bg_color" in cat["defaults"]
    assert any(s["key"] == "text_glitch" for s in cat["text_fx"])
    assert any(s["key"] == "logo_glow" for s in cat["logo_fx"])
    assert {lk["id"] for lk in cat["looks"]} >= {"rust", "bone", "ice", "blood", "acid"}


def test_hex_and_palette():
    assert normalize_hex("D63D24") == "#d63d24"
    s = VisualSettings(bg_color="#050303", effect_color="#d63d24", text_color="#ede6dc")
    pal = palette_from_settings(s)
    assert pal["fg"][0] > pal["fg"][1]
    assert pal["accent"][0] > 0.8


def test_output_even():
    w, h = output_size("reels", "draft")
    assert w % 2 == 0 and h % 2 == 0
    assert w == 540 and h == 960


def test_resolved_scene():
    s = VisualSettings(scene="auto")
    assert resolved_scene(s) == "mixed"
    s = VisualSettings(scene="bars")
    assert resolved_scene(s) == "bars"


def test_rejects_bad_color():
    import pytest

    with pytest.raises(Exception):
        VisualSettings(bg_color="red")


def test_clip_owns_settings():
    clip = ClipIn(start=1.0, end=4.0, settings=VisualSettings(scene="starburst", grain=0.9, text="A"))
    assert clip.settings.scene == "starburst"
    assert clip.settings.grain == 0.9
    assert clip.settings.text == "A"
    plain = ClipIn(start=0.0, end=2.0)
    assert plain.settings is None
    faded = ClipIn(start=1.0, end=5.0, fade_in=0.4, fade_out=1.2)
    assert faded.fade_in == 0.4
    assert faded.fade_out == 1.2
