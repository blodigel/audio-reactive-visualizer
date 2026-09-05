from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
]
FormatId = Literal["reels", "square", "portrait", "landscape"]
QualityId = Literal["draft", "standard", "high"]
TextPosition = Literal["top", "center", "lower"]


class ClipIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def order(self) -> ClipIn:
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        if self.end - self.start < 0.5:
            raise ValueError("Clip must be at least 0.5 seconds")
        if self.end - self.start > 90:
            raise ValueError("Clip cannot be longer than 90 seconds (Reels limit)")
        return self


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
    text_size: float = Field(default=0.65, ge=0.2, le=1.5)
    text_opacity: float = Field(default=0.92, ge=0, le=1)
    seed: int = Field(default=1, ge=0, le=1_000_000)

    @field_validator("text", "subtext")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("bg_color", "effect_color", "text_color")
    @classmethod
    def colors(cls, v: str) -> str:
        return _hex_color(v)

    @field_validator("background_id")
    @classmethod
    def bg_id(cls, v: str) -> str:
        raw = v.strip()
        if not raw:
            return ""
        if not re.fullmatch(r"[a-fA-F0-9]{12,32}", raw):
            raise ValueError("Invalid background id")
        return raw.lower()


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
