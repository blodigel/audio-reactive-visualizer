import numpy as np

from app.audio import load_wav, mono, spectral_features
from app.logos import logo_xy
from app.models import TextBox, VisualSettings
from app.presets import SCENE_META, resolved_scene
from app.render import clamp_fades, fade_gain, render_clip
from app.viz import VisualEngine, build_text_boxes, build_text_layer


def test_engine_all_scenes(wav_path):
    data, sr = load_wav(wav_path)
    spec = spectral_features(mono(data), sr, fps=24)
    for scene in SCENE_META:
        settings = VisualSettings(
            scene=scene,
            bg_color="#050303",
            effect_color="#d63d24",
            text_color="#ede6dc",
        )
        engine = VisualEngine(data, sr, spec, settings, 80, 80, 1.0)
        frame = engine.render_frame(0, 24)
        assert frame.shape == (80, 80, 3)
        assert frame.dtype == np.uint8
        assert resolved_scene(settings)


def test_render_tiny_mp4(wav_path, tmp_path):
    out = tmp_path / "out.mp4"
    settings = VisualSettings(
        scene="oscilloscope",
        bg_color="#050303",
        effect_color="#d63d24",
        text_color="#ede6dc",
        text="FOG MARGINS",
        subtext="Rope",
        grain=0.4,
        jitter=0.2,
        glitch=0.3,
    )
    info = render_clip(wav_path, out, start=1.0, end=1.6, settings=settings, fmt="square", quality="draft", fps=24)
    assert out.is_file()
    assert out.stat().st_size > 2000
    assert info["frames"] >= 10


def test_fade_gain_independent():
    assert fade_gain(0.0, 4.0, 1.0, 0.0) == 0.0
    assert abs(fade_gain(0.5, 4.0, 1.0, 0.0) - 0.5) < 1e-6
    assert abs(fade_gain(1.0, 4.0, 1.0, 0.0) - 1.0) < 1e-6
    assert abs(fade_gain(3.0, 4.0, 0.0, 1.0) - 1.0) < 1e-6
    assert abs(fade_gain(3.5, 4.0, 0.0, 1.0) - 0.5) < 1e-6
    assert fade_gain(4.0, 4.0, 0.0, 1.0) == 0.0
    # both: start silent, mid full, end silent
    assert fade_gain(0.0, 4.0, 1.0, 1.0) == 0.0
    assert abs(fade_gain(2.0, 4.0, 1.0, 1.0) - 1.0) < 1e-6
    assert fade_gain(4.0, 4.0, 1.0, 1.0) == 0.0
    fi, fo = clamp_fades(2.0, 8.0, 8.0)
    assert fi == 2.0 and fo == 2.0


def test_render_with_fades(wav_path, tmp_path):
    out = tmp_path / "fade.mp4"
    settings = VisualSettings(
        scene="oscilloscope",
    )
    info = render_clip(
        wav_path,
        out,
        start=1.0,
        end=2.2,
        settings=settings,
        fade_in=0.35,
        fade_out=0.2,
        fmt="square",
        quality="draft",
        fps=24,
    )
    assert out.is_file()
    assert out.stat().st_size > 2000
    assert info["frames"] >= 10


def _first_ink_row(layer: np.ndarray) -> int:
    rows = np.where(layer[:, :, 3].max(axis=1) > 10)[0]
    assert len(rows)
    return int(rows[0])


def test_text_y_moves_block():
    color = (0.93, 0.90, 0.86)
    high = build_text_layer(200, 400, "FOG MARGINS", "Rope", "lower", 0.65, color, y_frac=0.20)
    low = build_text_layer(200, 400, "FOG MARGINS", "Rope", "lower", 0.65, color, y_frac=0.86)
    assert high is not None and low is not None
    assert _first_ink_row(low) > _first_ink_row(high) + 150
    assert VisualSettings().text_y == 0.86
    assert VisualSettings().text_boxes == []


def _ink_col(layer: np.ndarray) -> int:
    cols = np.where(layer[:, :, 3].max(axis=0) > 10)[0]
    assert len(cols)
    return int(cols.mean())


def test_text_box_places_line_anywhere():
    color = (0.93, 0.90, 0.86)
    left = build_text_boxes(320, 200, [TextBox(on=True, text="LEFT", x=0.18, y=0.5, size=0.9)], color)
    right = build_text_boxes(320, 200, [TextBox(on=True, text="LEFT", x=0.82, y=0.5, size=0.9)], color)
    high = build_text_boxes(320, 200, [TextBox(on=True, text="LEFT", x=0.5, y=0.18, size=0.9)], color)
    low = build_text_boxes(320, 200, [TextBox(on=True, text="LEFT", x=0.5, y=0.82, size=0.9)], color)
    assert left is not None and right is not None and high is not None and low is not None
    assert _ink_col(right) > _ink_col(left) + 80
    assert _first_ink_row(low) > _first_ink_row(high) + 60
    assert build_text_boxes(80, 40, [TextBox(on=False, text="NOPE", x=0.5, y=0.5, size=0.8)], color) is None


def test_text_boxes_mirror_title_and_subtext():
    s = VisualSettings(
        text="OLD",
        subtext="GONE",
        text_boxes=[
            {"on": True, "text": "NEW", "x": 0.2, "y": 0.3, "size": 0.5},
            {"on": True, "text": "SUB", "x": 0.8, "y": 0.7, "size": 0.4},
            {"on": False, "text": "HIDDEN", "x": 0.5, "y": 0.5, "size": 0.4},
        ],
    )
    assert s.text == "NEW"
    assert s.subtext == "SUB"
    assert s.text_y == 0.3
    assert s.text_size == 0.5


