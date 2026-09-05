from app.models import VisualSettings
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
