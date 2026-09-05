from app.models import VisualSettings
from app.presets import GENRE_META, public_catalog, resolved_scene, settings_from_genre, output_size


def test_catalog_complete():
    cat = public_catalog()
    assert {g["id"] for g in cat["genres"]} == set(GENRE_META)
    assert any(s["id"] == "auto" for s in cat["scenes"])
    assert any(f["id"] == "reels" for f in cat["formats"])


def test_genre_settings_valid():
    for gid in GENRE_META:
        s = settings_from_genre(gid)
        assert s.genre == gid
        assert 0 <= s.grain <= 1


def test_output_even():
    w, h = output_size("reels", "draft")
    assert w % 2 == 0 and h % 2 == 0
    assert w == 540 and h == 960


def test_resolved_scene():
    s = VisualSettings(genre="techno", scene="auto")
    assert resolved_scene(s) == "tunnel"
    s = VisualSettings(genre="techno", scene="bars")
    assert resolved_scene(s) == "bars"
