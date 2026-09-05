from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

from app.config import config

BUNDLED_DIR = Path(__file__).resolve().parent / "static" / "fonts"
ALLOWED_FONT_EXT = {".ttf", ".otf"}
MAX_FONT_BYTES = 8 * 1024 * 1024

BUNDLED: list[dict] = [
    {
        "id": "archivo",
        "label": "Archivo",
        "family": "Archivo Black",
        "file": "ArchivoBlack-Regular.ttf",
        "tracking": 0.08,
        "blurb": "Heavy grotesk — default titles.",
    },
    {
        "id": "bebas",
        "label": "Bebas",
        "family": "Bebas Neue",
        "file": "BebasNeue-Regular.ttf",
        "tracking": 0.10,
        "blurb": "Condensed display caps.",
    },
    {
        "id": "mono",
        "label": "Tech Mono",
        "family": "Share Tech Mono",
        "file": "ShareTechMono-Regular.ttf",
        "tracking": 0.08,
        "blurb": "Industrial mono.",
    },
    {
        "id": "typewriter",
        "label": "Elite",
        "family": "Special Elite",
        "file": "SpecialElite-Regular.ttf",
        "tracking": 0.05,
        "blurb": "Worn typewriter.",
    },
    {
        "id": "rocker",
        "label": "Rocker",
        "family": "New Rocker",
        "file": "NewRocker-Regular.ttf",
        "tracking": 0.04,
        "blurb": "Metal display.",
    },
    {
        "id": "blackletter",
        "label": "Fraktur",
        "family": "UnifrakturMaguntia",
        "file": "UnifrakturMaguntia-Book.ttf",
        "tracking": 0.02,
        "blurb": "Blackletter.",
    },
    {
        "id": "glitch",
        "label": "Glitch",
        "family": "Rubik Glitch",
        "file": "RubikGlitch-Regular.ttf",
        "tracking": 0.04,
        "blurb": "Broken grotesk.",
    },
]

FONT_IDS = tuple(item["id"] for item in BUNDLED)
_BY_ID = {item["id"]: item for item in BUNDLED}


class FontError(ValueError):
    pass


def bundled_path(font_id: str) -> Path | None:
    meta = _BY_ID.get(font_id)
    if not meta:
        return None
    path = BUNDLED_DIR / meta["file"]
    return path if path.is_file() else None


def custom_path(font_id: str) -> Path | None:
    if not font_id:
        return None
    for ext in (".ttf", ".otf"):
        path = config.fonts_dir / f"{font_id}{ext}"
        if path.is_file():
            return path
    return None


def font_meta(font_id: str) -> dict:
    return _BY_ID.get(font_id) or _BY_ID["archivo"]


def resolve_font(settings_font: str, custom_id: str = "") -> tuple[Path | None, float]:
    """Return (path, tracking). Custom upload wins when present."""
    if custom_id:
        path = custom_path(custom_id)
        if path is not None:
            return path, 0.06
    path = bundled_path(settings_font if settings_font in _BY_ID else "archivo")
    if path is None:
        path = bundled_path("archivo")
    tracking = float(font_meta(settings_font if settings_font in _BY_ID else "archivo")["tracking"])
    return path, tracking


def load_truetype(path: Path | None, size: int) -> ImageFont.ImageFont:
    if path and path.is_file():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    fallback = bundled_path("archivo")
    if fallback and fallback.is_file():
        try:
            return ImageFont.truetype(str(fallback), size)
        except Exception:
            pass
    sys_path = find_system_font()
    if sys_path:
        try:
            return ImageFont.truetype(str(sys_path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def find_font() -> Path | None:
    return bundled_path("archivo") or find_system_font()


def find_system_font() -> Path | None:
    for path in (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ):
        if path.is_file():
            return path
    return None


def save_font(src: Path, dest: Path) -> str:
    try:
        font = ImageFont.truetype(str(src), 32)
        family, style = font.getname()
        name = family if not style or style == "Regular" else f"{family} {style}"
    except Exception as exc:
        raise FontError(f"Could not read font: {exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    return name.strip() or dest.stem


def public_fonts() -> list[dict]:
    out = []
    for item in BUNDLED:
        path = BUNDLED_DIR / item["file"]
        if not path.is_file():
            continue
        out.append(
            {
                "id": item["id"],
                "label": item["label"],
                "family": item["family"],
                "tracking": item["tracking"],
                "blurb": item["blurb"],
                "url": f"/static/fonts/{item['file']}",
            }
        )
    return out
