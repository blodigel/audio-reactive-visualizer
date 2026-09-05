from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from app.clips import suggest_clips
from app.config import config


class AudioError(ValueError):
    pass


AUDIO_EXT = {
    ".wav",
    ".wave",
    ".mp3",
    ".flac",
    ".aiff",
    ".aif",
    ".aifc",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wma",
    ".caf",
}


def _ffmpeg_bin() -> str:
    path = shutil.which(config.ffmpeg) or shutil.which("ffmpeg")
    if not path:
        raise AudioError("ffmpeg not found on PATH. Install ffmpeg or set FFMPEG=/path/to/ffmpeg")
    return path


def decode_to_wav(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_bin(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-map",
        "0:a:0",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise AudioError("Decoding timed out. Try a shorter file.") from exc
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 64:
        dest.unlink(missing_ok=True)
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        hint = err[-400:] if err else "unreadable file"
        raise AudioError(
            "Could not decode audio. Use WAV, MP3, FLAC, AIFF, M4A, AAC or OGG. "
            f"({hint})"
        )


def ingest_audio(src: Path, dest: Path) -> None:
    """Normalize any supported upload to 16-bit stereo PCM WAV at dest."""
    ext = src.suffix.lower()
    if ext in {".wav", ".wave"}:
        try:
            load_wav(src)
            if src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
            return
        except AudioError:
            pass
    decode_to_wav(src, dest)
    load_wav(dest)


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    try:
        data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    except Exception as exc:
        raise AudioError(f"Could not read WAV: {exc}") from exc
    if data.size == 0 or sr <= 0:
        raise AudioError("WAV file is empty or has an invalid sample rate")
    duration = data.shape[0] / sr
    if duration < 0.5:
        raise AudioError("Track is too short (need at least 0.5 seconds)")
    if duration > 30 * 60:
        raise AudioError("Track is longer than 30 minutes")
    np.clip(data, -1.0, 1.0, out=data)
    return data, int(sr)


def mono(data: np.ndarray) -> np.ndarray:
    return np.mean(data, axis=1, dtype=np.float32)


def waveform_peaks(samples: np.ndarray, buckets: int = 1800) -> dict[str, list[float]]:
    n = samples.shape[0]
    buckets = int(min(max(buckets, 64), n))
    # Vectorized min/max per bucket via pad + reshape when possible
    step = n / buckets
    mins = np.empty(buckets, dtype=np.float32)
    maxs = np.empty(buckets, dtype=np.float32)
    for i in range(buckets):
        a = int(i * step)
        b = int((i + 1) * step)
        if b <= a:
            b = min(a + 1, n)
        sl = samples[a:b]
        mins[i] = float(sl.min())
        maxs[i] = float(sl.max())
    return {"mins": mins.tolist(), "maxs": maxs.tolist(), "n": buckets}


def rms_envelope(
    samples: np.ndarray, sr: int, hop_s: float = 0.02, win_s: float = 0.05
) -> tuple[np.ndarray, np.ndarray]:
    hop = max(1, int(sr * hop_s))
    win = max(hop, int(sr * win_s))
    if samples.shape[0] < win:
        t = np.array([0.0], dtype=np.float32)
        r = np.array([float(np.sqrt(np.mean(samples * samples)))], dtype=np.float32)
        return t, r
    sq = samples.astype(np.float64) ** 2
    c = np.cumsum(sq, dtype=np.float64)
    starts = np.arange(0, samples.shape[0] - win, hop)
    ends = starts + win
    # c[i] = sum of sq[0..i]
    left = np.where(starts == 0, 0.0, c[starts - 1])
    means = (c[ends - 1] - left) / win
    rms = np.sqrt(np.maximum(means, 0.0)).astype(np.float32)
    times = ((starts + win / 2) / sr).astype(np.float32)
    return times, rms


def _norm(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x.astype(np.float32)
    p = float(np.percentile(x, 95))
    if p <= 1e-8:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip(x / p, 0.0, 1.5).astype(np.float32)


def spectral_features(samples: np.ndarray, sr: int, fps: int = 30) -> dict[str, Any]:
    hop = max(1, int(round(sr / fps)))
    nperseg = 2048
    if samples.shape[0] < nperseg:
        nperseg = int(2 ** max(8, math.floor(math.log2(max(16, samples.shape[0])))))
    noverlap = max(0, nperseg - hop)
    freqs, times, zxx = signal.stft(
        samples,
        fs=sr,
        nperseg=nperseg,
        noverlap=noverlap,
        boundary=None,
        padded=False,
    )
    mag = np.abs(zxx).astype(np.float32)
    if mag.size == 0:
        raise AudioError("Could not compute spectrum (file too short?)")

    def band(lo: float, hi: float) -> np.ndarray:
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            return np.zeros(mag.shape[1], dtype=np.float32)
        return _norm(mag[mask].mean(axis=0))

    flux = np.diff(mag, axis=1, prepend=mag[:, :1])
    flux = np.maximum(flux, 0.0).sum(axis=0)
    flux = _norm(flux)

    centroid_num = (freqs[:, None] * mag).sum(axis=0)
    centroid_den = mag.sum(axis=0) + 1e-8
    centroid = (centroid_num / centroid_den) / (sr / 2)

    # downsample spectrum to 64 bins for the circular viz
    n_spec = 64
    spec_bins = np.zeros((n_spec, mag.shape[1]), dtype=np.float32)
    n_use = max(1, mag.shape[0] // 2)  # drop mirrored nyquist half already; stft is one-sided
    edges = np.linspace(0, n_use, n_spec + 1).astype(int)
    for i in range(n_spec):
        a, b = edges[i], max(edges[i + 1], edges[i] + 1)
        spec_bins[i] = mag[a:b].mean(axis=0)
    spec_bins = _norm(spec_bins.ravel()).reshape(n_spec, -1)

    peaks, _ = signal.find_peaks(flux, height=0.32, distance=max(1, int(0.09 * fps)))
    onset_times = times[peaks].astype(np.float64).tolist() if peaks.size else []

    return {
        "times": times.astype(np.float32),
        "sub": band(20, 60),
        "bass": band(60, 250),
        "lowmid": band(250, 500),
        "mid": band(500, 2000),
        "highmid": band(2000, 6000),
        "high": band(6000, 12000),
        "air": band(12000, 20000),
        "flux": flux.astype(np.float32),
        "centroid": np.clip(centroid, 0, 1).astype(np.float32),
        "spec": spec_bins,
        "onset_times": onset_times,
    }


def analyze_file(
    path: Path,
    filename: str,
    track_id: str,
    clip_length: float = 15.0,
    clip_count: int = 3,
) -> dict[str, Any]:
    data, sr = load_wav(path)
    samples = mono(data)
    duration = float(samples.shape[0] / sr)
    env_t, env_rms = rms_envelope(samples, sr)
    spec = spectral_features(samples, sr, fps=30)
    onsets = spec["onset_times"]
    suggestions = suggest_clips(
        duration=duration,
        env_times=env_t,
        env_rms=env_rms,
        onset_times=np.asarray(onsets, dtype=np.float64),
        clip_len=clip_length,
        count=clip_count,
    )
    # downsample envelope for the UI (~8 points/sec max 4000)
    max_pts = 4000
    if env_t.shape[0] > max_pts:
        idx = np.linspace(0, env_t.shape[0] - 1, max_pts).astype(int)
        env_t_ui = env_t[idx]
        env_rms_ui = env_rms[idx]
    else:
        env_t_ui, env_rms_ui = env_t, env_rms

    return {
        "id": track_id,
        "filename": filename,
        "duration": duration,
        "sample_rate": sr,
        "channels": int(data.shape[1]),
        "samples": int(data.shape[0]),
        "waveform": waveform_peaks(samples),
        "envelope": {
            "times": env_t_ui.tolist(),
            "rms": env_rms_ui.tolist(),
        },
        "onsets": onsets,
        "suggestions": suggestions,
    }


def window_stereo(
    data: np.ndarray, sr: int, t: float, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return n samples of L/R centered at time t, padded if needed."""
    center = int(t * sr)
    half = n // 2
    start = center - half
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)
    src_l = data[:, 0]
    src_r = data[:, 0] if data.shape[1] < 2 else data[:, 1]
    if data.shape[1] < 2:
        src_r = np.roll(src_l, max(1, int(sr * 0.002)))
    a = max(0, start)
    b = min(data.shape[0], start + n)
    da = a - start
    sl = src_l[a:b]
    sr_ = src_r[a:b]
    left[da : da + sl.shape[0]] = sl
    right[da : da + sr_.shape[0]] = sr_
    return left, right


def interp_feat(times: np.ndarray, values: np.ndarray, t: float) -> float:
    if times.size == 0:
        return 0.0
    return float(np.interp(t, times, values))


def interp_spec(times: np.ndarray, spec: np.ndarray, t: float) -> np.ndarray:
    """Linear interpolate 64-bin spectrum at time t. spec is (64, T)."""
    if times.size == 1:
        return spec[:, 0]
    if t <= times[0]:
        return spec[:, 0]
    if t >= times[-1]:
        return spec[:, -1]
    i = int(np.searchsorted(times, t) - 1)
    i = max(0, min(i, times.size - 2))
    span = float(times[i + 1] - times[i]) or 1.0
    u = (t - float(times[i])) / span
    return spec[:, i] * (1 - u) + spec[:, i + 1] * u
