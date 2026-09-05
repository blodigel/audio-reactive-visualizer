from __future__ import annotations

import numpy as np


def suggest_clips(
    duration: float,
    env_times: np.ndarray,
    env_rms: np.ndarray,
    onset_times: np.ndarray,
    clip_len: float = 15.0,
    count: int = 3,
    min_gap: float = 1.0,
) -> list[dict]:
    """Pick non-overlapping windows with high energy, dynamics and transients."""
    if duration <= 0:
        return []
    clip_len = float(min(clip_len, duration))
    if duration <= clip_len + 0.05:
        return [
            {
                "start": 0.0,
                "end": round(duration, 3),
                "score": 1.0,
                "reason": "full track",
            }
        ]

    step = 0.5
    starts = np.arange(0.0, max(duration - clip_len, 0.0001), step, dtype=np.float64)
    if starts.size == 0:
        return [
            {
                "start": 0.0,
                "end": round(duration, 3),
                "score": 1.0,
                "reason": "full track",
            }
        ]

    scores = np.zeros(starts.size, dtype=np.float64)
    reasons = ["energy"] * starts.size
    env_times = np.asarray(env_times, dtype=np.float64)
    env_rms = np.asarray(env_rms, dtype=np.float64)
    onset_times = np.asarray(onset_times, dtype=np.float64)

    for i, s in enumerate(starts):
        e = s + clip_len
        m = (env_times >= s) & (env_times < e)
        rms = env_rms[m]
        if rms.size < 4:
            continue
        mean = float(rms.mean())
        var = float(rms.var())
        peak = float(rms.max())
        n_on = int(np.count_nonzero((onset_times >= s) & (onset_times < e))) if onset_times.size else 0
        onset_rate = n_on / clip_len
        silence = float((rms < 0.02).mean())
        energy_term = mean * 1.5
        dyn_term = var * 3.0
        peak_term = peak * 0.7
        onset_term = onset_rate * 0.55
        scores[i] = (energy_term + dyn_term + peak_term + onset_term) * (1.0 - 0.88 * silence)
        if dyn_term >= energy_term and dyn_term >= onset_term:
            reasons[i] = "dynamic"
        elif onset_term >= energy_term:
            reasons[i] = "transients"
        elif silence < 0.15 and mean > 0:
            reasons[i] = "high energy"

    order = np.argsort(scores)[::-1]
    picked: list[dict] = []
    for idx in order:
        if scores[idx] <= 0:
            break
        s = float(starts[idx])
        e = float(s + clip_len)
        overlap = False
        for p in picked:
            if not (e + min_gap <= p["start"] or s >= p["end"] + min_gap):
                overlap = True
                break
        if overlap:
            continue
        picked.append(
            {
                "start": round(s, 3),
                "end": round(e, 3),
                "score": round(float(scores[idx]), 4),
                "reason": reasons[int(idx)],
            }
        )
        if len(picked) >= count:
            break

    if not picked:
        # fall back to evenly spaced
        if count == 1:
            mid = max(0.0, (duration - clip_len) / 2)
            picked = [
                {
                    "start": round(mid, 3),
                    "end": round(mid + clip_len, 3),
                    "score": 0.0,
                    "reason": "center",
                }
            ]
        else:
            span = duration - clip_len
            for k in range(count):
                s = 0.0 if count == 1 else span * k / (count - 1)
                picked.append(
                    {
                        "start": round(float(s), 3),
                        "end": round(float(s + clip_len), 3),
                        "score": 0.0,
                        "reason": "spaced",
                    }
                )
    picked.sort(key=lambda c: c["start"])
    return picked


def clamp_clip(start: float, end: float, duration: float) -> tuple[float, float]:
    start = max(0.0, min(start, duration - 0.5))
    end = max(start + 0.5, min(end, duration))
    return start, end