def _flat_engine(wav_path, plate: np.ndarray, **settings):
    from app.backgrounds import StillSource

    data, sr = load_wav(wav_path)
    spec = spectral_features(mono(data), sr, fps=24)
    quiet = dict(
        scene="field",
        bg_opacity=0,
        bg_blur=0,
        bg_brightness=0.5,
        bg_saturation=1,
        bg_grain=0,
        bg_glitch=0,
        bg_scanlines=0,
        bg_chroma=0,
        grain=0,
        jitter=0,
        bloom=0,
        intensity=0,
        glitch=0,
        scanlines=0,
        vignette=0,
        chromatic=0,
        trail=0,
    )
    quiet.update(settings)
    return VisualEngine(
        data,
        sr,
        spec,
        VisualSettings(**quiet),
        plate.shape[1],
        plate.shape[0],
        0.2,
        background=StillSource(plate),
    )


def test_background_fx_do_not_follow_the_visualizer(wav_path):
    plate = np.zeros((40, 48, 3), dtype=np.float32)
    plate[:, ::2] = 1.0
    sharp = _flat_engine(wav_path, plate, bg_blur=0).render_frame(0, 24)
    soft = _flat_engine(wav_path, plate, bg_blur=1).render_frame(0, 24)
    sharp_edge = np.abs(sharp[:, 1:].astype(np.float32) - sharp[:, :-1].astype(np.float32)).mean()
    soft_edge = np.abs(soft[:, 1:].astype(np.float32) - soft[:, :-1].astype(np.float32)).mean()
    assert soft_edge < sharp_edge * 0.75

    red = np.zeros((32, 32, 3), dtype=np.float32)
    red[..., 0] = 1.0
    full = _flat_engine(wav_path, red, bg_saturation=1).render_frame(0, 24)
    gray = _flat_engine(wav_path, red, bg_saturation=0).render_frame(0, 24)

    def spread(frame: np.ndarray) -> float:
        return float(np.abs(frame[..., 0].astype(np.float32) - frame[..., 1].astype(np.float32)).mean())

    assert spread(gray) < spread(full) * 0.55

    flat = np.full((36, 36, 3), 0.45, dtype=np.float32)
    clean = _flat_engine(wav_path, flat).render_frame(0, 24)
    viz_grain = _flat_engine(wav_path, flat, grain=1).render_frame(0, 24)
    bg_grain = _flat_engine(wav_path, flat, bg_grain=1).render_frame(0, 24)
    viz_delta = float(np.abs(viz_grain.astype(np.float32) - clean.astype(np.float32)).mean())
    bg_delta = float(np.abs(bg_grain.astype(np.float32) - clean.astype(np.float32)).mean())
    assert bg_delta > viz_delta * 3


def test_logo_above_text_follows_title_x():
    left = logo_xy(400, 800, 40, 20, "above-text", text_y=0.5, text_x=0.2)
    right = logo_xy(400, 800, 40, 20, "above-text", text_y=0.5, text_x=0.8)
    assert right[0] > left[0] + 100


def test_background_reactivity_follows_the_audio(wav_path):
    from app.viz import plate_amounts

    quiet = {"energy": 0.0, "bass": 0.0, "high": 0.0, "air": 0.0, "onset": 0.0}
    loud = {"energy": 1.0, "bass": 1.0, "high": 0.6, "air": 0.4, "onset": 1.0}
    static = VisualSettings(bg_blur=0.5, bg_grain=0.5, bg_chroma=0.3, bg_reactivity=0, bg_punch=0)
    for feat in (quiet, loud):
        amt = plate_amounts(static, feat)
        assert amt["zoom"] == 1.0
        assert amt["blur"] == 0.5
        assert amt["gain"] == 1.0
        assert amt["saturation"] == 1.0
        assert amt["grain"] == 0.5
        assert amt["chroma"] == 0.3

    live = VisualSettings(bg_blur=0.5, bg_grain=0.5, bg_chroma=0.3, bg_reactivity=1, bg_punch=1)
    q = plate_amounts(live, quiet)
    l = plate_amounts(live, loud)
    assert l["gain"] > 1.0 > q["gain"]
    assert l["blur"] < q["blur"]
    assert l["grain"] > q["grain"]
    assert l["chroma"] > q["chroma"]
    assert l["zoom"] > 1.05 and q["zoom"] == 1.0

    plate = np.full((36, 36, 3), 0.45, dtype=np.float32)
    plate[:, ::2] = 0.15

    def with_features(engine, feat):
        base = engine.features_at(0.2)
        base.update(feat)
        engine.features_at = lambda _t: base
        return engine

    loud_static = with_features(_flat_engine(wav_path, plate), loud).render_frame(0, 24)
    quiet_static = with_features(_flat_engine(wav_path, plate), quiet).render_frame(0, 24)
    # the plasma wash over the picture already breathes a little with energy
    static_delta = float(loud_static.mean()) - float(quiet_static.mean())
    assert abs(static_delta) < 8

    loud_live = with_features(_flat_engine(wav_path, plate, bg_reactivity=1), loud).render_frame(0, 24)
    quiet_live = with_features(_flat_engine(wav_path, plate, bg_reactivity=1), quiet).render_frame(0, 24)
    live_delta = float(loud_live.mean()) - float(quiet_live.mean())
    assert live_delta > static_delta + 15

    # punch zooms the stripes: the pattern period grows, so fewer edges per row
    punched = with_features(_flat_engine(wav_path, plate, bg_punch=1), loud).render_frame(0, 24)
    edges = lambda fr: int((np.abs(np.diff(fr[18, :, 0].astype(np.int16))) > 20).sum())
    assert edges(punched) < edges(loud_static)
