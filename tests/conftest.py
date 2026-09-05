from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient


def write_noise_wav(path: Path, seconds: float = 8.0, sr: int = 22050) -> Path:
    n = int(seconds * sr)
    t = np.arange(n) / sr
    # harsh-ish: noise bursts + a low pulse + a tone that comes in later
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n).astype(np.float32) * 0.18
    pulse = (np.sin(2 * np.pi * 2.2 * t) > 0.6).astype(np.float32) * 0.25
    tone = np.sin(2 * np.pi * 110 * t).astype(np.float32) * 0.12
    env = np.clip((t - 1.0) / 0.4, 0, 1) * np.clip((seconds - 0.4 - t) / 0.4, 0, 1)
    # louder middle section
    mid = np.exp(-((t - seconds * 0.55) ** 2) / (2 * 0.8**2))
    mono = (noise + pulse + tone * env) * (0.35 + 0.9 * mid)
    stereo = np.stack([mono, np.roll(mono, 40)], axis=1).astype(np.float32)
    stereo = np.clip(stereo, -1.0, 1.0)
    sf.write(path, stereo, sr, subtype="PCM_16")
    return path


@pytest.fixture
def wav_path(tmp_path: Path) -> Path:
    return write_noise_wav(tmp_path / "track.wav", seconds=8.0)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.config import config

    config.data_dir = tmp_path / "data"
    config.ensure_dirs()
    from app.main import create_app

    return TestClient(create_app())
