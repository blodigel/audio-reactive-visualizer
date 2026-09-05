from app.audio import analyze_file, load_wav, mono, waveform_peaks, rms_envelope


def test_load_and_duration(wav_path):
    data, sr = load_wav(wav_path)
    assert sr == 22050
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert abs(data.shape[0] / sr - 8.0) < 0.05


def test_analyze_has_suggestions(wav_path):
    meta = analyze_file(wav_path, filename="track.wav", track_id="abc", clip_length=2.0, clip_count=2)
    assert meta["duration"] > 7
    assert meta["waveform"]["n"] > 100
    assert len(meta["waveform"]["mins"]) == meta["waveform"]["n"]
    assert len(meta["suggestions"]) >= 1
    for c in meta["suggestions"]:
        assert 0 <= c["start"] < c["end"] <= meta["duration"] + 0.05


def test_peaks_and_envelope(wav_path):
    data, sr = load_wav(wav_path)
    m = mono(data)
    peaks = waveform_peaks(m, buckets=200)
    assert peaks["n"] == 200
    times, rms = rms_envelope(m, sr)
    assert times.shape == rms.shape
    assert rms.max() > 0
