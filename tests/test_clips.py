import numpy as np

from app.clips import suggest_clips


def test_short_track_is_full():
    t = np.linspace(0, 4, 200)
    rms = np.ones_like(t)
    out = suggest_clips(4.0, t, rms, np.array([]), clip_len=15.0, count=3)
    assert len(out) == 1
    assert out[0]["reason"] == "full track"


def test_picks_non_overlapping():
    duration = 60.0
    t = np.linspace(0, duration, 3000)
    rms = np.zeros_like(t)
    # three hot spots
    for center in (8.0, 30.0, 50.0):
        rms += np.exp(-((t - center) ** 2) / (2 * 1.5**2))
    onsets = np.array([7.2, 8.1, 29.4, 30.2, 49.5, 50.1])
    out = suggest_clips(duration, t, rms, onsets, clip_len=6.0, count=3, min_gap=1.0)
    assert len(out) == 3
    out = sorted(out, key=lambda c: c["start"])
    for a, b in zip(out, out[1:]):
        assert b["start"] >= a["end"] + 1.0 - 1e-6
