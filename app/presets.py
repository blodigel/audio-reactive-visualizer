from __future__ import annotations

from typing import Any

from app.models import FormatId, GenreId, SceneId, VisualSettings

FORMATS: dict[FormatId, dict[str, Any]] = {
    "reels": {
        "label": "Reels / Shorts",
        "ratio": "9:16",
        "size": (1080, 1920),
        "note": "Instagram Reels, TikTok, YouTube Shorts",
    },
    "square": {
        "label": "Square",
        "ratio": "1:1",
        "size": (1080, 1080),
        "note": "Feed post",
    },
    "portrait": {
        "label": "Portrait",
        "ratio": "4:5",
        "size": (1080, 1350),
        "note": "Instagram portrait post",
    },
    "landscape": {
        "label": "Landscape",
        "ratio": "16:9",
        "size": (1920, 1080),
        "note": "YouTube / wide",
    },
}

QUALITY_SCALE = {
    "draft": 0.5,
    "standard": 1.0,
    "high": 1.0,
}

QUALITY_CRF = {
    "draft": 23,
    "standard": 19,
    "high": 16,
}

QUALITY_PRESET = {
    "draft": "veryfast",
    "standard": "veryfast",
    "high": "fast",
}

# RGB 0-1
Palette = dict[str, tuple[float, float, float]]

PALETTES: dict[GenreId, Palette] = {
    "noise": {
        "bg": (0.018, 0.012, 0.010),
        "fg": (0.84, 0.24, 0.14),
        "accent": (0.93, 0.86, 0.76),
        "fog": (0.14, 0.04, 0.03),
        "dim": (0.28, 0.09, 0.06),
    },
    "dark_ambient": {
        "bg": (0.010, 0.016, 0.032),
        "fg": (0.28, 0.58, 0.64),
        "accent": (0.62, 0.38, 0.78),
        "fog": (0.04, 0.09, 0.16),
        "dim": (0.10, 0.20, 0.28),
    },
    "industrial": {
        "bg": (0.012, 0.012, 0.012),
        "fg": (0.92, 0.90, 0.86),
        "accent": (0.95, 0.42, 0.10),
        "fog": (0.10, 0.09, 0.08),
        "dim": (0.35, 0.32, 0.28),
    },
    "drone": {
        "bg": (0.012, 0.014, 0.018),
        "fg": (0.55, 0.62, 0.58),
        "accent": (0.78, 0.72, 0.48),
        "fog": (0.06, 0.08, 0.10),
        "dim": (0.18, 0.22, 0.24),
    },
    "black_metal": {
        "bg": (0.008, 0.008, 0.008),
        "fg": (0.92, 0.92, 0.90),
        "accent": (0.70, 0.08, 0.08),
        "fog": (0.08, 0.08, 0.08),
        "dim": (0.28, 0.28, 0.28),
    },
    "techno": {
        "bg": (0.010, 0.010, 0.018),
        "fg": (0.20, 0.92, 0.88),
        "accent": (0.92, 0.18, 0.62),
        "fog": (0.04, 0.06, 0.14),
        "dim": (0.12, 0.22, 0.32),
    },
    "experimental": {
        "bg": (0.016, 0.010, 0.022),
        "fg": (0.55, 0.95, 0.40),
        "accent": (0.95, 0.35, 0.85),
        "fog": (0.10, 0.04, 0.14),
        "dim": (0.30, 0.12, 0.28),
    },
    "shoegaze": {
        "bg": (0.030, 0.018, 0.028),
        "fg": (0.92, 0.55, 0.68),
        "accent": (0.62, 0.72, 0.95),
        "fog": (0.16, 0.08, 0.14),
        "dim": (0.40, 0.22, 0.32),
    },
}

GENRE_SCENE: dict[GenreId, SceneId] = {
    "noise": "mixed",
    "dark_ambient": "spectrum",
    "industrial": "bars",
    "drone": "field",
    "black_metal": "oscilloscope",
    "techno": "tunnel",
    "experimental": "lissajous",
    "shoegaze": "particles",
}

