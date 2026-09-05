function hexRgba(hex, a) {
  const h = String(hex || "#d4523e").replace("#", "");
  if (h.length !== 6) return `rgba(212,82,62,${a})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function uid() {
  return Math.random().toString(16).slice(2, 10);
}

export function formatTime(t) {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export class Waveform {
  constructor(canvas, onChange) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onChange = onChange;
    this.track = null;
    this.clips = [];
    this.selected = null;
    this.playhead = 0;
    this.drag = null;
    this.hoverT = null;
    this.defaultLen = 15;

    canvas.addEventListener("pointerdown", (e) => this._down(e));
    canvas.addEventListener("pointermove", (e) => this._move(e));
    window.addEventListener("pointerup", (e) => this._up(e));
    canvas.addEventListener("pointerleave", () => {
      if (!this.drag) this.hoverT = null;
      this.draw();
    });
    canvas.addEventListener("dblclick", (e) => {
      const t = this._timeAt(e);
      this.addClipAt(t);
    });
  }

  setTrack(track) {
    this.track = track;
    this.draw();
  }

  setClips(clips, selected) {
    this.clips = clips;
    this.selected = selected;
    this.draw();
  }

  setPlayhead(t) {
    this.playhead = t;
    this.draw();
  }

  selectedClip() {
    return this.clips.find((c) => c.id === this.selected) || null;
  }

  addClipAt(t, length = this.defaultLen) {
    if (!this.track) return;
    const dur = this.track.duration;
    const len = Math.min(length, dur);
    let start = Math.max(0, t);
    let end = start + len;
    if (end > dur) {
      end = dur;
      start = Math.max(0, end - len);
    }
    const clip = { id: uid(), start, end, reason: "manual" };
    this.clips = [...this.clips, clip];
    this.selected = clip.id;
    this._emit();
  }

  fromSuggestions(suggestions) {
    this.clips = suggestions.map((s) => ({
      id: uid(),
      start: s.start,
      end: s.end,
      reason: s.reason || "",
      score: s.score,
    }));
    this.selected = this.clips[0]?.id || null;
    this._emit();
  }

  removeSelected() {
    if (!this.selected) return;
    this.clips = this.clips.filter((c) => c.id !== this.selected);
    this.selected = this.clips[0]?.id || null;
    this._emit();
  }

  _emit() {
    this.draw();
    this.onChange({ clips: this.clips, selected: this.selected });
  }

  _rect() {
    return this.canvas.getBoundingClientRect();
  }

  _timeAt(e) {
    const r = this._rect();
    const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    return x * (this.track?.duration || 0);
  }

  _hit(t) {
    const dur = this.track?.duration || 1;
    const r = this._rect();
    const handle = (8 / r.width) * dur;
    for (let i = this.clips.length - 1; i >= 0; i--) {
      const c = this.clips[i];
      if (Math.abs(t - c.start) <= handle) return { clip: c, mode: "l" };
      if (Math.abs(t - c.end) <= handle) return { clip: c, mode: "r" };
      if (t >= c.start && t <= c.end) return { clip: c, mode: "move" };
    }
    return null;
  }

  _down(e) {
    if (!this.track) return;
    this.canvas.setPointerCapture(e.pointerId);
    const t = this._timeAt(e);
    const hit = this._hit(t);
    if (hit) {
      this.selected = hit.clip.id;
      this.drag = {
        mode: hit.mode,
        id: hit.clip.id,
        origin: t,
        start0: hit.clip.start,
        end0: hit.clip.end,
      };
      this._emit();
    } else {
      this.drag = { mode: "create", origin: t, id: null };
    }
    this.draw();
  }

  _move(e) {
    if (!this.track) return;
    const t = this._timeAt(e);
    this.hoverT = t;
    if (!this.drag) {
      const hit = this._hit(t);
      this.canvas.style.cursor = hit
        ? hit.mode === "move"
          ? "grab"
          : "ew-resize"
        : "crosshair";
      this.draw();
      return;
    }
    const dur = this.track.duration;
    if (this.drag.mode === "create") {
      const a = Math.min(this.drag.origin, t);
      const b = Math.max(this.drag.origin, t);
      if (!this.drag.id) {
        const clip = { id: uid(), start: a, end: Math.max(a + 0.5, b), reason: "manual" };
        this.drag.id = clip.id;
        this.clips = [...this.clips, clip];
        this.selected = clip.id;
      } else {
        const c = this.clips.find((x) => x.id === this.drag.id);
        if (c) {
          c.start = a;
          c.end = Math.max(a + 0.5, b);
        }
      }
    } else {
      const c = this.clips.find((x) => x.id === this.drag.id);
      if (!c) return;
      const dt = t - this.drag.origin;
      if (this.drag.mode === "l") {
        c.start = Math.max(0, Math.min(this.drag.end0 - 0.5, this.drag.start0 + dt));
      } else if (this.drag.mode === "r") {
        c.end = Math.min(dur, Math.max(this.drag.start0 + 0.5, this.drag.end0 + dt));
      } else {
        const len = this.drag.end0 - this.drag.start0;
        let ns = this.drag.start0 + dt;
        ns = Math.max(0, Math.min(dur - len, ns));
        c.start = ns;
        c.end = ns + len;
      }
    }
    this._emit();
  }

  _up() {
    if (this.drag?.mode === "create" && this.drag.id) {
      const c = this.clips.find((x) => x.id === this.drag.id);
      if (c && c.end - c.start < 0.5) {
        this.clips = this.clips.filter((x) => x.id !== c.id);
        this.selected = this.clips[0]?.id || null;
        this._emit();
      }
    }
    this.drag = null;
  }

  draw() {
    const c = this.canvas;
    const ctx = this.ctx;
    const dpr = window.devicePixelRatio || 1;
    const r = c.getBoundingClientRect();
    const w = Math.max(1, Math.floor(r.width * dpr));
    const h = Math.max(1, Math.floor(r.height * dpr));
    if (c.width !== w || c.height !== h) {
      c.width = w;
      c.height = h;
    }
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0b0a09";
    ctx.fillRect(0, 0, w, h);
    if (!this.track) return;
    const dur = this.track.duration || 1;
    const peaks = this.track.waveform;
    const mid = h / 2;
    const n = peaks.n;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / n) * w;
      const mx = peaks.maxs[i] || 0;
      const mn = peaks.mins[i] || 0;
      const y1 = mid - mx * mid * 0.92;
      const y2 = mid - mn * mid * 0.92;
      ctx.moveTo(x, y1);
      ctx.lineTo(x, y2);
    }
    ctx.strokeStyle = "rgba(212, 82, 62, 0.85)";
    ctx.lineWidth = Math.max(1, dpr * 0.7);
    ctx.stroke();

    for (const t of this.track.onsets || []) {
      const x = (t / dur) * w;
      ctx.fillStyle = "rgba(232, 201, 168, 0.22)";
      ctx.fillRect(x, 0, Math.max(1, dpr), h);
    }

    for (const clip of this.clips) {
      const x1 = (clip.start / dur) * w;
      const x2 = (clip.end / dur) * w;
      const on = clip.id === this.selected;
      const col = (clip.settings && clip.settings.effect_color) || "#d4523e";
      ctx.fillStyle = hexRgba(col, on ? 0.28 : 0.12);
      ctx.fillRect(x1, 0, Math.max(2, x2 - x1), h);
      ctx.strokeStyle = on ? col : hexRgba(col, 0.45);
      ctx.lineWidth = dpr;
      ctx.strokeRect(x1 + 0.5, 0.5, Math.max(2, x2 - x1 - 1), h - 1);
      const hw = 3 * dpr;
      ctx.fillStyle = on ? "#e8c9a8" : "rgba(237, 230, 220, 0.35)";
      ctx.fillRect(x1, 0, hw, h);
      ctx.fillRect(x2 - hw, 0, hw, h);
    }

    const px = (this.playhead / dur) * w;
    ctx.fillStyle = "#ede6dc";
    ctx.fillRect(px, 0, Math.max(1, dpr), h);

    if (this.hoverT != null) {
      const tip = document.getElementById("wave-tip");
      if (tip) {
        tip.hidden = false;
        tip.textContent = formatTime(this.hoverT);
        const left = (this.hoverT / dur) * r.width;
        tip.style.left = `${left}px`;
      }
    } else {
      const tip = document.getElementById("wave-tip");
      if (tip) tip.hidden = true;
    }
  }
}
