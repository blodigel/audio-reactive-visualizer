from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def write_demo_wav(path: Path, seconds: float = 24.0, sr: int = 44100) -> Path:
    """Harsh-ish stereo noise with pulses — enough structure to pick clips from."""
    n = int(seconds * sr)
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(23)
    from scipy.signal import lfilter

    noise = rng.standard_normal(n).astype(np.float32)
    colored = lfilter([0.08], [1.0, -0.92], noise).astype(np.float32)
    pulses = (np.sin(2 * np.pi * 1.7 * t) > 0.55).astype(np.float32)
    tone_a = np.sin(2 * np.pi * 55 * t).astype(np.float32)
    tone_b = np.sin(2 * np.pi * 220 * t * (1 + 0.02 * np.sin(2 * np.pi * 0.3 * t))).astype(np.float32)
    swell = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 8.0))
    burst = np.exp(-((t - 7.0) ** 2) / (2 * 0.6**2)) + np.exp(-((t - 16.5) ** 2) / (2 * 0.9**2))
    mono = (colored * 0.55 + noise * 0.12 + pulses * 0.35 + tone_a * 0.18 + tone_b * 0.08 * swell) * (
        0.45 + 0.55 * swell + 0.7 * burst
    )
    fade = np.clip(t / 0.2, 0, 1) * np.clip((seconds - t) / 0.3, 0, 1)
    mono = np.clip(mono * fade, -1.0, 1.0).astype(np.float32)
    stereo = np.stack([mono, np.roll(mono, int(sr * 0.002))], axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, sr, subtype="PCM_16")
    return path
