function hexRgb(hex) {
  const h = String(hex || "#000000").replace("#", "");
  if (h.length !== 6) return [0, 0, 0];
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function paletteFromSettings(s) {
  return {
    bg: hexRgb(s.bg_color || "#050303"),
    fg: hexRgb(s.effect_color || "#d63d24"),
    accent: hexRgb(s.text_color || "#ede6dc"),
  };
}

export class Preview {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.settings = null;
    this.audio = null;
    this.buffer = null;
    this.actx = null;
    this.analyser = null;
    this.srcNode = null;
    this.running = false;
    this._lookKey = "";
    this.bgImage = null;
    this.grain = this._makeGrain();
    this.trail = document.createElement("canvas");
    this.tctx = this.trail.getContext("2d");
    this.bloom = document.createElement("canvas");
    this.bctx = this.bloom.getContext("2d");
    this.chroma = document.createElement("canvas");
    this.cctx = this.chroma.getContext("2d");
    this.particles = Array.from({ length: 120 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: 0,
      vy: 0,
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

  setSettings(s) {
    this.settings = s;
    const key = `${s?.bg_color || ""}|${s?.effect_color || ""}|${s?.text_color || ""}|${s?.scene || ""}|${s?.background_id || ""}|${s?.bg_opacity ?? ""}`;
    if (key !== this._lookKey) {
      this._lookKey = key;
      this.tctx.clearRect(0, 0, this.trail.width || 0, this.trail.height || 0);
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
    }
    return { w, h, dpr };
  }

  _bands() {
    if (!this.analyser) {
      return { freq: new Uint8Array(64), time: new Uint8Array(1024), bass: 0, mid: 0, high: 0, energy: 0 };
    }
    const freq = new Uint8Array(this.analyser.frequencyBinCount);
    const time = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteFrequencyData(freq);
    this.analyser.getByteTimeDomainData(time);
    const react = 0.35 + 0.65 * (this.settings?.reactivity ?? 0.85);
    const bass = Math.min(1.4, (avg(freq, 0, 24) / 255) * react);
    const mid = Math.min(1.4, (avg(freq, 24, 90) / 255) * react);
    const high = Math.min(1.4, (avg(freq, 90, 220) / 255) * react);
    const energy = bass * 0.45 + mid * 0.35 + high * 0.2;
    return { freq, time, bass, mid, high, energy };
  }

  _scopeFromBuffer(n, w, h) {
    const t = this.audio?.currentTime || 0;
    const sr = this.buffer?.sampleRate || 44100;
    const ch0 = this.buffer?.getChannelData(0);
    const ch1 = this.buffer && this.buffer.numberOfChannels > 1 ? this.buffer.getChannelData(1) : ch0;
    if (!ch0) return { xs: [], ys: [], lx: [], ly: [] };
    const center = Math.floor(t * sr);
    const xs = new Array(n);
    const ys = new Array(n);
    const lx = new Array(n);
    const ly = new Array(n);
    const amp = 0.28 + 0.2 * (this.settings?.intensity ?? 0.7);
    for (let i = 0; i < n; i++) {
      const idx = Math.max(0, Math.min(ch0.length - 1, center - Math.floor(n / 2) + i));
      const l = ch0[idx] || 0;
      const r = ch1[idx] || 0;
      xs[i] = (i / (n - 1)) * w;
      ys[i] = h * 0.5 - l * h * amp;
      lx[i] = w * 0.5 + l * w * amp;
      ly[i] = h * 0.5 + r * h * amp * 0.85;
    }
    return { xs, ys, lx, ly };
  }

  draw() {
    const { w, h } = this._size();
    const ctx = this.ctx;
    const s = this.settings || {};
    const pal = paletteFromSettings(s);
    const b = this._bands();
    const trailAmt = s.trail ?? 0.4;
    const lookKey = `${s.bg_color || ""}|${s.effect_color || ""}|${s.text_color || ""}|${s.scene || ""}|${s.background_id || ""}|${s.bg_opacity ?? ""}`;
    const lookChanged = lookKey !== this._lookKey;
    if (lookChanged) {
      this._lookKey = lookKey;
      this.tctx.clearRect(0, 0, this.trail.width, this.trail.height);
    } else if (trailAmt > 0.02) {
      this.tctx.globalAlpha = 0.4 + 0.55 * trailAmt;
      this.tctx.drawImage(this.canvas, 0, 0);
      this.tctx.globalAlpha = 1;
    }

    const tint = s.bg_opacity ?? 0.22;
    if (this.bgImage) {
      drawCover(ctx, this.bgImage, w, h);
      ctx.fillStyle = `rgba(${pal.bg[0]},${pal.bg[1]},${pal.bg[2]},${tint})`;
      ctx.fillRect(0, 0, w, h);
    } else {
      ctx.fillStyle = `rgb(${pal.bg[0]},${pal.bg[1]},${pal.bg[2]})`;
      ctx.fillRect(0, 0, w, h);
    }

    const g = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, Math.max(w, h) * 0.7);
    g.addColorStop(0, `rgba(${pal.fg[0]},${pal.fg[1]},${pal.fg[2]},${0.08 + b.energy * 0.18})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    if (trailAmt > 0.02) {
      ctx.globalAlpha = 0.2 + 0.7 * trailAmt;
      ctx.drawImage(this.trail, 0, 0);
      ctx.globalAlpha = 1;
    }

    const scene = !s.scene || s.scene === "auto" ? "mixed" : s.scene;
    const scope = this._scopeFromBuffer(420, w, h);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    if (scene === "oscilloscope" || scene === "mixed") {
      strokePath(ctx, scope.xs, scope.ys, pal.fg, 2 + (s.intensity ?? 0.7) * 2);
    }
    if (scene === "lissajous") {
      strokePath(ctx, scope.lx, scope.ly, pal.fg, 1.8);
    }
    if (scene === "spectrum" || scene === "tunnel") {
      this._ring(ctx, w, h, b, pal.fg);
    }
    if (scene === "tunnel") {
      this._tunnel(ctx, w, h, b, pal);
    }
    if (scene === "bars") {
      this._bars(ctx, w, h, b, pal.fg);
    }
    if (scene === "particles" || scene === "mixed") {
      this._particles(ctx, w, h, b, pal.fg);
    }
    if (scene === "starburst") this._starburst(ctx, w, h, b, pal.fg);
    if (scene === "grid") this._grid(ctx, w, h, b, pal.fg);
    if (scene === "kaleido") this._kaleido(ctx, w, h, scope, pal.fg);
    if (scene === "orbits") this._orbits(ctx, w, h, b, pal.fg);

    const gamt = s.glitch ?? 0;
    if (gamt > 0.02 && (b.energy * gamt > 0.08 || gamt > 0.45)) {
      const slices = 1 + Math.floor(gamt * 10 * (0.35 + b.energy));
      for (let i = 0; i < slices; i++) {
        const y = Math.random() * h;
        const hh = 3 + Math.random() * (6 + gamt * 24);
        const dx = (Math.random() - 0.5) * w * 0.1 * gamt;
        ctx.drawImage(this.canvas, 0, y, w, hh, dx, y, w, hh);
      }
    }

    this._bloom(ctx, w, h, s.bloom ?? 0);

    const grainA = (s.grain ?? 0.4) * 0.38;
    if (grainA > 0.01) {
      ctx.save();
      ctx.globalAlpha = grainA;
      ctx.globalCompositeOperation = "overlay";
      const ox = Math.random() * 64;
      const oy = Math.random() * 64;
      ctx.fillStyle = ctx.createPattern(this.grain, "repeat");
      ctx.translate(-ox, -oy);
      ctx.fillRect(0, 0, w + 128, h + 128);
      ctx.restore();
    }

    const sln = s.scanlines ?? 0.4;
    if (sln > 0.02) {
      ctx.fillStyle = `rgba(0,0,0,${0.28 * sln})`;
      for (let y = 0; y < h; y += 2) ctx.fillRect(0, y, w, 1);
      if (sln > 0.55) {
        ctx.fillStyle = `rgba(0,0,0,${0.12 * sln})`;
        for (let y = 1; y < h; y += 4) ctx.fillRect(0, y, w, 1);
      }
    }

    const vig = s.vignette ?? 0.7;
    const vg = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.2, w / 2, h / 2, Math.max(w, h) * 0.72);
    vg.addColorStop(0, "rgba(0,0,0,0)");
    vg.addColorStop(1, `rgba(0,0,0,${0.85 * vig})`);
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, w, h);

    this._chroma(ctx, w, h, s.chromatic ?? 0, b.high);

    this._text(ctx, w, h, pal);

    const jit = (s.jitter ?? 0.3) * (5 + b.bass * 12);
    this.canvas.style.transform = `translate(${(Math.random() - 0.5) * jit}px, ${(Math.random() - 0.5) * jit}px)`;
  }

  _bloom(ctx, w, h, amount) {
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
    bctx.filter = `blur(${3 + amount * 14}px)`;
    bctx.drawImage(this.canvas, 0, 0, bw, bh);
    bctx.filter = "none";
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = 0.4 + amount * 1.05;
    ctx.drawImage(buf, 0, 0, w, h);
    ctx.restore();
  }

  _chroma(ctx, w, h, amount, high) {
    if (amount < 0.02) return;
    const shift = Math.max(1, Math.round(1 + amount * 8 + high * 2));
    const buf = this.chroma;
    if (buf.width !== w || buf.height !== h) {
      buf.width = w;
      buf.height = h;
    }
    this.cctx.clearRect(0, 0, w, h);
    this.cctx.drawImage(this.canvas, 0, 0);
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    ctx.globalAlpha = Math.min(0.8, 0.2 + amount * 0.75);
    ctx.drawImage(buf, -shift, 0);
    ctx.drawImage(buf, shift, 0);
    ctx.restore();
  }

  _ring(ctx, w, h, b, rgb) {
    const n = 64;
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const idx = Math.floor((i % n) * (b.freq.length / n));
      const mag = (b.freq[idx] || 0) / 255;
      const a = (i / n) * Math.PI * 2;
      const r = Math.min(w, h) * (0.16 + mag * 0.22 * (this.settings?.intensity ?? 0.7));
      const x = w / 2 + Math.cos(a) * r;
      const y = h / 2 + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.9)`;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  _tunnel(ctx, w, h, b, pal) {
    const t = this.audio?.currentTime || 0;
    for (let i = 0; i < 10; i++) {
      const u = i / 10;
      const pulse = 0.7 + b.bass * 0.5;
      ctx.strokeStyle = `rgba(${pal.fg[0]},${pal.fg[1]},${pal.fg[2]},${0.15 + (1 - u) * 0.5})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(
        w / 2,
        h / 2,
        w * (0.08 + u * 0.45) * pulse,
        h * (0.08 + u * 0.38) * pulse,
        t * 0.2 + i * 0.08,
        0,
        Math.PI * 2
      );
      ctx.stroke();
    }
  }

  _bars(ctx, w, h, b, rgb) {
    const n = 48;
    const step = w / n;
    ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.85)`;
    for (let i = 0; i < n; i++) {
      const idx = Math.floor(i * (b.freq.length / n));
      const mag = (b.freq[idx] || 0) / 255;
      const bh = mag * h * 0.45;
      ctx.fillRect(i * step + 1, h * 0.78 - bh, Math.max(1, step - 2), bh);
    }
  }

  _particles(ctx, w, h, b, rgb) {
    ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.9)`;
    for (const p of this.particles) {
      p.vx += (Math.random() - 0.5) * 0.002;
      p.vy += (Math.random() - 0.5) * 0.002;
      const dx = p.x - 0.5;
      const dy = p.y - 0.5;
      if (b.energy > 0.5) {
        p.vx += dx * 0.01 * b.energy;
        p.vy += dy * 0.01 * b.energy;
      }
      p.vx *= 0.96;
      p.vy *= 0.96;
      p.x = (p.x + p.vx + 1) % 1;
      p.y = (p.y + p.vy + 1) % 1;
      ctx.fillRect(p.x * w, p.y * h, 2, 2);
    }
  }

  _starburst(ctx, w, h, b, rgb) {
    const n = 48;
    const t = this.audio?.currentTime || 0;
    const cx = w / 2;
    const cy = h / 2;
    const r0 = Math.min(w, h) * 0.04;
    const span = Math.min(w, h) * (0.22 + 0.28 * (this.settings?.intensity ?? 0.7));
    ctx.lineCap = "round";
    for (let i = 0; i < n; i++) {
      const idx = Math.floor(i * (b.freq.length / n));
      const mag = (b.freq[idx] || 0) / 255;
      const a = t * 0.2 + (i / n) * Math.PI * 2;
      const r1 = r0 + mag * span;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${0.35 + mag * 0.65})`;
      ctx.lineWidth = 1 + mag * 2;
      ctx.stroke();
    }
  }

  _grid(ctx, w, h, b, rgb) {
    const t = this.audio?.currentTime || 0;
    const step = Math.max(14, Math.min(w, h) * (0.08 - 0.03 * b.bass));
    const amp = 4 + 18 * b.mid * (this.settings?.intensity ?? 0.7);
    ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.55)`;
    ctx.lineWidth = 1;
    for (let x = 0; x < w + step; x += step) {
      ctx.beginPath();
      for (let y = 0; y <= h; y += 8) {
        const dx = Math.sin(y * 0.018 + t * 2.2) * amp;
        if (y === 0) ctx.moveTo(x + dx, y);
        else ctx.lineTo(x + dx, y);
      }
      ctx.stroke();
    }
    for (let y = 0; y < h + step; y += step) {
      ctx.beginPath();
      for (let x = 0; x <= w; x += 8) {
        const dy = Math.sin(x * 0.016 + t * 1.7) * amp * 0.7;
        if (x === 0) ctx.moveTo(x, y + dy);
        else ctx.lineTo(x, y + dy);
      }
      ctx.stroke();
    }
  }

  _kaleido(ctx, w, h, scope, rgb) {
    const cx = w / 2;
    const cy = h / 2;
    for (let k = 0; k < 6; k++) {
      const a = (k * Math.PI) / 3;
      const c = Math.cos(a);
      const s = Math.sin(a);
      const xs = [];
      const ys = [];
      for (let i = 0; i < scope.lx.length; i++) {
        const x = scope.lx[i] - cx;
        const y = scope.ly[i] - cy;
        xs.push(x * c - y * s + cx);
        ys.push(x * s + y * c + cy);
      }
      strokePath(ctx, xs, ys, rgb, 1.4);
    }
  }

  _orbits(ctx, w, h, b, rgb) {
    const t = this.audio?.currentTime || 0;
    const cx = w / 2;
    const cy = h / 2;
    for (let ring = 0; ring < 5; ring++) {
      const n = 10 + ring * 5;
      const r = Math.min(w, h) * (0.07 + ring * 0.07) * (1 + b.bass * 0.18);
      const speed = 0.35 + ring * 0.12;
      for (let i = 0; i < n; i++) {
        const u = i / n;
        const idx = Math.floor(u * (b.freq.length - 1));
        const mag = (b.freq[idx] || 0) / 255;
        const a = t * speed + u * Math.PI * 2;
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r * 0.72;
        ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${0.4 + mag * 0.6})`;
        const rad = 1 + mag * 3 * (this.settings?.intensity ?? 0.7);
        ctx.beginPath();
        ctx.arc(x, y, rad, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  _text(ctx, w, h, pal) {
    const s = this.settings || {};
    if (!s.text && !s.subtext) return;
    ctx.textAlign = "center";
    ctx.fillStyle = `rgba(${pal.accent[0]},${pal.accent[1]},${pal.accent[2]},${s.text_opacity ?? 0.9})`;
    const size = (s.text_size ?? 0.65) * w * 0.06;
    ctx.font = `600 ${size}px ui-sans-serif, system-ui, sans-serif`;
    ctx.letterSpacing = "0.14em";
    let y = h * 0.72;
    if (s.text_position === "top") y = h * 0.12;
    if (s.text_position === "center") y = h * 0.5;
    if (s.text) ctx.fillText(s.text, w / 2, y);
    if (s.subtext) {
      ctx.font = `400 ${size * 0.42}px ui-monospace, monospace`;
      ctx.fillStyle = `rgba(${pal.accent[0]},${pal.accent[1]},${pal.accent[2]},0.7)`;
      ctx.fillText(s.subtext, w / 2, y + size * 0.7);
    }
  }
}

function avg(arr, a, b) {
  let s = 0;
  let n = 0;
  const end = Math.min(arr.length, b);
  for (let i = a; i < end; i++) {
    s += arr[i];
    n++;
  }
  return n ? s / n : 0;
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

function strokePath(ctx, xs, ys, rgb, width) {
  if (!xs.length) return;
  ctx.beginPath();
  ctx.moveTo(xs[0], ys[0]);
  for (let i = 1; i < xs.length; i++) ctx.lineTo(xs[i], ys[i]);
  ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.35)`;
  ctx.lineWidth = width + 6;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(xs[0], ys[0]);
  for (let i = 1; i < xs.length; i++) ctx.lineTo(xs[i], ys[i]);
  ctx.strokeStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  ctx.lineWidth = width;
  ctx.stroke();
}
