from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.audio import interp_feat, interp_spec, window_stereo
from app.fonts import load_truetype, resolve_font
from app.logos import apply_logo
from app.models import VisualSettings
from app.presets import LOOK, palette_from_settings, resolved_scene


def _col(rgb: tuple[float, float, float], scale: float = 255.0) -> tuple[int, int, int]:
    return (
        int(np.clip(rgb[2] * scale, 0, 255)),  # BGR for cv2
        int(np.clip(rgb[1] * scale, 0, 255)),
        int(np.clip(rgb[0] * scale, 0, 255)),
    )


def _rgb(rgb: tuple[float, float, float]) -> np.ndarray:
    return np.array(rgb, dtype=np.float32)


def make_vignette(h: int, w: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    ry, rx = h * 0.62, w * 0.62
    v = 1.0 - ((xx - cx) ** 2 / (rx * rx) + (yy - cy) ** 2 / (ry * ry))
    v = np.clip(v, 0.0, 1.0) ** 0.9
    return v.astype(np.float32)


def make_noise_tex(rng: np.random.Generator, size: int = 256) -> np.ndarray:
    base = rng.random((size, size), dtype=np.float32)
    # cheap blur via cv2 for analog grain clumps
    u8 = (base * 255).astype(np.uint8)
    u8 = cv2.GaussianBlur(u8, (0, 0), 1.2)
    return u8.astype(np.float32) / 255.0


def sample_tex(tex: np.ndarray, h: int, w: int, t: float, scale: float, ox: float, oy: float) -> np.ndarray:
    th, tw = tex.shape
    yy = (np.arange(h, dtype=np.float32) * scale + oy + t * 18.0) % th
    xx = (np.arange(w, dtype=np.float32) * scale + ox + t * 11.0) % tw
    yi = yy.astype(np.int32)
    xi = xx.astype(np.int32)
    return tex[np.ix_(yi, xi)]


def glow_polyline(layer: np.ndarray, pts: np.ndarray, color_bgr: tuple[int, int, int], thickness: int) -> None:
    if pts is None or len(pts) < 2:
        return
    pts = pts.astype(np.int32).reshape(-1, 1, 2)
    dim = tuple(int(c * 0.28) for c in color_bgr)
    mid = tuple(int(c * 0.62) for c in color_bgr)
    cv2.polylines(layer, [pts], False, dim, max(thickness + 5, 6), cv2.LINE_AA)
    cv2.polylines(layer, [pts], False, mid, max(thickness + 2, 3), cv2.LINE_AA)
    cv2.polylines(layer, [pts], False, color_bgr, max(thickness, 1), cv2.LINE_AA)


def build_text_layer(
    w: int,
    h: int,
    text: str,
    subtext: str,
    position: str,
    size: float,
    color: tuple[float, float, float],
    font_path: Path | None = None,
    tracking: float = 0.08,
) -> np.ndarray | None:
    if not text and not subtext:
        return None
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fs = max(14, int(w * 0.048 * (0.55 + size)))
    sub_fs = max(11, int(fs * 0.42))
    font = load_truetype(font_path, fs)
    subfont = load_truetype(font_path, sub_fs)

    def draw_spaced(y: int, content: str, fnt: ImageFont.ImageFont, fill: tuple[int, int, int, int], track: float) -> int:
        if not content:
            return 0
        widths = [draw.textlength(ch, font=fnt) for ch in content]
        gap = fnt.size * track
        total = sum(widths) + gap * max(len(content) - 1, 0)
        x = (w - total) / 2
        for ch, cw in zip(content, widths, strict=True):
            draw.text((x, y), ch, font=fnt, fill=fill)
            x += cw + gap
        bbox = fnt.getbbox("Ag")
        return (bbox[3] - bbox[1]) if bbox else fnt.size

    fill = (
        int(color[0] * 255),
        int(color[1] * 255),
        int(color[2] * 255),
        255,
    )
    shadow = (0, 0, 0, 220)
    if position == "top":
        y = int(h * 0.08)
    elif position == "center":
        y = int(h * 0.42)
    else:
        y = int(h * 0.70)

    if text:
        draw_spaced(y + 3, text, font, shadow, tracking)
        used = draw_spaced(y, text, font, fill, tracking)
        y += int(used * 1.45)
    if subtext:
        sub_fill = (
            int(min(color[0] * 255 + 20, 255)),
            int(min(color[1] * 255 + 20, 255)),
            int(min(color[2] * 255 + 20, 255)),
            240,
        )
        sub_track = min(tracking + 0.04, 0.18)
        draw_spaced(y + 2, subtext, subfont, shadow, sub_track)
        draw_spaced(y, subtext, subfont, sub_fill, sub_track)

    arr = np.array(img, dtype=np.uint8)
    return arr


def apply_text(img: np.ndarray, layer_rgba: np.ndarray, opacity: float) -> None:
    alpha = (layer_rgba[:, :, 3:4].astype(np.float32) / 255.0) * opacity
    rgb = layer_rgba[:, :, :3].astype(np.float32) / 255.0
    img *= 1.0 - alpha
    img += rgb * alpha


class VisualEngine:
    def __init__(
        self,
        data: np.ndarray,
        sr: int,
        spec: dict,
        settings: VisualSettings,
        width: int,
        height: int,
        clip_start: float,
        background: np.ndarray | None = None,
        logo: Image.Image | None = None,
    ):
        self.data = data
        self.sr = sr
        self.spec = spec
        self.settings = settings
        self.w = width
        self.h = height
        self.clip_start = clip_start
        self.bg_photo = background
        self.logo = logo
        self.scene = resolved_scene(settings)
        self.palette = palette_from_settings(settings)
        self.look = LOOK
        self.rng = np.random.default_rng(settings.seed + 17)
        self.trail = np.zeros((height, width, 3), dtype=np.float32)
        self.vignette = make_vignette(height, width)
        self.noise_tex = make_noise_tex(self.rng, 256)
        self.grain_tiles = np.stack(
            [self.rng.random((128, 128), dtype=np.float32) for _ in range(12)]
        )
        n_part = 220
        self.part_pos = self.rng.random((n_part, 2), dtype=np.float32) * np.array(
            [width, height], dtype=np.float32
        )
        self.part_vel = (self.rng.random((n_part, 2), dtype=np.float32) - 0.5) * 2.0
        self.part_life = self.rng.random(n_part, dtype=np.float32)
        font_path, tracking = resolve_font(settings.font, settings.font_id)
        self.text_layer = build_text_layer(
            width,
            height,
            settings.text,
            settings.subtext,
            settings.text_position,
            settings.text_size,
            self.palette["accent"],
            font_path=font_path,
            tracking=tracking,
        )
        self.yy, self.xx = np.mgrid[0:height, 0:width].astype(np.float32)

    def features_at(self, t: float) -> dict[str, float | np.ndarray]:
        times = self.spec["times"]
        react = float(self.settings.reactivity)
        def g(name: str) -> float:
            v = interp_feat(times, self.spec[name], t)
            return float(np.clip(v * (0.35 + 0.65 * react), 0.0, 1.4))

        spec64 = interp_spec(times, self.spec["spec"], t)
        spec64 = np.clip(spec64 * (0.35 + 0.65 * react), 0.0, 1.6)
        return {
            "sub": g("sub"),
            "bass": g("bass"),
            "lowmid": g("lowmid"),
            "mid": g("mid"),
            "highmid": g("highmid"),
            "high": g("high"),
            "air": g("air"),
            "flux": g("flux"),
            "centroid": interp_feat(times, self.spec["centroid"], t),
            "spec": spec64,
            "onset": g("flux"),
            "energy": float(
                np.clip(
                    0.45 * g("bass") + 0.30 * g("mid") + 0.25 * g("high"),
                    0.0,
                    1.4,
                )
            ),
        }

    def _field(self, feat: dict, t: float) -> np.ndarray:
        pal = self.palette
        h, w = self.h, self.w
        swirl = self.look.get("swirl", 0.3)
        n1 = sample_tex(self.noise_tex, h, w, t * 0.15, 0.55 + swirl * 0.4, 0, 0)
        n2 = sample_tex(self.noise_tex, h, w, t * -0.08, 1.1, 40, 90)
        plasma = 0.5 + 0.5 * np.sin(
            self.xx * (0.006 + 0.004 * swirl)
            + self.yy * (0.004 + feat["centroid"] * 0.006)
            + t * (0.25 + feat["mid"] * 0.8)
            + n1 * (1.8 + swirl)
        )
        field = 0.35 * n1 + 0.25 * n2 + 0.40 * plasma
        field = field * (0.42 + 0.70 * (0.40 + feat["energy"]))
        bg = _rgb(pal["bg"])
        fog = _rgb(pal["fog"])
        dim = _rgb(pal["dim"])
        img = bg[None, None, :] + field[:, :, None] * fog[None, None, :]
        # horizon / wasteland line for noise & drone
        horizon = h * (0.58 - feat["bass"] * 0.06)
        band = np.exp(-((self.yy - horizon) ** 2) / (2 * (h * 0.04) ** 2))
        img += band[:, :, None] * dim[None, None, :] * (0.15 + 0.35 * feat["lowmid"])
        return np.clip(img, 0.0, 1.0)

    def _scope_pts(self, t: float, n: int = 900) -> np.ndarray:
        left, _ = window_stereo(self.data, self.sr, t, n)
        amp = 0.28 + 0.22 * self.settings.intensity
        xs = np.linspace(self.w * 0.06, self.w * 0.94, n, dtype=np.float32)
        ys = self.h * 0.5 - left * self.h * amp
        return np.stack([xs, ys], axis=1)

    def _liss_pts(self, t: float, n: int = 700) -> np.ndarray:
        left, right = window_stereo(self.data, self.sr, t, n)
        amp_x = self.w * (0.28 + 0.16 * self.settings.intensity)
        amp_y = self.h * (0.22 + 0.14 * self.settings.intensity)
        xs = self.w * 0.5 + left * amp_x
        ys = self.h * 0.5 + right * amp_y
        return np.stack([xs, ys], axis=1)

    def _draw_spectrum_ring(self, layer: np.ndarray, feat: dict, color_bgr: tuple[int, int, int]) -> None:
        spec = np.asarray(feat["spec"], dtype=np.float32)
        # mirror for a full symmetric ring
        bins = np.concatenate([spec, spec[::-1]])
        n = bins.shape[0]
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        r0 = min(self.w, self.h) * (0.16 + 0.04 * feat["sub"])
        r = r0 + bins * min(self.w, self.h) * (0.18 + 0.16 * self.settings.intensity)
        xs = self.w * 0.5 + np.cos(angles) * r
        ys = self.h * 0.5 + np.sin(angles) * r
        pts = np.stack([xs, ys], axis=1).astype(np.int32)
        overlay = np.zeros_like(layer)
        cv2.fillPoly(overlay, [pts], tuple(int(c * 0.35) for c in color_bgr), cv2.LINE_AA)
        glow_polyline(overlay, pts, color_bgr, 2)
        # inner ring
        inner = np.stack(
            [
                self.w * 0.5 + np.cos(angles) * r0 * 0.72,
                self.h * 0.5 + np.sin(angles) * r0 * 0.72,
            ],
            axis=1,
        ).astype(np.int32)
        cv2.polylines(overlay, [inner], True, tuple(int(c * 0.5) for c in color_bgr), 1, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _draw_bars(self, layer: np.ndarray, feat: dict, color_bgr: tuple[int, int, int]) -> None:
        spec = np.asarray(feat["spec"], dtype=np.float32)
        n = spec.shape[0]
        margin = self.w * 0.08
        usable = self.w - 2 * margin
        step = usable / n
        bw = max(1, int(step * 0.45))
        overlay = np.zeros_like(layer)
        cy = self.h // 2
        max_h = self.h * (0.20 + 0.22 * self.settings.intensity)
        dim = tuple(int(c * 0.45) for c in color_bgr)
        for i, v in enumerate(spec):
            x = int(margin + i * step + (step - bw) / 2)
            bh = max(2, int(float(v) * max_h))
            cv2.rectangle(overlay, (x, cy - bh), (x + bw, cy + bh), color_bgr, -1)
            if bw >= 3:
                cv2.rectangle(overlay, (x - 1, cy - bh), (x, cy + bh), dim, -1)
        cv2.add(layer, overlay, layer)

    def _draw_tunnel(self, layer: np.ndarray, feat: dict, t: float, color_bgr: tuple[int, int, int]) -> None:
        overlay = np.zeros_like(layer)
        rings = 16
        rot = t * (0.4 + feat["mid"] * 1.6)
        cx, cy = int(self.w * 0.5), int(self.h * 0.5)
        for i in range(rings):
            u = i / rings
            pulse = 0.65 + 0.55 * feat["bass"] + 0.25 * np.sin(t * 2 + i)
            rx = int(self.w * (0.05 + u * 0.55) * pulse)
            ry = int(self.h * (0.05 + u * 0.42) * pulse)
            thickness = 1 + int((1 - u) * 3)
            col = tuple(int(c * (0.25 + 0.75 * (1 - u))) for c in color_bgr)
            angle = rot * 40 + i * 4
            box = ((cx, cy), (max(rx, 2), max(ry, 2)), angle)
            cv2.ellipse(overlay, box, col, thickness, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _step_particles(self, feat: dict) -> None:
        w, h = self.w, self.h
        c = np.array([w / 2.0, h / 2.0], dtype=np.float32)
        to_c = self.part_pos - c
        nrm = np.linalg.norm(to_c, axis=1, keepdims=True) + 1e-5
        swirl = np.stack([-to_c[:, 1], to_c[:, 0]], axis=1) / nrm
        self.part_vel += swirl * (0.12 + feat["mid"] * 0.45)
        if feat["onset"] > 0.42:
            self.part_vel += (to_c / nrm) * feat["onset"] * (6.0 + 8.0 * self.settings.intensity)
        self.part_vel *= 0.955
        self.part_pos += self.part_vel * (1.6 + feat["bass"] * 5.0)
        self.part_pos[:, 0] %= w
        self.part_pos[:, 1] %= h
        self.part_life = 0.92 * self.part_life + 0.08 * (0.3 + feat["energy"])

    def _draw_particles(self, layer: np.ndarray, feat: dict, color_bgr: tuple[int, int, int]) -> None:
        self._step_particles(feat)
        overlay = np.zeros_like(layer)
        pts = self.part_pos.astype(np.int32)
        xs = np.clip(pts[:, 0], 0, self.w - 1)
        ys = np.clip(pts[:, 1], 0, self.h - 1)
        overlay[ys, xs] = color_bgr
        # a handful of larger sparks
        bright = np.argsort(self.part_life)[-28:]
        for i in bright:
            x, y = int(self.part_pos[i, 0]), int(self.part_pos[i, 1])
            rad = 1 + int(self.part_life[i] * 3 + feat["high"] * 2)
            cv2.circle(overlay, (x, y), rad, color_bgr, -1, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _draw_starburst(self, layer: np.ndarray, feat: dict, t: float, color_bgr: tuple[int, int, int]) -> None:
        spec = np.asarray(feat["spec"], dtype=np.float32)
        overlay = np.zeros_like(layer)
        cx, cy = self.w * 0.5, self.h * 0.5
        n = spec.shape[0]
        r0 = min(self.w, self.h) * 0.04
        span = min(self.w, self.h) * (0.22 + 0.28 * self.settings.intensity)
        rot = t * (0.15 + feat["mid"] * 0.4)
        for i, v in enumerate(spec):
            a = rot + (i / n) * np.pi * 2
            r1 = r0 + float(v) * span
            x0 = int(cx + np.cos(a) * r0)
            y0 = int(cy + np.sin(a) * r0)
            x1 = int(cx + np.cos(a) * r1)
            y1 = int(cy + np.sin(a) * r1)
            col = tuple(int(c * (0.35 + 0.65 * float(v))) for c in color_bgr)
            cv2.line(overlay, (x0, y0), (x1, y1), col, 1, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _draw_grid(self, layer: np.ndarray, feat: dict, t: float, color_bgr: tuple[int, int, int]) -> None:
        overlay = np.zeros_like(layer)
        step = max(14, int(min(self.w, self.h) * (0.08 - 0.03 * feat["bass"])))
        amp = (4 + 18 * feat["mid"] * self.settings.intensity)
        col = tuple(int(c * 0.75) for c in color_bgr)
        for x in range(0, self.w + step, step):
            pts = []
            for y in range(0, self.h + 8, 8):
                dx = np.sin(y * 0.018 + t * 2.2) * amp
                pts.append([x + dx, y])
            arr = np.array(pts, dtype=np.int32)
            if len(arr) >= 2:
                cv2.polylines(overlay, [arr], False, col, 1, cv2.LINE_AA)
        for y in range(0, self.h + step, step):
            pts = []
            for x in range(0, self.w + 8, 8):
                dy = np.sin(x * 0.016 + t * 1.7) * amp * 0.7
                pts.append([x, y + dy])
            arr = np.array(pts, dtype=np.int32)
            if len(arr) >= 2:
                cv2.polylines(overlay, [arr], False, col, 1, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _draw_kaleido(self, layer: np.ndarray, t: float, color_bgr: tuple[int, int, int]) -> None:
        pts = self._liss_pts(t, n=420)
        cx, cy = self.w * 0.5, self.h * 0.5
        x = pts[:, 0] - cx
        y = pts[:, 1] - cy
        for k in range(6):
            a = k * (np.pi / 3)
            c, s = np.cos(a), np.sin(a)
            rot = np.stack([x * c - y * s + cx, x * s + y * c + cy], axis=1)
            glow_polyline(layer, rot, color_bgr, 1)

    def _draw_orbits(self, layer: np.ndarray, feat: dict, t: float, color_bgr: tuple[int, int, int]) -> None:
        overlay = np.zeros_like(layer)
        cx, cy = int(self.w * 0.5), int(self.h * 0.5)
        spec = np.asarray(feat["spec"], dtype=np.float32)
        for ring in range(5):
            n = 10 + ring * 5
            r = min(self.w, self.h) * (0.07 + ring * 0.07) * (1.0 + feat["bass"] * 0.18)
            speed = 0.35 + ring * 0.12
            for i in range(n):
                u = i / n
                mag = float(spec[int(u * (spec.shape[0] - 1))])
                a = t * speed + u * np.pi * 2
                x = int(cx + np.cos(a) * r)
                y = int(cy + np.sin(a) * r * 0.72)
                rad = 1 + int(mag * 3 * self.settings.intensity)
                col = tuple(int(c * (0.4 + 0.6 * mag)) for c in color_bgr)
                cv2.circle(overlay, (x, y), max(rad, 1), col, -1, cv2.LINE_AA)
        cv2.add(layer, overlay, layer)

    def _snow(self, img: np.ndarray, feat: dict, frame_i: int) -> None:
        density = 0.002 + 0.01 * float(self.settings.grain) * (0.25 + feat["high"] + feat["air"])
        n = int(self.h * self.w * density)
        n = max(0, min(n, 18000))
        if n == 0:
            return
        rng = np.random.default_rng(self.settings.seed * 1009 + frame_i)
        xs = rng.integers(0, self.w, n)
        ys = rng.integers(0, self.h, n)
        v = 0.45 + 0.5 * float(self.settings.grain)
        img[ys, xs] = np.clip(img[ys, xs] + v * _rgb(self.palette["fg"]), 0.0, 1.0)

    def _draw_scene(self, layer: np.ndarray, feat: dict, t: float) -> None:
        fg = _col(self.palette["fg"])
        scene = self.scene
        if scene in ("field",):
            return
        if scene == "oscilloscope":
            glow_polyline(layer, self._scope_pts(t), fg, 2)
        elif scene == "lissajous":
            glow_polyline(layer, self._liss_pts(t), fg, 2)
        elif scene == "spectrum":
            self._draw_spectrum_ring(layer, feat, fg)
        elif scene == "tunnel":
            self._draw_tunnel(layer, feat, t, fg)
        elif scene == "particles":
            self._draw_particles(layer, feat, fg)
        elif scene == "bars":
            self._draw_bars(layer, feat, fg)
        elif scene == "mixed":
            glow_polyline(layer, self._scope_pts(t), fg, 2)
            self._draw_particles(layer, feat, fg)
        elif scene == "starburst":
            self._draw_starburst(layer, feat, t, fg)
        elif scene == "grid":
            self._draw_grid(layer, feat, t, fg)
        elif scene == "kaleido":
            self._draw_kaleido(layer, t, fg)
        elif scene == "orbits":
            self._draw_orbits(layer, feat, t, fg)
        else:
            glow_polyline(layer, self._scope_pts(t), fg, 2)

    def render_frame(self, frame_i: int, fps: int) -> np.ndarray:
        t = self.clip_start + frame_i / float(fps)
        feat = self.features_at(t)
        decay = 0.50 + 0.45 * float(self.settings.trail)
        decay = float(np.clip(decay, 0.45, 0.94))
        img = self.trail * decay
        field = self._field(feat, t)
        if self.bg_photo is not None:
            op = float(np.clip(self.settings.bg_opacity, 0.0, 1.0))
            tint = _rgb(self.palette["bg"])
            wash = field - tint
            live = self.bg_photo * (1.0 - op) + tint * op
            live = np.clip(live + wash * 0.35 * (1.0 - 0.5 * op), 0.0, 1.0)
        else:
            live = field
        img = np.clip(live * (0.72 + 0.15 * (1.0 - self.settings.trail)) + img * 0.85, 0.0, 1.0)

        layer_bgr = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self._draw_scene(layer_bgr, feat, t)
        add = layer_bgr[:, :, ::-1].astype(np.float32) / 255.0
        img = np.clip(img + add * (0.65 + 0.55 * self.settings.intensity), 0.0, 1.5)

        self.trail = np.clip(img, 0.0, 1.0)

        # onset flash
        if feat["onset"] > 0.5:
            flash = _rgb(self.palette["fg"]) * (feat["onset"] - 0.5) * 0.55 * self.settings.intensity
            img += flash

        # glitch slices
        gamt = float(self.settings.glitch)
        if gamt > 0.02 and feat["onset"] * gamt > 0.12:
            rng = np.random.default_rng(self.settings.seed + frame_i * 13)
            n_slices = int(1 + gamt * 10 * feat["onset"])
            for _ in range(n_slices):
                y = int(rng.integers(0, max(self.h - 8, 1)))
                hgt = int(rng.integers(2, max(3, int(6 + gamt * 28))))
                hgt = min(hgt, self.h - y)
                shift = int(rng.integers(-int(self.w * 0.07 * gamt) - 1, int(self.w * 0.07 * gamt) + 2))
                img[y : y + hgt] = np.roll(img[y : y + hgt], shift, axis=1)
                if gamt > 0.4:
                    ch = int(rng.integers(0, 3))
                    img[y : y + hgt, :, ch] = np.roll(img[y : y + hgt, :, ch], shift // 2, axis=1)

        self._snow(img, feat, frame_i)

        # bloom
        bloom = float(self.settings.bloom)
        if bloom > 0.02:
            gray = img.max(axis=2)
            mask = np.clip((gray - 0.52) * 2.8, 0.0, 1.0)
            hi = img * mask[:, :, None]
            sigma = 5.0 + 16.0 * bloom
            blurred = cv2.GaussianBlur(hi, (0, 0), sigmaX=sigma)
            img = img + blurred * bloom * 1.35

        img = np.clip(img, 0.0, 1.0)

        # vignette
        vig = float(self.settings.vignette)
        img *= ((1.0 - vig) + vig * self.vignette)[:, :, None]

        # scanlines
        sl = float(self.settings.scanlines)
        if sl > 0.01:
            img[::2] *= 1.0 - 0.38 * sl
            if sl > 0.55:
                img[1::4] *= 1.0 - 0.12 * sl

        # chromatic aberration
        ch = float(self.settings.chromatic)
        if ch > 0.02:
            shift = max(1, int(1 + ch * 7 + feat["high"] * 2))
            out = img.copy()
            out[:, :, 0] = np.roll(img[:, :, 0], -shift, axis=1)
            out[:, :, 2] = np.roll(img[:, :, 2], shift, axis=1)
            img = out

        # crush + contrast
        crush = float(self.look.get("crush", 0.05))
        contrast = float(self.look.get("contrast", 1.15))
        img = np.clip((img - crush) / max(1.0 - crush, 0.2), 0.0, 1.0)
        img = np.clip((img - 0.5) * contrast + 0.5, 0.0, 1.0)

        # grain tile
        grain_amt = float(self.settings.grain)
        if grain_amt > 0.01:
            tile = self.grain_tiles[frame_i % len(self.grain_tiles)]
            gh, gw = tile.shape
            yy = (frame_i * 19) % gh
            xx = (frame_i * 13) % gw
            tiled = np.tile(tile, (self.h // gh + 3, self.w // gw + 3))
            g = tiled[yy : yy + self.h, xx : xx + self.w]
            img = np.clip(img + (g[:, :, None] - 0.5) * grain_amt * 0.55, 0.0, 1.0)

        # jitter + bass punch via border crop
        jitter = float(self.settings.jitter)
        punch = 1.0 + feat["bass"] * 0.045 * self.settings.intensity
        pad = int(max(self.w, self.h) * (0.012 + 0.04 * jitter))
        pad = max(pad, 2)
        padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REFLECT)
        rng = np.random.default_rng(self.settings.seed + frame_i * 7)
        dx = int((rng.normal() * jitter * 0.55 + (feat["sub"] - 0.3) * jitter) * pad)
        dy = int((rng.normal() * jitter * 0.55 + (feat["bass"] - 0.3) * jitter) * pad)
        # scale from center (punch)
        ph, pw = padded.shape[:2]
        nw, nh = int(self.w / punch), int(self.h / punch)
        nw = max(nw, 8)
        nh = max(nh, 8)
        cx = pw // 2 + dx
        cy = ph // 2 + dy
        x0 = int(cx - nw / 2)
        y0 = int(cy - nh / 2)
        x0 = max(0, min(x0, pw - nw))
        y0 = max(0, min(y0, ph - nh))
        crop = padded[y0 : y0 + nh, x0 : x0 + nw]
        img = cv2.resize(crop, (self.w, self.h), interpolation=cv2.INTER_LINEAR)

        img = np.clip(img, 0.0, 1.0)
        if self.logo is not None:
            apply_logo(
                img,
                self.logo,
                self.settings.logo_position,
                float(self.settings.logo_size),
                float(self.settings.logo_opacity),
                self.settings.text_position,
            )
        if self.text_layer is not None:
            apply_text(img, self.text_layer, float(self.settings.text_opacity))
        return (img * 255.0 + 0.5).astype(np.uint8)