GENRE_LOOK: dict[GenreId, dict[str, float]] = {
    "noise": {
        "grain": 0.48,
        "jitter": 0.32,
        "bloom": 0.22,
        "intensity": 0.78,
        "glitch": 0.38,
        "scanlines": 0.52,
        "vignette": 0.72,
        "chromatic": 0.22,
        "trail": 0.42,
        "reactivity": 0.88,
        "crush": 0.08,
        "contrast": 1.28,
        "swirl": 0.25,
    },
    "dark_ambient": {
        "grain": 0.22,
        "jitter": 0.08,
        "bloom": 0.55,
        "intensity": 0.55,
        "glitch": 0.05,
        "scanlines": 0.18,
        "vignette": 0.78,
        "chromatic": 0.12,
        "trail": 0.62,
        "reactivity": 0.45,
        "crush": 0.04,
        "contrast": 1.05,
        "swirl": 0.55,
    },
    "industrial": {
        "grain": 0.28,
        "jitter": 0.42,
        "bloom": 0.18,
        "intensity": 0.92,
        "glitch": 0.48,
        "scanlines": 0.35,
        "vignette": 0.55,
        "chromatic": 0.18,
        "trail": 0.18,
        "reactivity": 0.95,
        "crush": 0.05,
        "contrast": 1.35,
        "swirl": 0.10,
    },
    "drone": {
        "grain": 0.30,
        "jitter": 0.06,
        "bloom": 0.40,
        "intensity": 0.50,
        "glitch": 0.04,
        "scanlines": 0.22,
        "vignette": 0.80,
        "chromatic": 0.08,
        "trail": 0.72,
        "reactivity": 0.35,
        "crush": 0.06,
        "contrast": 1.08,
        "swirl": 0.70,
    },
    "black_metal": {
        "grain": 0.55,
        "jitter": 0.22,
        "bloom": 0.10,
        "intensity": 0.82,
        "glitch": 0.22,
        "scanlines": 0.40,
        "vignette": 0.85,
        "chromatic": 0.06,
        "trail": 0.28,
        "reactivity": 0.80,
        "crush": 0.12,
        "contrast": 1.45,
        "swirl": 0.15,
    },
    "techno": {
        "grain": 0.12,
        "jitter": 0.18,
        "bloom": 0.48,
        "intensity": 0.85,
        "glitch": 0.12,
        "scanlines": 0.08,
        "vignette": 0.50,
        "chromatic": 0.28,
        "trail": 0.35,
        "reactivity": 1.00,
        "crush": 0.02,
        "contrast": 1.18,
        "swirl": 0.40,
    },
    "experimental": {
        "grain": 0.40,
        "jitter": 0.35,
        "bloom": 0.32,
        "intensity": 0.80,
        "glitch": 0.62,
        "scanlines": 0.28,
        "vignette": 0.48,
        "chromatic": 0.45,
        "trail": 0.38,
        "reactivity": 0.90,
        "crush": 0.03,
        "contrast": 1.20,
        "swirl": 0.45,
    },
    "shoegaze": {
        "grain": 0.18,
        "jitter": 0.10,
        "bloom": 0.78,
        "intensity": 0.62,
        "glitch": 0.04,
        "scanlines": 0.12,
        "vignette": 0.60,
        "chromatic": 0.32,
        "trail": 0.80,
        "reactivity": 0.50,
        "crush": 0.01,
        "contrast": 0.95,
        "swirl": 0.60,
    },
}

GENRE_META: dict[GenreId, dict[str, str]] = {
    "noise": {
        "label": "Noise",
        "blurb": "Crushed blacks, analog snow, rust and bone. Default for harsh / experimental.",
    },
    "dark_ambient": {
        "label": "Dark ambient",
        "blurb": "Slow fog, deep teal and violet, soft bloom.",
    },
    "industrial": {
        "label": "Industrial",
        "blurb": "Hard transients, strobe, metal on black.",
    },
    "drone": {
        "label": "Drone",
        "blurb": "Long trails, slow field, almost still.",
    },
    "black_metal": {
        "label": "Black metal",
        "blurb": "High-contrast frost, bone white, blood flash.",
    },
    "techno": {
        "label": "Techno",
        "blurb": "Beat-locked geometry, cyan / magenta punch.",
    },
    "experimental": {
        "label": "Experimental",
        "blurb": "Glitch, channel-split, unstable color.",
    },
    "shoegaze": {
        "label": "Shoegaze",
        "blurb": "Washed bloom, smear, pastel on dusk.",
    },
}

