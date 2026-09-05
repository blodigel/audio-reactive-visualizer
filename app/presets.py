from __future__ import annotations

import re
from typing import Any

from app.fonts import public_fonts
from app.models import FormatId, SceneId, VisualSettings

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

LOOK = {
    "crush": 0.08,
    "contrast": 1.28,
    "swirl": 0.25,
}

HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")

COLOR_PRESETS: list[dict[str, str]] = [
    {"id": "rust", "label": "Rust", "bg_color": "#050303", "effect_color": "#d63d24", "text_color": "#ede6dc"},
    {"id": "bone", "label": "Bone", "bg_color": "#0c0b0a", "effect_color": "#e8c9a8", "text_color": "#f4eee6"},
    {"id": "ice", "label": "Ice", "bg_color": "#03050c", "effect_color": "#47a4b3", "text_color": "#dce8f0"},
    {"id": "blood", "label": "Blood", "bg_color": "#080808", "effect_color": "#c41414", "text_color": "#f0f0ee"},
    {"id": "acid", "label": "Acid", "bg_color": "#040306", "effect_color": "#8cf266", "text_color": "#f2e6ff"},
    {"id": "cyan", "label": "Cyan", "bg_color": "#030305", "effect_color": "#33ebe0", "text_color": "#f2e6f0"},
    {"id": "violet", "label": "Violet", "bg_color": "#08050c", "effect_color": "#9e61c7", "text_color": "#ede6dc"},
    {"id": "white", "label": "White", "bg_color": "#020202", "effect_color": "#ebebe6", "text_color": "#c4452e"},
]

SCENE_META: dict[SceneId, dict[str, str]] = {
    "mixed": {"label": "Mixed", "blurb": "Field + scope + particles."},
    "oscilloscope": {"label": "Scope", "blurb": "Classic waveform trace."},
    "lissajous": {"label": "Lissajous", "blurb": "Stereo X/Y figure."},
    "spectrum": {"label": "Spectrum", "blurb": "Circular frequency ring."},
    "tunnel": {"label": "Tunnel", "blurb": "Concentric beat rings."},
    "field": {"label": "Field", "blurb": "Warped analog plasma."},
    "particles": {"label": "Particles", "blurb": "Sparks that explode on hits."},
    "bars": {"label": "Bars", "blurb": "Harsh spectral columns."},
    "starburst": {"label": "Starburst", "blurb": "Radial rays from the spectrum."},
    "grid": {"label": "Grid", "blurb": "Warped wireframe, bass-punched."},
    "kaleido": {"label": "Kaleido", "blurb": "Six-fold mirrored lissajous."},
    "orbits": {"label": "Orbits", "blurb": "Rings of dots locked to the beat."},
}


def normalize_hex(value: str) -> str:
    raw = value.strip()
    if not HEX_RE.match(raw):
        raise ValueError("Color must be #RRGGBB")
    if not raw.startswith("#"):
        raw = "#" + raw
    return raw.lower()


def parse_hex(value: str) -> tuple[float, float, float]:
    h = normalize_hex(value)[1:]
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b)


def _mix(
    a: tuple[float, float, float], b: tuple[float, float, float], t: float
) -> tuple[float, float, float]:
    return (
        a[0] * (1 - t) + b[0] * t,
        a[1] * (1 - t) + b[1] * t,
        a[2] * (1 - t) + b[2] * t,
    )


def palette_from_settings(settings: VisualSettings) -> dict[str, tuple[float, float, float]]:
    bg = parse_hex(settings.bg_color)
    fg = parse_hex(settings.effect_color)
    text = parse_hex(settings.text_color)
    fog = _mix(bg, fg, 0.22)
    fog = tuple(min(c, 0.28) for c in fog)  # type: ignore[assignment]
    dim = _mix(bg, fg, 0.42)
    return {"bg": bg, "fg": fg, "accent": text, "fog": fog, "dim": dim}


def resolved_scene(settings: VisualSettings) -> SceneId:
    if settings.scene == "auto":
        return "mixed"
    return settings.scene


def output_size(fmt: FormatId, quality: str) -> tuple[int, int]:
    w, h = FORMATS[fmt]["size"]
    scale = QUALITY_SCALE.get(quality, 1.0)
    w = int(w * scale)
    h = int(h * scale)
    w -= w % 2
    h -= h % 2
    return max(w, 2), max(h, 2)


def public_catalog() -> dict[str, Any]:
    return {
        "palettes": COLOR_PRESETS,
        "scenes": [{"id": k, **v} for k, v in SCENE_META.items()],
        "formats": [
            {
                "id": k,
                **{kk: vv for kk, vv in v.items() if kk != "size"},
                "width": v["size"][0],
                "height": v["size"][1],
            }
            for k, v in FORMATS.items()
        ],
        "qualities": [
            {"id": "draft", "label": "Draft", "blurb": "Half-res, faster preview encode."},
            {"id": "standard", "label": "Standard", "blurb": "1080, good for posting."},
            {"id": "high", "label": "High", "blurb": "1080, slower, cleaner encode."},
        ],
        "sliders": [
            {"key": "bg_opacity", "label": "BG tint", "blurb": "Color wash over an imported background. 0 = photo only."},
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
        "fonts": public_fonts(),
        "logo_positions": [
            {"id": "above-text", "label": "Above text"},
            {"id": "top-left", "label": "Top left"},
            {"id": "top-right", "label": "Top right"},
            {"id": "lower-left", "label": "Lower left"},
            {"id": "lower-right", "label": "Lower right"},
        ],
        "defaults": {
            "bg_color": COLOR_PRESETS[0]["bg_color"],
            "effect_color": COLOR_PRESETS[0]["effect_color"],
            "text_color": COLOR_PRESETS[0]["text_color"],
            "scene": "mixed",
            "font": "archivo",
        },
    }
