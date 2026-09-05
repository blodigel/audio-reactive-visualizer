import numpy as np

from app.audio import load_wav, mono, spectral_features
from app.models import VisualSettings
from app.presets import GENRE_META, resolved_scene
from app.render import render_clip
from app.viz import VisualEngine


def test_engine_all_scenes(wav_path):
    data, sr = load_wav(wav_path)
    spec = spectral_features(mono(data), sr, fps=24)
    for gid in GENRE_META:
        settings = VisualSettings(genre=gid, scene="auto", format="square", quality="draft", fps=24)
        engine = VisualEngine(data, sr, spec, settings, 80, 80, 1.0)
        frame = engine.render_frame(0, 24)
        assert frame.shape == (80, 80, 3)
        assert frame.dtype == np.uint8
        assert resolved_scene(settings)


def test_render_tiny_mp4(wav_path, tmp_path):
    out = tmp_path / "out.mp4"
    settings = VisualSettings(
        genre="noise",
        scene="oscilloscope",
        format="square",
        quality="draft",
        fps=24,
        text="TEST",
        subtext="noise-viz",
        grain=0.4,
        jitter=0.2,
        glitch=0.3,
    )
    info = render_clip(wav_path, out, start=1.0, end=1.6, settings=settings)
    assert out.is_file()
    assert out.stat().st_size > 2000
    assert info["frames"] >= 10
