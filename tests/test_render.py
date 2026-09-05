import numpy as np

from app.audio import load_wav, mono, spectral_features
from app.models import VisualSettings
from app.presets import SCENE_META, resolved_scene
from app.render import clamp_fades, fade_gain, render_clip
from app.viz import VisualEngine, build_text_layer


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
