from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.fonts import FONT_IDS

SceneId = Literal[
    "auto",
    "oscilloscope",
    "lissajous",
    "spectrum",
    "tunnel",
    "field",
    "particles",
    "bars",
    "mixed",
    "starburst",
    "grid",
    "kaleido",
    "orbits",
]
FormatId = Literal["reels", "square", "portrait", "landscape"]
QualityId = Literal["draft", "standard", "high"]
TextPosition = Literal["top", "center", "lower"]
LogoPosition = Literal["above-text", "top-left", "top-right", "lower-left", "lower-right"]


_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _hex_color(value: str) -> str:
    raw = value.strip()
    if not _HEX.match(raw):
        raise ValueError("Color must be #RRGGBB")
    if not raw.startswith("#"):
        raw = "#" + raw
    return raw.lower()


class VisualSettings(BaseModel):
    scene: SceneId = "mixed"
    bg_color: str = "#050303"
    effect_color: str = "#d63d24"
    text_color: str = "#ede6dc"
    background_id: str = ""
    font: str = "archivo"
    font_id: str = ""
    logo_id: str = ""
    logo_position: LogoPosition = "above-text"
    logo_size: float = Field(default=0.18, ge=0.06, le=0.55)
    logo_opacity: float = Field(default=1.0, ge=0, le=1)
    logo_glow: float = Field(default=0.0, ge=0, le=1)
    logo_glitch: float = Field(default=0.0, ge=0, le=1)
    logo_chroma: float = Field(default=0.0, ge=0, le=1)
    logo_jitter: float = Field(default=0.0, ge=0, le=1)
    bg_opacity: float = Field(default=0.22, ge=0, le=1)
    format: FormatId = "reels"
    quality: QualityId = "standard"
    fps: int = Field(default=30, ge=12, le=60)
    grain: float = Field(default=0.45, ge=0, le=1)
    jitter: float = Field(default=0.30, ge=0, le=1)
    bloom: float = Field(default=0.25, ge=0, le=1)
    intensity: float = Field(default=0.75, ge=0, le=1)
    glitch: float = Field(default=0.35, ge=0, le=1)
    scanlines: float = Field(default=0.50, ge=0, le=1)
    vignette: float = Field(default=0.70, ge=0, le=1)
    chromatic: float = Field(default=0.20, ge=0, le=1)
    trail: float = Field(default=0.40, ge=0, le=1)
    reactivity: float = Field(default=0.85, ge=0, le=1)
    text: str = Field(default="", max_length=80)
    subtext: str = Field(default="", max_length=80)
    text_position: TextPosition = "lower"
    text_y: float = Field(default=0.86, ge=0.06, le=0.94)
    text_size: float = Field(default=0.65, ge=0.2, le=1.5)
    text_opacity: float = Field(default=0.92, ge=0, le=1)
    text_glow: float = Field(default=0.0, ge=0, le=1)
    text_glitch: float = Field(default=0.0, ge=0, le=1)
    text_chroma: float = Field(default=0.0, ge=0, le=1)
    text_jitter: float = Field(default=0.0, ge=0, le=1)
    seed: int = Field(default=1, ge=0, le=1_000_000)

    @field_validator("text", "subtext")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("bg_color", "effect_color", "text_color")
    @classmethod
    def colors(cls, v: str) -> str:
        return _hex_color(v)

    @field_validator("background_id", "font_id", "logo_id")
    @classmethod
    def asset_id(cls, v: str) -> str:
        raw = v.strip()
        if not raw:
            return ""
        if not re.fullmatch(r"[a-fA-F0-9]{12,32}", raw):
            raise ValueError("Invalid asset id")
        return raw.lower()

    @field_validator("font")
    @classmethod
    def font_ok(cls, v: str) -> str:
        raw = v.strip().lower()
        if raw in FONT_IDS or raw == "custom":
            return raw
        raise ValueError("Unknown font")


class ClipIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    fade_in: float = Field(default=0.0, ge=0, le=30)
    fade_out: float = Field(default=0.0, ge=0, le=30)
    settings: VisualSettings | None = None

    @model_validator(mode="after")
    def order(self) -> ClipIn:
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        if self.end - self.start < 0.5:
            raise ValueError("Clip must be at least 0.5 seconds")
        if self.end - self.start > 90:
            raise ValueError("Clip cannot be longer than 90 seconds (Reels limit)")
        return self


class SuggestIn(BaseModel):
    count: int = Field(default=3, ge=1, le=8)
    length: float = Field(default=15.0, ge=1.0, le=90.0)


class RenderRequest(BaseModel):
    track_id: str
    clips: list[ClipIn] = Field(min_length=1, max_length=8)
    settings: VisualSettings = Field(default_factory=VisualSettings)


class ClipOut(BaseModel):
    start: float
    end: float
    score: float = 0.0
    reason: str = ""


class TrackOut(BaseModel):
    id: str
    filename: str
    duration: float
    sample_rate: int
    channels: int
    samples: int
    waveform: dict
    envelope: dict
    onsets: list[float]
    suggestions: list[ClipOut]


class JobFileOut(BaseModel):
    name: str
    clip_index: int
    start: float
    end: float
    bytes: int = 0


class JobOut(BaseModel):
    id: str
    status: str
    progress: float
    message: str
    track_id: str
    outputs: list[JobFileOut] = Field(default_factory=list)
    error: str | None = None