SCENE_META: dict[SceneId, dict[str, str]] = {
    "auto": {"label": "Auto", "blurb": "Scene follows the genre."},
    "oscilloscope": {"label": "Scope", "blurb": "Classic waveform trace."},
    "lissajous": {"label": "Lissajous", "blurb": "Stereo X/Y figure."},
    "spectrum": {"label": "Spectrum", "blurb": "Circular frequency ring."},
    "tunnel": {"label": "Tunnel", "blurb": "Concentric beat rings."},
    "field": {"label": "Field", "blurb": "Warped analog plasma."},
    "particles": {"label": "Particles", "blurb": "Sparks that explode on hits."},
    "bars": {"label": "Bars", "blurb": "Harsh spectral columns."},
    "mixed": {"label": "Mixed", "blurb": "Field + scope + particles."},
}


def resolved_scene(settings: VisualSettings) -> SceneId:
    if settings.scene != "auto":
        return settings.scene
    return GENRE_SCENE[settings.genre]


def output_size(fmt: FormatId, quality: str) -> tuple[int, int]:
    w, h = FORMATS[fmt]["size"]
    scale = QUALITY_SCALE.get(quality, 1.0)
    w = int(w * scale)
    h = int(h * scale)
    w -= w % 2
    h -= h % 2
    return max(w, 2), max(h, 2)


def settings_from_genre(genre: GenreId) -> VisualSettings:
    look = GENRE_LOOK[genre]
    payload = {k: look[k] for k in VisualSettings.model_fields if k in look}
    payload["genre"] = genre
    payload["scene"] = "auto"
    return VisualSettings(**payload)


def public_catalog() -> dict[str, Any]:
    genres = []
    for gid, meta in GENRE_META.items():
        look = GENRE_LOOK[gid]
        genres.append(
            {
                "id": gid,
                "label": meta["label"],
                "blurb": meta["blurb"],
                "scene": GENRE_SCENE[gid],
                "defaults": {k: look[k] for k in (
                    "grain",
                    "jitter",
                    "bloom",
                    "intensity",
                    "glitch",
                    "scanlines",
                    "vignette",
                    "chromatic",
                    "trail",
                    "reactivity",
                )},
                "palette": {k: list(v) for k, v in PALETTES[gid].items()},
            }
        )
    return {
        "genres": genres,
        "scenes": [{"id": k, **v} for k, v in SCENE_META.items()],
        "formats": [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "size"}, "width": v["size"][0], "height": v["size"][1]} for k, v in FORMATS.items()],
        "qualities": [
            {"id": "draft", "label": "Draft", "blurb": "Half-res, faster preview encode."},
            {"id": "standard", "label": "Standard", "blurb": "1080, good for posting."},
            {"id": "high", "label": "High", "blurb": "1080, slower, cleaner encode."},
        ],
        "sliders": [
            {"key": "grain", "label": "Grain", "blurb": "Film grain / analog snow"},
            {"key": "jitter", "label": "Jitter", "blurb": "Frame shake, bass-linked"},
            {"key": "bloom", "label": "Bloom", "blurb": "Glow on highlights"},
            {"key": "intensity", "label": "Intensity", "blurb": "How hard the viz draws"},
            {"key": "glitch", "label": "Glitch", "blurb": "Tears and slice offsets on hits"},
            {"key": "scanlines", "label": "Scanlines", "blurb": "CRT line structure"},
            {"key": "vignette", "label": "Vignette", "blurb": "Edge crush"},
            {"key": "chromatic", "label": "Chroma", "blurb": "RGB channel split"},
            {"key": "trail", "label": "Trail", "blurb": "Phosphor persistence"},
            {"key": "reactivity", "label": "Reactivity", "blurb": "How tightly it follows the audio"},
        ],
    }
