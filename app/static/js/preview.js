// Live preview. Mirrors app/viz.py step for step so the canvas predicts the MP4:
// field base -> trail mix -> additive scene -> onset flash -> glitch -> snow ->
// bloom -> vignette -> scanlines -> chroma -> crush/contrast -> grain -> jitter
// -> logo -> text -> clip fade. Constants are the ones in viz.py, scaled from
// a 1080-wide frame to the canvas size where they are in pixels.

function hexRgb(hex) {
  const h = String(hex || "#000000").replace("#", "");
  if (h.length !== 6) return [0, 0, 0];
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function mix(a, b, t) {
  return [a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t, a[2] * (1 - t) + b[2] * t];
}

// palette_from_settings in presets.py
function paletteFromSettings(s) {
  const bg = hexRgb(s.bg_color || "#050303");
  const fg = hexRgb(s.effect_color || "#d63d24");
  const accent = hexRgb(s.text_color || "#ede6dc");
  const fog = mix(bg, fg, 0.22).map((c) => Math.min(c, 0.28 * 255));
  const dim = mix(bg, fg, 0.42);
  return { bg, fg, accent, fog, dim };
}

const rgba = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
const scaled = (c, k) => c.map((v) => Math.min(255, v * k));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
// rough normal sample; viz.py uses rng.normal()
const randn = () => (Math.random() + Math.random() + Math.random() + Math.random() - 2) * 1.7;

export class Preview {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.settings = null;
    this.format = "reels";
    this.audio = null;
    this.buffer = null;
    this.actx = null;
    this.analyser = null;
    this.srcNode = null;
    this.running = false;
    this._lookKey = "";
    this.bgImage = null;
    this.logoImage = null;
    this.catalog = null;
    this._fontFam = "";
    this.grain = this._makeGrain();
    this.trail = document.createElement("canvas");
    this.tctx = this.trail.getContext("2d");
    this.bloom = document.createElement("canvas");
    this.bctx = this.bloom.getContext("2d");
    this.scratch = document.createElement("canvas");
    this.sctx = this.scratch.getContext("2d");
    this.overlay = document.createElement("canvas");
    this.octx = this.overlay.getContext("2d");
    this.overlayFx = document.createElement("canvas");
    this.ofx = this.overlayFx.getContext("2d");
    this.clipFade = null;
    this.safeArea = false;
    this.frame = 0;
    this._lastDraw = 0;
    this._prevFreq = null;
    this._fluxMax = 1e-3;
    this._initParticles();
  }

  _initParticles() {
    // 220 sparks, positions in 0..1 so a resize does not scatter them
    this.particles = Array.from({ length: 220 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 2,
      vy: (Math.random() - 0.5) * 2,
      life: Math.random(),
    }));
  }

  _makeGrain() {
    const c = document.createElement("canvas");
    c.width = 128;
    c.height = 128;
    const x = c.getContext("2d");
    const img = x.createImageData(128, 128);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = Math.random() * 255;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    x.putImageData(img, 0, 0);
    return c;
  }

  setBackground(img) {
    this.bgImage = img || null;
    this._lookKey = "";
    if (this.running) this.draw();
  }

  setLogo(img) {
    this.logoImage = img || null;
    this._lookKey = "";
    if (this.running) this.draw();
  }

  setCatalog(catalog) {
    this.catalog = catalog || null;
  }

  setFormat(fmt) {
    this.format = fmt || "reels";
    if (this.running) this.draw();
  }

  setSafeArea(on) {
    this.safeArea = Boolean(on);
    if (this.running) this.draw();
  }

  setClipFade(clip) {
    if (!clip) {
      this.clipFade = null;
      return;
    }
    this.clipFade = {
      start: clip.start,
      end: clip.end,
      fade_in: clip.fade_in || 0,
      fade_out: clip.fade_out || 0,
    };
  }

  _lookSignature(s) {
    if (!s) return "";
    return [
      s.bg_color,
      s.effect_color,
      s.text_color,
      s.scene,
      s.background_id,
      s.bg_opacity,
      s.font,
      s.font_id,
      s.logo_id,
      s.logo_position,
      s.logo_size,
      s.text,
      s.subtext,
      s.text_position,
      s.text_y,
      s.text_size,
    ].join("|");
  }

  _fontFamily(s) {
    if (s?.font_id) return `nv-custom-${s.font_id}`;
    const fonts = this.catalog?.fonts || [];
    const hit = fonts.find((f) => f.id === (s?.font || "archivo"));
    return hit?.family || "Archivo Black";
  }

  _tracking(s) {
    if (s?.font_id) return 0.06;
    const fonts = this.catalog?.fonts || [];
    const hit = fonts.find((f) => f.id === (s?.font || "archivo"));
    return hit?.tracking ?? 0.08;
  }

  setSettings(s) {
    this.settings = s;
    const key = this._lookSignature(s);
    if (key !== this._lookKey) {
      this._lookKey = key;
      this.tctx.clearRect(0, 0, this.trail.width || 0, this.trail.height || 0);
    }
    const fam = this._fontFamily(s);
    if (fam !== this._fontFam) {
      this._fontFam = fam;
      const load = document.fonts?.load?.(`600 48px "${fam}"`);
      if (load) load.then(() => { if (this.running) this.draw(); }).catch(() => {});
    }
    if (this.running) this.draw();
  }

  async attachAudio(audioEl, arrayBuffer) {
    this.audio = audioEl;
    if (!this.actx) this.actx = new AudioContext();
    if (this.actx.state === "suspended") await this.actx.resume();
    if (!this.buffer) {
      this.buffer = await this.actx.decodeAudioData(arrayBuffer.slice(0));
    }
    if (!this.srcNode) {
      this.analyser = this.actx.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.55;
      this.srcNode = this.actx.createMediaElementSource(audioEl);
      this.srcNode.connect(this.analyser);
      this.analyser.connect(this.actx.destination);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      this.draw();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  stop() {
    this.running = false;
  }

  _size() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.canvas.getBoundingClientRect();
    const w = Math.max(2, Math.floor(r.width * dpr));
    const h = Math.max(2, Math.floor(r.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.trail.width = w;
      this.trail.height = h;
      this.scratch.width = w;
      this.scratch.height = h;
    }
    return { w, h, dpr };
  }

  // spectral_features + features_at in audio.py / viz.py, from the live analyser
  _features() {
    const react = 0.35 + 0.65 * (this.settings?.reactivity ?? 0.85);
    const empty = {
      sub: 0, bass: 0, lowmid: 0, mid: 0, highmid: 0, high: 0, air: 0,
      onset: 0, energy: 0, centroid: 0.2, spec: new Float32Array(64),
    };
    if (!this.analyser || !this.audio || this.audio.paused) return empty;
    const freq = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(freq);
    const sr = this.actx?.sampleRate || 44100;
    const hzPerBin = sr / 2 / freq.length;
    const band = (lo, hi) => {
      const a = Math.max(0, Math.floor(lo / hzPerBin));
      const b = Math.min(freq.length, Math.max(a + 1, Math.ceil(hi / hzPerBin)));
      let s = 0;
      for (let i = a; i < b; i++) s += freq[i];
      // byte magnitudes sit ~0.8 for loud material; viz.py normalises to the
      // track's 95th percentile, so lift a little and clip like features_at
      return clamp((s / (b - a) / 255) * 1.25 * react, 0, 1.4);
    };
    // spectral flux -> onset, normalised against a slowly decaying running max
    let flux = 0;
    if (this._prevFreq) {
      for (let i = 0; i < freq.length; i++) {
        const d = freq[i] - this._prevFreq[i];
        if (d > 0) flux += d;
      }
    }
    this._prevFreq = freq;
    this._fluxMax = Math.max(this._fluxMax * 0.992, flux, 1e-3);
    const onset = clamp((flux / this._fluxMax) * 1.15 * react, 0, 1.4);
    // 64 bins over the lower half of the spectrum, as spec_bins in audio.py
    const spec = new Float32Array(64);
    const half = Math.max(1, freq.length >> 1);
    for (let i = 0; i < 64; i++) {
      const a = Math.floor((i / 64) * half);
      const b = Math.max(a + 1, Math.floor(((i + 1) / 64) * half));
      let s = 0;
      for (let j = a; j < b; j++) s += freq[j];
      spec[i] = clamp((s / (b - a) / 255) * 1.3 * react, 0, 1.6);
    }
    let num = 0;
    let den = 1e-6;
    for (let i = 0; i < freq.length; i++) {
      num += i * freq[i];
      den += freq[i];
    }
    const f = {
      sub: band(20, 60),
      bass: band(60, 250),
      lowmid: band(250, 500),
      mid: band(500, 2000),
      highmid: band(2000, 6000),
      high: band(6000, 12000),
      air: band(12000, 20000),
      onset,
      centroid: clamp(num / den / freq.length, 0, 1),
      spec,
    };
    f.energy = clamp(0.45 * f.bass + 0.3 * f.mid + 0.25 * f.high, 0, 1.4);
    return f;
  }

  _stereoWindow(n) {
    const t = this.audio?.currentTime || 0;
    const sr = this.buffer?.sampleRate || 44100;
    const ch0 = this.buffer?.getChannelData(0);
    if (!ch0) return null;
    const ch1 = this.buffer.numberOfChannels > 1 ? this.buffer.getChannelData(1) : null;
    const center = Math.floor(t * sr);
    const left = new Float32Array(n);
    const right = new Float32Array(n);
    const half = n >> 1;
    const mono = !ch1;
    const monoShift = Math.max(1, Math.floor(sr * 0.002));
    for (let i = 0; i < n; i++) {
      const idx = center - half + i;
      if (idx < 0 || idx >= ch0.length) continue;
      left[i] = ch0[idx];
      right[i] = mono ? ch0[Math.max(0, idx - monoShift)] : ch1[idx];
    }
    return { left, right };
  }

  // _scope_pts: 900 samples, x from 6% to 94% of width
  _scopePts(w, h) {
    const n = 900;
    const win = this._stereoWindow(n);
    const amp = 0.28 + 0.22 * (this.settings?.intensity ?? 0.75);
    const xs = new Float32Array(n);
    const ys = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      xs[i] = w * 0.06 + (i / (n - 1)) * w * 0.88;
      ys[i] = h * 0.5 - (win ? win.left[i] : 0) * h * amp;
    }
    return { xs, ys };
  }

  // _liss_pts
  _lissPts(w, h, n = 700) {
    const win = this._stereoWindow(n);
    const inten = this.settings?.intensity ?? 0.75;
    const ax = w * (0.28 + 0.16 * inten);
    const ay = h * (0.22 + 0.14 * inten);
    const xs = new Float32Array(n);
    const ys = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      xs[i] = w * 0.5 + (win ? win.left[i] : 0) * ax;
      ys[i] = h * 0.5 + (win ? win.right[i] : 0) * ay;
    }
    return { xs, ys };
  }

  draw() {
    const { w, h } = this._size();
    const ctx = this.ctx;
    const s = this.settings || {};
    const pal = paletteFromSettings(s);
    const f = this._features();
    const t = this.audio?.currentTime || 0;
    const k = w / 1080; // pixel constants in viz.py are tuned for a 1080-wide frame
    const px = (n) => Math.max(0.75, n * k);
    const inten = s.intensity ?? 0.75;
    const trailAmt = s.trail ?? 0.4;
    this.frame++;

    const lookKey = this._lookSignature(s);
    if (lookKey !== this._lookKey) {
      this._lookKey = lookKey;
      this.tctx.clearRect(0, 0, w, h);
    }

    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.filter = "none";

    // --- field base (VisualEngine._field) -------------------------------
    // render: img = live*(0.72 + 0.15*(1-trail)) + trail*decay*0.85, once per
    // 30 fps frame. The browser draws at whatever rate it likes, so scale the
    // per-frame gains to elapsed time and keep the same steady state.
    const now = performance.now();
    const frames = this._lastDraw ? clamp(((now - this._lastDraw) / 1000) * 30, 0.25, 4) : 1;
    this._lastDraw = now;
    const b = clamp(0.5 + 0.45 * trailAmt, 0.45, 0.94) * 0.85;
    const bEff = Math.pow(b, frames);
    const liveGain = clamp((0.72 + 0.15 * (1 - trailAmt)) * ((1 - bEff) / (1 - b)), 0.05, 1);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, w, h);
    ctx.globalAlpha = liveGain;
    this._field(ctx, w, h, f, pal, t, s);
    ctx.globalAlpha = 1;
    if (trailAmt > 0.02) {
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = bEff;
      ctx.drawImage(this.trail, 0, 0);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    }

    // --- scene layer, additive (img += layer * (0.65 + 0.55*intensity)) --
    ctx.globalCompositeOperation = "lighter";
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    this._scene(ctx, w, h, f, pal, t, s, px);
    ctx.globalCompositeOperation = "source-over";

    // trail keeps the frame at this point, like self.trail = clip(img)
    this.tctx.globalCompositeOperation = "copy";
    this.tctx.drawImage(this.canvas, 0, 0);
    this.tctx.globalCompositeOperation = "source-over";

    // --- onset flash ------------------------------------------------------
    if (f.onset > 0.5) {
      ctx.globalCompositeOperation = "lighter";
      ctx.fillStyle = rgba(pal.fg, clamp((f.onset - 0.5) * 0.55 * inten, 0, 1));
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";
    }

    // --- glitch slices, gated on hits like viz.py -------------------------
    const gamt = s.glitch ?? 0;
    if (gamt > 0.02 && f.onset * gamt > 0.12) {
      const slices = 1 + Math.floor(gamt * 10 * f.onset);
      for (let i = 0; i < slices; i++) {
        const y = Math.random() * Math.max(h - px(8), 1);
        const hh = px(2 + Math.random() * (4 + gamt * 28));
        const dx = (Math.random() * 2 - 1) * (w * 0.07 * gamt + 1);
        ctx.drawImage(this.canvas, 0, y, w, hh, dx, y, w, hh);
      }
    }

    // --- analog snow (_snow) ---------------------------------------------
    const grainAmt = s.grain ?? 0.45;
    const density = 0.002 + 0.01 * grainAmt * (0.25 + f.high + f.air);
    const dots = Math.min(3500, Math.floor(w * h * density * 0.25));
    if (dots > 0) {
      ctx.globalCompositeOperation = "lighter";
      ctx.fillStyle = rgba(pal.fg, 0.45 + 0.5 * grainAmt);
      const d = Math.max(1, Math.round(k * 2));
      for (let i = 0; i < dots; i++) ctx.fillRect(Math.random() * w, Math.random() * h, d, d);
      ctx.globalCompositeOperation = "source-over";
    }

    // --- bloom on highlights ---------------------------------------------
    this._bloom(ctx, w, h, s.bloom ?? 0, k);

    // --- vignette (make_vignette) -----------------------------------------
    this._vignette(ctx, w, h, s.vignette ?? 0.7);

    // --- scanlines --------------------------------------------------------
    const sln = s.scanlines ?? 0.5;
    if (sln > 0.01) {
      const step = Math.max(2, Math.round(2 * k));
      ctx.fillStyle = `rgba(0,0,0,${0.38 * sln})`;
      for (let y = 0; y < h; y += step) ctx.fillRect(0, y, w, Math.max(1, step / 2));
      if (sln > 0.55) {
        ctx.fillStyle = `rgba(0,0,0,${0.12 * sln})`;
        for (let y = step / 2; y < h; y += step * 2) ctx.fillRect(0, y, w, Math.max(1, step / 2));
      }
    }

    // --- chromatic aberration ---------------------------------------------
    this._chroma(ctx, w, h, s.chromatic ?? 0, f.high, k);

    // --- crush + contrast (LOOK crush 0.08, contrast 1.28) ----------------
    this._selfFilter(ctx, w, h, "contrast(1.39) brightness(0.94)");

    // --- grain tile -------------------------------------------------------
    if (grainAmt > 0.01) {
      ctx.save();
      ctx.globalAlpha = grainAmt * 0.45;
      ctx.globalCompositeOperation = "overlay";
      const ox = (this.frame * 13) % 128;
      const oy = (this.frame * 19) % 128;
      ctx.fillStyle = ctx.createPattern(this.grain, "repeat");
      ctx.translate(-ox, -oy);
      ctx.fillRect(0, 0, w + 128, h + 128);
      ctx.restore();
    }

    // --- jitter + bass punch, inside the frame so text stays put ---------
    const jitter = s.jitter ?? 0.3;
    const punch = 1 + f.bass * 0.045 * inten;
    const pad = Math.max(2, Math.max(w, h) * (0.012 + 0.04 * jitter));
    const dx = (randn() * jitter * 0.55 + (f.sub - 0.3) * jitter) * pad;
    const dy = (randn() * jitter * 0.55 + (f.bass - 0.3) * jitter) * pad;
    if (Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3 || punch > 1.001) {
      const sc = this.sctx;
      sc.globalCompositeOperation = "copy";
      sc.drawImage(this.canvas, 0, 0);
      sc.globalCompositeOperation = "source-over";
      const nw = w * punch;
      const nh = h * punch;
      ctx.drawImage(this.scratch, (w - nw) / 2 - dx, (h - nh) / 2 - dy, nw, nh);
    }

    // --- logo + text (after everything, like viz.py) ----------------------
    this._logo(ctx, w, h, s);
    this._text(ctx, w, h, pal, s, k);

    // --- clip fade --------------------------------------------------------
    const fade = this.clipFade;
    if (fade) {
      const dur = Math.max(0.001, fade.end - fade.start);
      const local = t - fade.start;
      let g = 1;
      const fi = Math.min(fade.fade_in || 0, dur);
      const fo = Math.min(fade.fade_out || 0, dur);
      if (fi > 0.0005 && local < fi) g *= Math.max(0, local / fi);
      if (fo > 0.0005 && dur - local < fo) g *= Math.max(0, (dur - local) / fo);
      g = clamp(g, 0, 1);
      if (g < 0.999) {
        ctx.fillStyle = `rgba(0,0,0,${1 - g})`;
        ctx.fillRect(0, 0, w, h);
      }
    }

    if (this.safeArea) this._safeArea(ctx, w, h);
    ctx.restore();
    this.canvas.style.transform = "";
  }

  // VisualEngine._field: bg + noise/plasma * fog + horizon band. Canvas has no
  // cheap per-pixel plasma, so this uses drifting soft blobs of the same fog
  // colour at the same overall level.
  _field(ctx, w, h, f, pal, t, s) {
    const op = clamp(s.bg_opacity ?? 0.22, 0, 1);
    if (this.bgImage) {
      // live = photo*(1-op) + tint*op, then a wash of the field
      drawCover(ctx, this.bgImage, w, h);
      ctx.fillStyle = rgba(pal.bg, op);
      ctx.fillRect(0, 0, w, h);
    } else {
      ctx.fillStyle = rgba(pal.bg);
      ctx.fillRect(0, 0, w, h);
    }
    const washGain = this.bgImage ? 0.35 * (1 - 0.5 * op) : 1;
    const level = (0.42 + 0.7 * (0.4 + f.energy)) * 0.5 * washGain;
    ctx.fillStyle = rgba(pal.fog, clamp(level * 0.55, 0, 1));
    ctx.fillRect(0, 0, w, h);
    const blobs = 3;
    for (let i = 0; i < blobs; i++) {
      const cx = w * (0.5 + 0.38 * Math.sin(t * (0.11 + i * 0.05) + i * 2.1));
      const cy = h * (0.5 + 0.34 * Math.cos(t * (0.09 + i * 0.04) + i * 1.3 + f.centroid));
      const r = Math.max(w, h) * (0.35 + 0.15 * Math.sin(t * 0.2 + i));
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, rgba(pal.fog, clamp(level * 0.9, 0, 1)));
      g.addColorStop(1, rgba(pal.fog, 0));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    }
    // horizon line
    const horizon = h * (0.58 - f.bass * 0.06);
    const sigma = h * 0.04;
    const hg = ctx.createLinearGradient(0, horizon - sigma * 2.5, 0, horizon + sigma * 2.5);
    const ha = clamp((0.15 + 0.35 * f.lowmid) * washGain, 0, 1);
    hg.addColorStop(0, rgba(pal.dim, 0));
    hg.addColorStop(0.5, rgba(pal.dim, ha));
    hg.addColorStop(1, rgba(pal.dim, 0));
    ctx.fillStyle = hg;
    ctx.fillRect(0, horizon - sigma * 2.5, w, sigma * 5);
  }

  _scene(ctx, w, h, f, pal, t, s, px) {
    const scene = !s.scene || s.scene === "auto" ? "mixed" : s.scene;
    const fg = pal.fg;
    const gain = Math.min(1, 0.65 + 0.55 * (s.intensity ?? 0.75));
    ctx.globalAlpha = gain;
    switch (scene) {
      case "field":
        break;
      case "oscilloscope": {
        const p = this._scopePts(w, h);
        glowPath(ctx, p.xs, p.ys, fg, px(2), px);
        break;
      }
      case "lissajous": {
        const p = this._lissPts(w, h);
        glowPath(ctx, p.xs, p.ys, fg, px(2), px);
        break;
      }
      case "spectrum":
        this._spectrumRing(ctx, w, h, f, fg, px);
        break;
      case "tunnel":
        this._tunnel(ctx, w, h, f, t, fg, px);
        break;
      case "particles":
        this._particles(ctx, w, h, f, fg, px);
        break;
      case "bars":
        this._bars(ctx, w, h, f, fg);
        break;
      case "starburst":
        this._starburst(ctx, w, h, f, t, fg, px);
        break;
      case "grid":
        this._grid(ctx, w, h, f, t, fg, px);
        break;
      case "kaleido":
        this._kaleido(ctx, w, h, fg, px);
        break;
      case "orbits":
        this._orbits(ctx, w, h, f, t, fg, px);
        break;
      case "mixed":
      default: {
        const p = this._scopePts(w, h);
        glowPath(ctx, p.xs, p.ys, fg, px(2), px);
        this._particles(ctx, w, h, f, fg, px);
      }
    }
    ctx.globalAlpha = 1;
  }

  // _draw_spectrum_ring: mirrored 128-point ring, filled at 35%, glow outline, inner ring
  _spectrumRing(ctx, w, h, f, fg, px) {
    const spec = f.spec;
    const n = spec.length * 2;
    const m = Math.min(w, h);
    const inten = this.settings?.intensity ?? 0.75;
    const r0 = m * (0.16 + 0.04 * f.sub);
    const xs = new Float32Array(n);
    const ys = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const v = i < spec.length ? spec[i] : spec[n - 1 - i];
      const a = (i / n) * Math.PI * 2;
      const r = r0 + v * m * (0.18 + 0.16 * inten);
      xs[i] = w * 0.5 + Math.cos(a) * r;
      ys[i] = h * 0.5 + Math.sin(a) * r;
    }
    ctx.beginPath();
    ctx.moveTo(xs[0], ys[0]);
    for (let i = 1; i < n; i++) ctx.lineTo(xs[i], ys[i]);
    ctx.closePath();
    ctx.fillStyle = rgba(scaled(fg, 0.35));
    ctx.fill();
    glowPath(ctx, xs, ys, fg, px(2), px, true);
    ctx.beginPath();
    ctx.arc(w * 0.5, h * 0.5, r0 * 0.72, 0, Math.PI * 2);
    ctx.strokeStyle = rgba(scaled(fg, 0.5));
    ctx.lineWidth = px(1);
    ctx.stroke();
  }

  // _draw_bars: 64 mirrored columns around the vertical centre
  _bars(ctx, w, h, f, fg) {
    const spec = f.spec;
    const n = spec.length;
    const margin = w * 0.08;
    const step = (w - 2 * margin) / n;
    const bw = Math.max(1, step * 0.45);
    const cy = h / 2;
    const maxH = h * (0.2 + 0.22 * (this.settings?.intensity ?? 0.75));
    const dim = rgba(scaled(fg, 0.45));
    const col = rgba(fg);
    for (let i = 0; i < n; i++) {
      const x = margin + i * step + (step - bw) / 2;
      const bh = Math.max(2, spec[i] * maxH);
      ctx.fillStyle = col;
      ctx.fillRect(x, cy - bh, bw, bh * 2);
      if (bw >= 3) {
        ctx.fillStyle = dim;
        ctx.fillRect(x - 1, cy - bh, 1, bh * 2);
      }
    }
  }

  // _draw_tunnel: 16 rotating ellipses, bass pulse
  _tunnel(ctx, w, h, f, t, fg, px) {
    const rings = 16;
    const rot = t * (0.4 + f.mid * 1.6);
    for (let i = 0; i < rings; i++) {
      const u = i / rings;
      const pulse = 0.65 + 0.55 * f.bass + 0.25 * Math.sin(t * 2 + i);
      const rx = Math.max(2, w * (0.05 + u * 0.55) * pulse);
      const ry = Math.max(2, h * (0.05 + u * 0.42) * pulse);
      ctx.strokeStyle = rgba(scaled(fg, 0.25 + 0.75 * (1 - u)));
      ctx.lineWidth = px(1 + (1 - u) * 3);
      ctx.beginPath();
      ctx.ellipse(w / 2, h / 2, rx, ry, ((rot * 40 + i * 4) * Math.PI) / 180, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // _step_particles + _draw_particles
  _particles(ctx, w, h, f, fg, px) {
    const inten = this.settings?.intensity ?? 0.75;
    const speed = 1.6 + f.bass * 5.0;
    const k = w / 1080;
    for (const p of this.particles) {
      const tx = p.x * w - w / 2;
      const ty = p.y * h - h / 2;
      const nrm = Math.hypot(tx, ty) + 1e-5;
      const sx = -ty / nrm;
      const sy = tx / nrm;
      p.vx += sx * (0.12 + f.mid * 0.45);
      p.vy += sy * (0.12 + f.mid * 0.45);
      if (f.onset > 0.42) {
        const push = f.onset * (6 + 8 * inten);
        p.vx += (tx / nrm) * push;
        p.vy += (ty / nrm) * push;
      }
      p.vx *= 0.955;
      p.vy *= 0.955;
      p.x = (((p.x * w + p.vx * speed * k) % w) + w) % w / w;
      p.y = (((p.y * h + p.vy * speed * k) % h) + h) % h / h;
      p.life = 0.92 * p.life + 0.08 * (0.3 + f.energy);
    }
    ctx.fillStyle = rgba(fg);
    const d = Math.max(1, Math.round(k));
    for (const p of this.particles) ctx.fillRect(p.x * w, p.y * h, d, d);
    const bright = [...this.particles].sort((a, b) => a.life - b.life).slice(-28);
    for (const p of bright) {
      const r = px(1 + p.life * 3 + f.high * 2);
      ctx.beginPath();
      ctx.arc(p.x * w, p.y * h, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // _draw_starburst: 64 rays
  _starburst(ctx, w, h, f, t, fg, px) {
    const spec = f.spec;
    const n = spec.length;
    const m = Math.min(w, h);
    const cx = w / 2;
    const cy = h / 2;
    const r0 = m * 0.04;
    const span = m * (0.22 + 0.28 * (this.settings?.intensity ?? 0.75));
    const rot = t * (0.15 + f.mid * 0.4);
    ctx.lineWidth = px(1);
    for (let i = 0; i < n; i++) {
      const v = spec[i];
      const a = rot + (i / n) * Math.PI * 2;
      const r1 = r0 + v * span;
      ctx.strokeStyle = rgba(scaled(fg, 0.35 + 0.65 * v));
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      ctx.stroke();
    }
  }

  _grid(ctx, w, h, f, t, fg, px) {
    const step = Math.max(px(14), Math.min(w, h) * (0.08 - 0.03 * f.bass));
    const amp = px(4 + 18 * f.mid * (this.settings?.intensity ?? 0.75));
    const seg = px(8);
    ctx.strokeStyle = rgba(scaled(fg, 0.75));
    ctx.lineWidth = px(1);
    for (let x = 0; x < w + step; x += step) {
      ctx.beginPath();
      for (let y = 0; y <= h + seg; y += seg) {
        const dx = Math.sin(y * 0.018 / (w / 1080) + t * 2.2) * amp;
        if (y === 0) ctx.moveTo(x + dx, y);
        else ctx.lineTo(x + dx, y);
      }
      ctx.stroke();
    }
    for (let y = 0; y < h + step; y += step) {
      ctx.beginPath();
      for (let x = 0; x <= w + seg; x += seg) {
        const dy = Math.sin(x * 0.016 / (w / 1080) + t * 1.7) * amp * 0.7;
        if (x === 0) ctx.moveTo(x, y + dy);
        else ctx.lineTo(x, y + dy);
      }
      ctx.stroke();
    }
  }

  _kaleido(ctx, w, h, fg, px) {
    const p = this._lissPts(w, h, 420);
    const cx = w / 2;
    const cy = h / 2;
    const n = p.xs.length;
    const xs = new Float32Array(n);
    const ys = new Float32Array(n);
    for (let k = 0; k < 6; k++) {
      const a = (k * Math.PI) / 3;
      const c = Math.cos(a);
      const s = Math.sin(a);
      for (let i = 0; i < n; i++) {
        const x = p.xs[i] - cx;
        const y = p.ys[i] - cy;
        xs[i] = x * c - y * s + cx;
        ys[i] = x * s + y * c + cy;
      }
      glowPath(ctx, xs, ys, fg, px(1), px);
    }
  }

  _orbits(ctx, w, h, f, t, fg, px) {
    const cx = w / 2;
    const cy = h / 2;
    const spec = f.spec;
    const inten = this.settings?.intensity ?? 0.75;
    for (let ring = 0; ring < 5; ring++) {
      const n = 10 + ring * 5;
      const r = Math.min(w, h) * (0.07 + ring * 0.07) * (1 + f.bass * 0.18);
      const speed = 0.35 + ring * 0.12;
      for (let i = 0; i < n; i++) {
        const u = i / n;
        const mag = spec[Math.floor(u * (spec.length - 1))] || 0;
        const a = t * speed + u * Math.PI * 2;
        ctx.fillStyle = rgba(scaled(fg, 0.4 + 0.6 * mag));
        ctx.beginPath();
        ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r * 0.72, px(1 + mag * 3 * inten), 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  // bloom: highlights above ~0.52 blurred and added back
  _bloom(ctx, w, h, amount, k) {
    if (amount < 0.02) return;
    const buf = this.bloom;
    const bw = Math.max(2, (w / 2) | 0);
    const bh = Math.max(2, (h / 2) | 0);
    if (buf.width !== bw || buf.height !== bh) {
      buf.width = bw;
      buf.height = bh;
    }
    const bctx = this.bctx;
    bctx.clearRect(0, 0, bw, bh);
    // contrast(2.8) around mid grey mimics mask = clip((gray-0.52)*2.8)
    bctx.filter = `contrast(2.8) brightness(0.92) blur(${((5 + 16 * amount) * k) / 2}px)`;
    bctx.drawImage(this.canvas, 0, 0, bw, bh);
    bctx.filter = "none";
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = Math.min(1, amount * 1.35);
    ctx.drawImage(buf, 0, 0, w, h);
    ctx.restore();
  }

  // make_vignette: v = clip(1 - dx²/(0.62w)² - dy²/(0.62h)²)^0.9 ; img *= (1-vig) + vig*v
  _vignette(ctx, w, h, vig) {
    if (vig < 0.01) return;
    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.scale(w / 2, h / 2);
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1.42);
    const stops = [0, 0.3, 0.5, 0.7, 0.85, 1.0, 1.15, 1.24, 1.42];
    for (const r of stops) {
      const v = Math.pow(clamp(1 - 0.65 * r * r, 0, 1), 0.9);
      g.addColorStop(r / 1.42, `rgba(0,0,0,${clamp(vig * (1 - v), 0, 1)})`);
    }
    ctx.fillStyle = g;
    ctx.fillRect(-1, -1, 2, 2);
    ctx.restore();
  }

  _chroma(ctx, w, h, amount, high, k) {
    if (amount < 0.02) return;
    const shift = Math.max(1, Math.round((1 + amount * 7 + high * 2) * k));
    const sc = this.sctx;
    sc.globalCompositeOperation = "copy";
    sc.drawImage(this.canvas, 0, 0);
    sc.globalCompositeOperation = "source-over";
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    ctx.globalAlpha = Math.min(0.8, 0.2 + amount * 0.75);
    ctx.drawImage(this.scratch, -shift, 0);
    ctx.drawImage(this.scratch, shift, 0);
    ctx.restore();
  }

  _selfFilter(ctx, w, h, filter) {
    const sc = this.sctx;
    sc.globalCompositeOperation = "copy";
    sc.drawImage(this.canvas, 0, 0);
    sc.globalCompositeOperation = "source-over";
    ctx.save();
    ctx.globalCompositeOperation = "copy";
    ctx.filter = filter;
    ctx.drawImage(this.scratch, 0, 0);
    ctx.restore();
  }

  _safeArea(ctx, w, h) {
    const fmt = this.format || "reels";
    const top = fmt === "landscape" ? 0.04 : 0.08;
    const bottom = fmt === "landscape" ? 0.12 : 0.18;
    ctx.save();
    ctx.strokeStyle = "rgba(237, 230, 220, 0.35)";
    ctx.lineWidth = Math.max(1, w * 0.002);
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(0, h * top);
    ctx.lineTo(w, h * top);
    ctx.moveTo(0, h * (1 - bottom));
    ctx.lineTo(w, h * (1 - bottom));
    if (fmt === "reels" || fmt === "portrait") {
      ctx.moveTo(w * 0.88, h * top);
      ctx.lineTo(w * 0.88, h * (1 - bottom));
    }
    ctx.stroke();
    ctx.restore();
  }

  _prepOverlay(w, h) {
    if (this.overlay.width !== w || this.overlay.height !== h) {
      this.overlay.width = w;
      this.overlay.height = h;
      this.overlayFx.width = w;
      this.overlayFx.height = h;
    }
    this.octx.clearRect(0, 0, w, h);
    return this.octx;
  }

  // fx_rgba: glow / glitch / chroma / jitter on a transparent overlay
  _stampOverlay(ctx, w, h, fx, k) {
    const glow = fx.glow ?? 0;
    const glitch = fx.glitch ?? 0;
    const chroma = fx.chroma ?? 0;
    const jitter = fx.jitter ?? 0;
    const opacity = fx.opacity ?? 1;
    const src = this.overlay;
    const dst = this.overlayFx;
    const dx = this.ofx;
    dx.clearRect(0, 0, w, h);
    dx.drawImage(src, 0, 0);
    if (glow > 0.02) {
      dx.save();
      dx.filter = `blur(${(2.2 + 11 * glow) * k}px)`;
      dx.globalCompositeOperation = "lighter";
      dx.globalAlpha = Math.min(1, glow * 1.2);
      dx.drawImage(src, 0, 0);
      dx.restore();
    }
    if (glitch > 0.02) {
      const slices = 1 + Math.floor(glitch * 9);
      for (let i = 0; i < slices; i++) {
        const y = Math.random() * h;
        const hh = (2 + Math.random() * (4 + glitch * 22)) * k;
        const shift = (Math.random() - 0.5) * w * 0.2 * glitch;
        dx.drawImage(dst, 0, y, w, hh, shift, y, w, hh);
      }
    }
    if (chroma > 0.02) {
      const shift = Math.max(1, (1 + chroma * 8) * k);
      dx.save();
      dx.globalCompositeOperation = "screen";
      dx.globalAlpha = 0.45 + 0.4 * chroma;
      dx.drawImage(dst, -shift, 0);
      dx.drawImage(dst, shift, 0);
      dx.restore();
    }
    const jx = jitter > 0.02 ? randn() * jitter * w * 0.04 : 0;
    const jy = jitter > 0.02 ? randn() * jitter * h * 0.03 : 0;
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.drawImage(dst, clamp(jx, -w * 0.12, w * 0.12), clamp(jy, -h * 0.1, h * 0.1));
    ctx.restore();
  }

  // build_text_layer: same size formula, shadow, spacing and clamp as viz.py
  _text(ctx, w, h, pal, s, k) {
    if (!s.text && !s.subtext) return;
    const ox = this._prepOverlay(w, h);
    const fam = this._fontFamily(s);
    const track = this._tracking(s);
    const fs = Math.max(14 * k, w * 0.048 * (0.55 + (s.text_size ?? 0.65)));
    const subFs = Math.max(11 * k, fs * 0.42);
    ox.textAlign = "center";
    ox.textBaseline = "top";
    let y = h * clamp(s.text_y ?? 0.86, 0.06, 0.94);
    y = Math.max(h * 0.05, Math.min(y, h - fs * (s.subtext ? 2.4 : 1.4)));
    const shadow = "rgba(0,0,0,0.86)";
    const drawSpaced = (text, size, fill, tr, yy) => {
      ox.font = `${size}px "${fam}", sans-serif`;
      ox.letterSpacing = `${tr}em`;
      // letterSpacing adds a trailing gap that centre alignment would include
      const x = w / 2 + (size * tr) / 2;
      ox.fillStyle = shadow;
      ox.fillText(text, x, yy + 3 * k);
      ox.fillStyle = fill;
      ox.fillText(text, x, yy);
      const m = ox.measureText("Ag");
      const used = (m.actualBoundingBoxAscent || 0) + (m.actualBoundingBoxDescent || 0);
      return used || size * 0.9;
    };
    if (s.text) {
      const used = drawSpaced(s.text, fs, rgba(pal.accent), track, y);
      y += used * 1.45;
    }
    if (s.subtext) {
      const subFill = rgba(pal.accent.map((c) => Math.min(255, c + 20)), 0.94);
      drawSpaced(s.subtext, subFs, subFill, Math.min(track + 0.04, 0.18), y);
    }
    ox.letterSpacing = "0px";
    this._stampOverlay(ctx, w, h, {
      glow: s.text_glow ?? 0,
      glitch: s.text_glitch ?? 0,
      chroma: s.text_chroma ?? 0,
      jitter: s.text_jitter ?? 0,
      opacity: s.text_opacity ?? 0.92,
    }, k);
  }

  _logo(ctx, w, h, s) {
    const img = this.logoImage;
    if (!img) return;
    const iw = img.naturalWidth || img.width;
    const ih = img.naturalHeight || img.height;
    if (!iw || !ih) return;
    let lw = Math.max(12, w * (s.logo_size ?? 0.18));
    let lh = lw * (ih / iw);
    if (lh > h * 0.42) {
      lh = h * 0.42;
      lw = lh * (iw / ih);
    }
    const pos = s.logo_position || "above-text";
    const mx = w * 0.055;
    const my = h * 0.045;
    let x = mx;
    let y = my;
    if (pos === "top-right") x = w - lw - mx;
    else if (pos === "lower-left") y = h - lh - my;
    else if (pos === "lower-right") {
      x = w - lw - mx;
      y = h - lh - my;
    } else if (pos === "above-text") {
      x = (w - lw) / 2;
      const ty = clamp(s.text_y ?? 0.86, 0.06, 0.94);
      y = Math.max(my, h * ty - lh - h * 0.025);
      y = Math.min(y, h - lh - my);
    }
    const ox = this._prepOverlay(w, h);
    ox.drawImage(img, x, y, lw, lh);
    this._stampOverlay(ctx, w, h, {
      glow: s.logo_glow ?? 0,
      glitch: s.logo_glitch ?? 0,
      chroma: s.logo_chroma ?? 0,
      jitter: s.logo_jitter ?? 0,
      opacity: s.logo_opacity ?? 1,
    }, w / 1080);
  }
}

function drawCover(ctx, img, w, h) {
  const iw = img.naturalWidth || img.width;
  const ih = img.naturalHeight || img.height;
  if (!iw || !ih) return;
  const scale = Math.max(w / iw, h / ih);
  const nw = iw * scale;
  const nh = ih * scale;
  ctx.drawImage(img, (w - nw) / 2, (h - nh) / 2, nw, nh);
}

// glow_polyline: dim wide stroke, mid stroke, full colour core (additive)
function glowPath(ctx, xs, ys, rgb, thickness, px, close = false) {
  if (!xs || xs.length < 2) return;
  const path = () => {
    ctx.beginPath();
    ctx.moveTo(xs[0], ys[0]);
    for (let i = 1; i < xs.length; i++) ctx.lineTo(xs[i], ys[i]);
    if (close) ctx.closePath();
  };
  path();
  ctx.strokeStyle = rgba(scaled(rgb, 0.28));
  ctx.lineWidth = Math.max(thickness + px(5), px(6));
  ctx.stroke();
  path();
  ctx.strokeStyle = rgba(scaled(rgb, 0.62));
  ctx.lineWidth = Math.max(thickness + px(2), px(3));
  ctx.stroke();
  path();
  ctx.strokeStyle = rgba(rgb);
  ctx.lineWidth = Math.max(thickness, px(1));
  ctx.stroke();
}
