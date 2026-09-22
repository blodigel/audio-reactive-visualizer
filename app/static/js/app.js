import { api, uploadWav } from "./api.js?v=27";
import { Preview } from "./preview.js?v=27";
import { Waveform, formatTime } from "./waveform.js?v=27";

const $ = (id) => document.getElementById(id);

const state = {
  catalog: null,
  track: null,
  settings: {
    scene: "mixed",
    bg_color: "#050303",
    effect_color: "#d63d24",
    text_color: "#ede6dc",
    background_id: "",
    font: "archivo",
    font_id: "",
    logo_id: "",
    logo_position: "above-text",
    logo_size: 0.18,
    logo_opacity: 1,
    logo_glow: 0,
    logo_glitch: 0,
    logo_chroma: 0,
    logo_jitter: 0,
    bg_opacity: 0.22,
    bg_blur: 0,
    bg_brightness: 0.5,
    bg_saturation: 1,
    bg_grain: 0,
    bg_glitch: 0,
    bg_scanlines: 0,
    bg_chroma: 0,
    bg_reactivity: 0,
    bg_punch: 0,
    grain: 0.48,
    jitter: 0.32,
    bloom: 0.22,
    intensity: 0.78,
    glitch: 0.38,
    scanlines: 0.52,
    vignette: 0.72,
    chromatic: 0.22,
    trail: 0.42,
    reactivity: 0.88,
    text: "",
    subtext: "",
    text_position: "lower",
    text_y: 0.86,
    text_size: 0.65,
    text_opacity: 0.92,
    text_glow: 0,
    text_glitch: 0,
    text_chroma: 0,
    text_jitter: 0,
    seed: 1,
  },
  // Output belongs to the render job, not to a clip's look.
  output: { format: "reels", quality: "standard", fps: 30 },
  job: null,
  poll: null,
  bgName: "",
  bgKind: "",
  bgNames: {},
  bgKinds: {},
  textFocus: -1,
  fontName: "",
  fontNames: {},
  logoName: "",
  logoNames: {},
  activeClipId: null,
  safeArea: false,
};

const SESSION_KEY = "nv-session-v1";
const LOOKS_KEY = "nv-looks-v1";
// A look is style: scene, palette, background, sliders, type and logo styling.
// Not content (title, subtext, logo file) and not output (format, quality, fps).
const LOOK_KEYS = [
  "scene",
  "bg_color",
  "effect_color",
  "text_color",
  "background_id",
  "bg_opacity",
  "bg_blur",
  "bg_brightness",
  "bg_saturation",
  "bg_grain",
  "bg_glitch",
  "bg_scanlines",
  "bg_chroma",
  "bg_reactivity",
  "bg_punch",
  "font",
  "font_id",
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
  "text_position",
  "text_y",
  "text_size",
  "text_opacity",
  "text_glow",
  "text_glitch",
  "text_chroma",
  "text_jitter",
  "logo_position",
  "logo_size",
  "logo_opacity",
  "logo_glow",
  "logo_glitch",
  "logo_chroma",
  "logo_jitter",
];
const OUTPUT_KEYS = ["format", "quality", "fps"];

function lookOf(settings) {
  const out = {};
  for (const k of LOOK_KEYS) if (settings[k] !== undefined) out[k] = settings[k];
  if (Array.isArray(settings.text_boxes)) {
    out.text_layout = settings.text_boxes.map((b) => ({
      on: Boolean(b.on),
      x: b.x,
      y: b.y,
      size: b.size,
    }));
  }
  return out;
}

const TEXT_BOX_COUNT = 6;
const TEXT_BOX_SEED = [
  { on: true, x: 0.5, y: 0.86, size: 0.65 },
  { on: true, x: 0.5, y: 0.94, size: 0.28 },
  { on: false, x: 0.5, y: 0.16, size: 0.55 },
  { on: false, x: 0.5, y: 0.5, size: 0.55 },
  { on: false, x: 0.22, y: 0.78, size: 0.4 },
  { on: false, x: 0.78, y: 0.78, size: 0.4 },
];
const TEXT_BOX_LABELS = ["Title", "Subtext", "Text 3", "Text 4", "Text 5", "Text 6"];

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, Number(v)));
}

function ensureBgFx(s) {
  if (!s) return;
  if (s.bg_blur == null) s.bg_blur = 0;
  if (s.bg_brightness == null) s.bg_brightness = 0.5;
  if (s.bg_saturation == null) s.bg_saturation = 1;
  if (s.bg_grain == null) s.bg_grain = 0;
  if (s.bg_glitch == null) s.bg_glitch = 0;
  if (s.bg_scanlines == null) s.bg_scanlines = 0;
  if (s.bg_chroma == null) s.bg_chroma = 0;
  if (s.bg_reactivity == null) s.bg_reactivity = 0;
  if (s.bg_punch == null) s.bg_punch = 0;
}

function ensureTextBoxes(s) {
  if (!s) return s;
  const existing = Array.isArray(s.text_boxes) ? s.text_boxes : null;
  if (!existing || !existing.length) {
    const y = clamp(s.text_y ?? 0.86, 0.02, 0.98);
    s.text_boxes = TEXT_BOX_SEED.map((seed, i) => ({
      on: i < 2 ? true : seed.on,
      text: i === 0 ? String(s.text || "") : i === 1 ? String(s.subtext || "") : "",
      x: seed.x,
      y: i === 0 ? y : i === 1 ? Math.min(0.98, y + 0.08) : seed.y,
      size: i === 0 ? clamp(s.text_size ?? seed.size, 0.15, 1.5) : seed.size,
    }));
    return s;
  }
  const boxes = existing.slice(0, TEXT_BOX_COUNT);
  while (boxes.length < TEXT_BOX_COUNT) {
    const seed = TEXT_BOX_SEED[boxes.length];
    boxes.push({ on: boxes.length < 2, text: "", x: seed.x, y: seed.y, size: seed.size });
  }
  for (let i = 0; i < boxes.length; i++) {
    const b = boxes[i] || {};
    const seed = TEXT_BOX_SEED[i];
    boxes[i] = {
      on: i < 2 ? true : b.on !== undefined ? Boolean(b.on) : seed.on,
      text: String(b.text || ""),
      x: clamp(b.x ?? seed.x, 0.02, 0.98),
      y: clamp(b.y ?? seed.y, 0.02, 0.98),
      size: clamp(b.size ?? seed.size, 0.15, 1.5),
    };
  }
  s.text_boxes = boxes;
  return s;
}

function mirrorPrimary(s) {
  const boxes = s?.text_boxes;
  if (!boxes?.length) return;
  s.text = boxes[0].text || "";
  s.subtext = boxes[1]?.on ? boxes[1].text || "" : "";
  s.text_y = clamp(boxes[0].y, 0.06, 0.94);
  s.text_size = clamp(boxes[0].size, 0.2, 1.5);
}

function cloneSettings(s) {
  const copy = { ...s };
  if (Array.isArray(s?.text_boxes)) copy.text_boxes = s.text_boxes.map((b) => ({ ...b }));
  return copy;
}

function stripOutput(settings) {
  if (!settings) return settings;
  for (const k of OUTPUT_KEYS) delete settings[k];
  return settings;
}

const audioEl = new Audio();
audioEl.preload = "auto";
const preview = new Preview($("viz"));
const wave = new Waveform($("wave"), ({ clips, selected }) => {
  if (selected !== state.activeClipId) {
    const prev = wave.clips.find((c) => c.id === state.activeClipId);
    if (prev) prev.settings = cloneSettings(state.settings);
    state.activeClipId = selected;
    loadClipSettings(selected);
  }
  for (const c of clips) {
    if (!c.settings) c.settings = cloneSettings(state.settings);
  }
  renderClipList(clips, selected);
  updatePlayRange();
  syncFadeControls();
  scheduleSave();
});

function toast(msg) {
  const el = $("toast");
  el.hidden = false;
  el.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 4200);
}

function seg(container, items, current, onPick, labelKey = "label") {
  if (!container) return;
  container.innerHTML = "";
  for (const item of items || []) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = item[labelKey] || item.id;
    b.title = item.blurb || "";
    b.className = item.id === current ? "on" : "";
    b.addEventListener("click", () => onPick(item.id));
    container.appendChild(b);
  }
}

function persistClipSettings() {
  mirrorPrimary(state.settings);
  const c = wave.selectedClip();
  if (c) c.settings = cloneSettings(state.settings);
  scheduleSave();
}

function saveSession() {
  try {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({
        track_id: state.track?.id || "",
        job_id: state.job?.id || "",
        output: state.output,
        settings: state.settings,
        clips: wave.clips.map((c) => ({
          id: c.id,
          start: c.start,
          end: c.end,
          fade_in: c.fade_in || 0,
          fade_out: c.fade_out || 0,
          reason: c.reason || "",
          settings: c.settings || null,
        })),
        selected: wave.selected,
        bgNames: state.bgNames,
        bgKinds: state.bgKinds,
        fontNames: state.fontNames,
        logoNames: state.logoNames,
        safeArea: Boolean(state.safeArea),
      })
    );
  } catch {
    /* quota / private mode */
  }
}

let _saveTimer = 0;
function scheduleSave() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(saveSession, 250);
}

function loadUserLooks() {
  try {
    const raw = JSON.parse(localStorage.getItem(LOOKS_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

function storeUserLooks(list) {
  localStorage.setItem(LOOKS_KEY, JSON.stringify(list));
}

function applyLook(look) {
  const bundled = Boolean(look.bundled);
  const src = look.settings || look;
  for (const k of LOOK_KEYS) {
    if (src[k] !== undefined) state.settings[k] = src[k];
  }
  ensureTextBoxes(state.settings);
  if (Array.isArray(src.text_layout) && src.text_layout.length) {
    src.text_layout.forEach((lay, i) => {
      const b = state.settings.text_boxes[i];
      if (!b || !lay) return;
      if (i >= 2 && lay.on !== undefined) b.on = Boolean(lay.on);
      if (lay.x !== undefined) b.x = clamp(lay.x, 0.02, 0.98);
      if (lay.y !== undefined) b.y = clamp(lay.y, 0.02, 0.98);
      if (lay.size !== undefined) b.size = clamp(lay.size, 0.15, 1.5);
    });
  } else {
    const b = state.settings.text_boxes[0];
    if (src.text_y !== undefined) b.y = clamp(src.text_y, 0.02, 0.98);
    if (src.text_size !== undefined) b.size = clamp(src.text_size, 0.15, 1.5);
  }
  mirrorPrimary(state.settings);
  // bundled looks name a bundled font; a lingering custom upload must not win
  if (bundled) state.settings.font_id = "";
  state.bgKind = state.bgKinds[state.settings.background_id] || "";
  state.bgName = state.bgNames[state.settings.background_id] || (state.settings.background_id ? "background" : "");
  state.fontName = state.fontNames[state.settings.font_id] || (state.settings.font_id ? "custom font" : "");
  afterLookChange();
  loadPreviewBg(state.settings.background_id);
  loadPreviewLogo(state.settings.logo_id);
  if (state.settings.font_id) {
    installCustomFont(state.settings.font_id, `/api/fonts/${state.settings.font_id}`);
  }
  preview.setSettings({ ...state.settings });
  syncControls();
}

function paintLooks() {
  const box = $("looks");
  if (!box) return;
  const bundled = state.catalog?.looks || [];
  const saved = loadUserLooks();
  const s = state.settings;
  box.innerHTML = "";
  const addChip = (look, user) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = look.label || look.id;
    if (user) b.classList.add("user");
    const src = look.settings || look;
    if (src.scene === s.scene && src.effect_color === s.effect_color && src.bg_color === s.bg_color) {
      b.classList.add("on");
    }
    b.addEventListener("click", () => applyLook(look));
    if (user) {
      const x = document.createElement("span");
      x.className = "look-x";
      x.textContent = "×";
      x.title = "Remove saved look";
      x.addEventListener("click", (ev) => {
        ev.stopPropagation();
        storeUserLooks(loadUserLooks().filter((l) => l.id !== look.id));
        paintLooks();
      });
      b.appendChild(x);
    }
    box.appendChild(b);
  };
  bundled.forEach((l) => addChip(l, false));
  saved.forEach((l) => addChip(l, true));
}

function paintSliderGroup(containerId, list) {
  const box = $(containerId);
  if (!box) return;
  const s = state.settings;
  box.innerHTML = "";
  for (const sl of list || []) {
    const wrap = document.createElement("div");
    wrap.className = "slider";
    wrap.innerHTML = `<label>${sl.label}</label><span class="val"></span>`;
    const input = document.createElement("input");
    input.type = "range";
    input.min = "0";
    input.max = "1";
    input.step = "0.01";
    input.value = String(s[sl.key] ?? 0);
    input.title = sl.blurb || sl.label;
    const val = wrap.querySelector(".val");
    const paint = () => {
      val.textContent = Number(input.value).toFixed(2);
    };
    paint();
    input.addEventListener("input", () => {
      s[sl.key] = Number(input.value);
      paint();
      persistClipSettings();
      preview.setSettings({ ...state.settings });
    });
    wrap.appendChild(input);
    box.appendChild(wrap);
  }
}

function afterLookChange() {
  persistClipSettings();
  const label = $("clip-edit");
  const clip = wave.selectedClip();
  if (label && clip) {
    const idx = wave.clips.indexOf(clip) + 1;
    label.textContent = `Editing clip ${idx} · ${state.settings.scene || "mixed"}`;
  }
  wave.draw();
  renderClipList(wave.clips, wave.selected);
}

function clipFadeGain(t, clip) {
  if (!clip) return 1;
  const dur = Math.max(0.001, clip.end - clip.start);
  const local = t - clip.start;
  let g = 1;
  const fi = Math.min(clip.fade_in || 0, dur);
  const fo = Math.min(clip.fade_out || 0, dur);
  if (fi > 0.0005 && local < fi) g *= Math.max(0, local / fi);
  if (fo > 0.0005 && dur - local < fo) g *= Math.max(0, (dur - local) / fo);
  return Math.max(0, Math.min(1, g));
}

function syncFadeControls() {
  const clip = wave.selectedClip();
  const fi = $("fade-in");
  const fo = $("fade-out");
  if (!fi || !fo) return;
  if (!clip) {
    fi.disabled = true;
    fo.disabled = true;
    return;
  }
  fi.disabled = false;
  fo.disabled = false;
  const max = Math.min(8, Math.max(0, clip.end - clip.start));
  fi.max = String(max);
  fo.max = String(max);
  const vin = Math.min(clip.fade_in || 0, max);
  const vout = Math.min(clip.fade_out || 0, max);
  clip.fade_in = vin;
  clip.fade_out = vout;
  fi.value = String(vin);
  fo.value = String(vout);
  $("fade-in-val").textContent = `${vin.toFixed(2)}s`;
  $("fade-out-val").textContent = `${vout.toFixed(2)}s`;
  preview.setClipFade(clip);
}

function loadClipSettings(id) {
  const c = wave.clips.find((x) => x.id === id);
  const label = $("clip-edit");
  if (!c) {
    if (label) label.textContent = "Settings apply to the selected clip";
    return;
  }
  if (!c.settings) c.settings = cloneSettings(state.settings);
  ensureTextBoxes(c.settings);
  Object.assign(state.settings, stripOutput(cloneSettings(c.settings)));
  ensureTextBoxes(state.settings);
  mirrorPrimary(state.settings);
  state.bgKind = state.bgKinds[state.settings.background_id] || "";
  state.bgName = state.bgNames[state.settings.background_id] || (state.settings.background_id ? "background" : "");
  state.fontName = state.fontNames[state.settings.font_id] || (state.settings.font_id ? "custom font" : "");
  state.logoName = state.logoNames[state.settings.logo_id] || (state.settings.logo_id ? "logo" : "");
  const idx = wave.clips.indexOf(c) + 1;
  if (label) {
    label.textContent = `Editing clip ${idx} · ${c.settings.scene || "mixed"}`;
  }
  loadPreviewBg(state.settings.background_id);
  loadPreviewLogo(state.settings.logo_id);
  if (state.settings.font_id) installCustomFont(state.settings.font_id, `/api/fonts/${state.settings.font_id}`);
  syncFadeControls();
  syncControls();
}

function installCatalogFonts(fonts) {
  for (const f of fonts || []) {
    const id = `ff-${f.id}`;
    if (document.getElementById(id)) continue;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = `@font-face{font-family:"${f.family}";src:url("${f.url}?v=10") format("truetype");font-display:swap;}`;
    document.head.appendChild(el);
  }
}

function installCustomFont(id, url) {
  const fam = `nv-custom-${id}`;
  const elId = `ff-custom-${id}`;
  if (!document.getElementById(elId)) {
    const el = document.createElement("style");
    el.id = elId;
    el.textContent = `@font-face{font-family:"${fam}";src:url("${url}");font-display:swap;}`;
    document.head.appendChild(el);
  }
  return fam;
}

function paintFonts() {
  const box = $("fonts");
  if (!box) return;
  const fonts = state.catalog?.fonts || [];
  const s = state.settings;
  box.innerHTML = "";
  for (const f of fonts) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = f.label;
    b.title = f.blurb || f.family;
    b.style.fontFamily = `"${f.family}", sans-serif`;
    const on = !s.font_id && s.font === f.id;
    if (on) b.className = "on";
    b.addEventListener("click", () => {
      s.font = f.id;
      s.font_id = "";
      state.fontName = "";
      afterLookChange();
      preview.setSettings({ ...state.settings });
      syncControls();
    });
    box.appendChild(b);
  }
  if (s.font_id) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = state.fontName || "Custom";
    b.className = "on";
    b.style.fontFamily = `"nv-custom-${s.font_id}", sans-serif`;
    box.appendChild(b);
  }
}

function applyPalette(p) {
  state.settings.bg_color = p.bg_color;
  state.settings.effect_color = p.effect_color;
  state.settings.text_color = p.text_color;
  afterLookChange();
  preview.setSettings({ ...state.settings });
  syncControls();
}

function bindColor(inputId, hexId, key) {
  const input = $(inputId);
  const hex = $(hexId);
  if (!input || !hex) return;
  input.value = state.settings[key];
  hex.textContent = state.settings[key];
  const apply = () => {
    state.settings[key] = input.value;
    hex.textContent = input.value;
    persistClipSettings();
    preview.setSettings({ ...state.settings });
    paintSwatches();
    wave.draw();
    renderClipList(wave.clips, wave.selected);
  };
  input.oninput = apply;
  input.onchange = apply;
}

function paintSwatches() {
  const box = $("swatches");
  if (!box) return;
  const palettes = state.catalog?.palettes || [];
  box.innerHTML = "";
  const s = state.settings;
  for (const p of palettes) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "swatch";
    b.title = p.label;
    const on =
      p.bg_color === s.bg_color &&
      p.effect_color === s.effect_color &&
      p.text_color === s.text_color;
    if (on) b.classList.add("on");
    b.innerHTML = `<i style="background:${p.effect_color}"></i><i style="background:${p.bg_color}"></i>`;
    b.addEventListener("click", () => applyPalette(p));
    box.appendChild(b);
  }
}

function syncControls() {
  const s = state.settings;
  const c = state.catalog || {};
  paintLooks();
  paintSwatches();
  bindColor("bg-color", "bg-hex", "bg_color");
  bindColor("effect-color", "effect-hex", "effect_color");
  bindColor("text-color", "text-hex", "text_color");
  paintFonts();
  seg($("scenes"), c.scenes, s.scene, (id) => {
    s.scene = id;
    afterLookChange();
    syncControls();
  });
  seg($("formats"), c.formats, state.output.format, (id) => {
    state.output.format = id;
    $("stage").dataset.format = id;
    const f = c.formats.find((x) => x.id === id);
    $("format-tag").textContent = f?.ratio || id;
    preview.setFormat(id);
    scheduleSave();
    syncControls();
  });
  seg($("qualities"), c.qualities, state.output.quality, (id) => {
    state.output.quality = id;
    scheduleSave();
    syncControls();
  });
  ensureBgFx(s);
  paintSliderGroup("bg-sliders", c.bg_sliders);
  paintSliderGroup("viz-sliders", c.viz_sliders);
  paintSliderGroup("text-fx", c.text_fx);
  paintSliderGroup("logo-fx", c.logo_fx);
  ensureTextBoxes(s);
  mirrorPrimary(s);
  paintTextBoxes();
  preview.setTextFocus(state.textFocus);
  $("logo-size").value = String(s.logo_size ?? 0.18);
  const safe = $("safe-area");
  if (safe) safe.checked = Boolean(state.safeArea);
  preview.setSafeArea(Boolean(state.safeArea));
  preview.setFormat(state.output.format);
  preview.setSettings({ ...s });
  $("stage").dataset.format = state.output.format;
  const fmtMeta = (c.formats || []).find((x) => x.id === state.output.format);
  if ($("format-tag")) $("format-tag").textContent = fmtMeta?.ratio || state.output.format;
  const hasBg = Boolean(s.background_id);
  $("bg-clear").hidden = !hasBg;
  $("bg-name").textContent = hasBg ? state.bgName || (state.bgKind === "video" ? "video" : "image") : "";
  const hasFont = Boolean(s.font_id);
  $("font-clear").hidden = !hasFont;
  $("font-name").textContent = hasFont ? state.fontName || "custom font" : "";
  const hasLogo = Boolean(s.logo_id);
  $("logo-clear").hidden = !hasLogo;
  $("logo-name").textContent = hasLogo ? state.logoName || "logo" : "";
  seg($("logopos"), c.logo_positions || [], s.logo_position, (id) => {
    s.logo_position = id;
    afterLookChange();
    preview.setSettings({ ...state.settings });
    syncControls();
  });
}

function renderClipList(clips, selected) {
  const el = $("clip-list");
  el.innerHTML = "";
  clips.forEach((c, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "clip-chip" + (c.id === selected ? " on" : "");
    const len = (c.end - c.start).toFixed(1);
    const scene = (c.settings && c.settings.scene) || "";
    const col = (c.settings && c.settings.effect_color) || "#d4523e";
    b.innerHTML = `${i + 1} · ${formatTime(c.start)}–${formatTime(c.end)} <span class="why">${len}s ${scene}</span><span class="dot" style="background:${col}"></span>`;
    b.addEventListener("click", () => {
      wave.selected = c.id;
      wave._emit();
    });
    el.appendChild(b);
  });
  $("render").disabled = !clips.length || !state.track;
}

function updatePlayRange() {
  const clip = wave.selectedClip();
  if (clip && audioEl.src) {
    if (audioEl.currentTime < clip.start || audioEl.currentTime >= clip.end) {
      audioEl.currentTime = clip.start;
    }
  }
}

function setWorkspace(on) {
  $("drop").hidden = on;
  $("stage").hidden = !on;
  $("timeline").hidden = !on;
  $("transport").hidden = !on;
}

async function loadTrack(meta, restore) {
  state.track = meta;
  $("track-label").textContent = `${meta.filename}  ·  ${formatTime(meta.duration)}  ·  ${meta.sample_rate} Hz  ·  ${meta.channels}ch`;
  wave.setTrack(meta);
  if (restore?.clips?.length) {
    wave.setClips(restore.clips, restore.selected || restore.clips[0].id);
    state.activeClipId = wave.selected;
    loadClipSettings(wave.selected);
  } else {
    wave.fromSuggestions(meta.suggestions || []);
  }
  $("stage-empty").hidden = true;
  preview.setSettings(state.settings);
  preview.start();
  setWorkspace(true);
  requestAnimationFrame(() => wave.draw());
  audioEl.src = `/api/tracks/${meta.id}/audio`;
  try {
    const buf = await fetch(audioEl.src).then((r) => r.arrayBuffer());
    const attach = preview.attachAudio(audioEl, buf);
    const timeout = new Promise((_, rej) =>
      setTimeout(() => rej(new Error("audio decode timeout")), 12000)
    );
    await Promise.race([attach, timeout]);
  } catch (err) {
    console.warn(err);
  }
  scheduleSave();
}

async function handleFile(file) {
  if (!file) return;
  $("job-pill").textContent = "uploading";
  $("job-pill").className = "pill busy";
  try {
    const meta = await uploadWav(file, (p) => {
      $("job-pill").textContent = `up ${Math.round(p * 100)}%`;
    });
    $("job-pill").textContent = "ready";
    $("job-pill").className = "pill";
    await loadTrack(meta);
  } catch (err) {
    $("job-pill").textContent = "idle";
    $("job-pill").className = "pill";
    toast(err.message || String(err));
  }
}

function currentClipWindow() {
  const clip = wave.selectedClip();
  if (clip) return clip;
  return { start: 0, end: state.track?.duration || 0 };
}

let bgToken = 0;
async function loadPreviewBg(id) {
  const token = ++bgToken;
  if (!id) {
    state.bgKind = "";
    preview.setBackground(null);
    return;
  }
  let kind = state.bgKinds[id] || "";
  if (!kind) {
    try {
      const meta = await api(`/api/backgrounds/${id}/meta`);
      if (token !== bgToken) return;
      kind = meta.kind || "image";
      state.bgKinds[id] = kind;
      if (meta.filename && !state.bgNames[id]) state.bgNames[id] = meta.filename;
    } catch {
      kind = "image";
    }
  }
  if (token !== bgToken) return;
  state.bgKind = kind;
  if (kind === "video") {
    preview.setVideoBackground(`/api/backgrounds/${id}/video`);
  } else {
    const img = new Image();
    img.onload = () => {
      if (token !== bgToken) return;
      preview.setBackground(img);
    };
    img.onerror = () => toast("Could not load background image");
    img.src = `/api/backgrounds/${id}`;
  }
}

function loadPreviewLogo(id) {
  if (!id) {
    preview.setLogo(null);
    return;
  }
  const img = new Image();
  img.onload = () => preview.setLogo(img);
  img.onerror = () => toast("Could not load logo");
  img.src = `/api/logos/${id}`;
}

$("bg-import").addEventListener("click", () => $("bg-file").click());
$("bg-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const meta = await api("/api/backgrounds", { method: "POST", body: fd });
    state.settings.background_id = meta.id;
    state.bgKind = meta.kind || "image";
    state.bgKinds[meta.id] = state.bgKind;
    state.bgName = meta.filename || (state.bgKind === "video" ? "video" : "image");
    state.bgNames[meta.id] = state.bgName;
    loadPreviewBg(meta.id);
    persistClipSettings();
    syncControls();
  } catch (err) {
    toast(err.message || String(err));
  }
});
$("bg-clear").addEventListener("click", () => {
  state.settings.background_id = "";
  state.bgName = "";
  state.bgKind = "";
  preview.setBackground(null);
  persistClipSettings();
  syncControls();
});

$("font-import").addEventListener("click", () => $("font-file").click());
$("font-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const meta = await api("/api/fonts", { method: "POST", body: fd });
    state.settings.font = "custom";
    state.settings.font_id = meta.id;
    state.fontName = meta.family || meta.filename || "custom font";
    state.fontNames[meta.id] = state.fontName;
    installCustomFont(meta.id, meta.url);
    persistClipSettings();
    preview.setSettings({ ...state.settings });
    syncControls();
  } catch (err) {
    toast(err.message || String(err));
  }
});
$("font-clear").addEventListener("click", () => {
  state.settings.font_id = "";
  state.settings.font = "archivo";
  state.fontName = "";
  persistClipSettings();
  preview.setSettings({ ...state.settings });
  syncControls();
});

$("logo-import").addEventListener("click", () => $("logo-file").click());
$("logo-file").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const meta = await api("/api/logos", { method: "POST", body: fd });
    state.settings.logo_id = meta.id;
    state.logoName = meta.filename || "logo";
    state.logoNames[meta.id] = state.logoName;
    loadPreviewLogo(meta.id);
    persistClipSettings();
    syncControls();
  } catch (err) {
    toast(err.message || String(err));
  }
});
$("logo-clear").addEventListener("click", () => {
  state.settings.logo_id = "";
  state.logoName = "";
  preview.setLogo(null);
  persistClipSettings();
  syncControls();
});
$("logo-size").addEventListener("input", (e) => {
  state.settings.logo_size = Number(e.target.value);
  persistClipSettings();
  preview.setSettings({ ...state.settings });
});

$("browse").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => handleFile(e.target.files[0]));
$("replace").addEventListener("click", () => $("file").click());
$("demo").addEventListener("click", async () => {
  $("job-pill").textContent = "demo";
  $("job-pill").className = "pill busy";
  try {
    const meta = await api("/api/tracks/demo", { method: "POST" });
    $("job-pill").textContent = "ready";
    $("job-pill").className = "pill";
    await loadTrack(meta);
  } catch (err) {
    $("job-pill").textContent = "idle";
    $("job-pill").className = "pill";
    toast(err.message || String(err));
  }
});

["dragenter", "dragover"].forEach((ev) => {
  window.addEventListener(ev, (e) => {
    e.preventDefault();
    $("drop").classList.add("over");
  });
});
["dragleave", "drop"].forEach((ev) => {
  window.addEventListener(ev, (e) => {
    e.preventDefault();
    $("drop").classList.remove("over");
  });
});
window.addEventListener("drop", (e) => {
  const f = e.dataTransfer?.files?.[0];
  if (!f) return;
  const name = (f.name || "").toLowerCase();
  const image = (f.type || "").startsWith("image/") || /\.(png|jpe?g|webp)$/.test(name);
  if (image) {
    const dt = new DataTransfer();
    dt.items.add(f);
    $("bg-file").files = dt.files;
    $("bg-file").dispatchEvent(new Event("change"));
    return;
  }
  handleFile(f);
});

$("play").addEventListener("click", async () => {
  if (!state.track) return;
  if (preview.actx?.state === "suspended") await preview.actx.resume();
  if (audioEl.paused) {
    const w = currentClipWindow();
    if (audioEl.currentTime < w.start || audioEl.currentTime >= w.end) {
      audioEl.currentTime = w.start;
    }
    await audioEl.play();
    $("play").textContent = "Pause";
  } else {
    audioEl.pause();
    $("play").textContent = "Play";
  }
});

audioEl.addEventListener("pause", () => {
  $("play").textContent = "Play";
});

function tick() {
  const t = audioEl.currentTime || 0;
  wave.setPlayhead(t);
  const w = currentClipWindow();
  $("clock").textContent = `${formatTime(t)}  /  ${formatTime(w.end)}`;
  const clip = wave.selectedClip();
  audioEl.volume = clipFadeGain(t, clip);
  preview.setClipFade(clip);
  if (!audioEl.paused && $("loop").checked && t >= w.end - 0.03) {
    audioEl.currentTime = w.start;
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

function bindFadeSlider(id, key, valId) {
  $(id).addEventListener("input", (e) => {
    const clip = wave.selectedClip();
    if (!clip) return;
    const max = Math.min(8, Math.max(0, clip.end - clip.start));
    const v = Math.min(max, Math.max(0, Number(e.target.value)));
    clip[key] = v;
    $(valId).textContent = `${v.toFixed(2)}s`;
    preview.setClipFade(clip);
    wave.draw();
  });
}
bindFadeSlider("fade-in", "fade_in", "fade-in-val");
bindFadeSlider("fade-out", "fade_out", "fade-out-val");

function focusTextBox(i) {
  state.textFocus = i;
  preview.setTextFocus(i);
  document.querySelectorAll(".text-box").forEach((el) => {
    el.classList.toggle("on", Number(el.dataset.i) === i);
  });
}

function updateTextReadout(i) {
  const row = document.querySelector(`.text-box[data-i="${i}"]`);
  const b = state.settings.text_boxes?.[i];
  if (!row || !b) return;
  for (const key of ["x", "y", "size"]) {
    const input = row.querySelector(`input[data-k="${key}"]`);
    const val = row.querySelector(`[data-val="${key}"]`);
    if (input && document.activeElement !== input) input.value = String(b[key]);
    if (val) val.textContent = Number(b[key]).toFixed(2);
  }
}

function paintTextBoxes() {
  const host = $("text-boxes");
  if (!host) return;
  ensureTextBoxes(state.settings);
  const boxes = state.settings.text_boxes;
  host.innerHTML = "";
  boxes.forEach((b, i) => {
    if (i >= 2 && !b.on) return;
    const row = document.createElement("div");
    row.className = "text-box" + (i === state.textFocus ? " on" : "");
    row.dataset.i = String(i);
    const head = document.createElement("div");
    head.className = "text-box-head";
    const label = document.createElement("span");
    label.textContent = TEXT_BOX_LABELS[i] || `Text ${i + 1}`;
    head.appendChild(label);
    if (i >= 2) {
      const hide = document.createElement("button");
      hide.type = "button";
      hide.className = "btn btn-sm";
      hide.textContent = "Hide";
      hide.addEventListener("click", (ev) => {
        ev.stopPropagation();
        b.on = false;
        if (state.textFocus === i) state.textFocus = 0;
        mirrorPrimary(state.settings);
        persistClipSettings();
        preview.setTextFocus(state.textFocus);
        preview.setSettings(state.settings);
        paintTextBoxes();
      });
      head.appendChild(hide);
    }
    row.appendChild(head);
    const field = document.createElement("input");
    field.className = "field";
    field.type = "text";
    field.maxLength = 80;
    field.placeholder = i === 0 ? "TITLE" : i === 1 ? "subtext / artist" : "text";
    field.value = b.text || "";
    field.addEventListener("focus", () => focusTextBox(i));
    field.addEventListener("input", () => {
      b.text = field.value;
      mirrorPrimary(state.settings);
      persistClipSettings();
      preview.setSettings(state.settings);
    });
    row.appendChild(field);
    const axes = document.createElement("div");
    axes.className = "text-axes";
    for (const key of [
      ["x", 0.02, 0.98],
      ["y", 0.02, 0.98],
      ["size", 0.15, 1.5],
    ]) {
      const [name, min, max] = key;
      const lab = document.createElement("label");
      lab.className = "mini";
      lab.innerHTML = `<span class="text-axis-name">${name} <b data-val="${name}">${Number(b[name]).toFixed(2)}</b></span>`;
      const input = document.createElement("input");
      input.type = "range";
      input.min = String(min);
      input.max = String(max);
      input.step = "0.01";
      input.dataset.k = name;
      input.value = String(b[name]);
      input.addEventListener("pointerdown", () => focusTextBox(i));
      input.addEventListener("input", () => {
        b[name] = Number(input.value);
        const val = lab.querySelector(`[data-val="${name}"]`);
        if (val) val.textContent = Number(b[name]).toFixed(2);
        mirrorPrimary(state.settings);
        persistClipSettings();
        preview.setSettings(state.settings);
      });
      lab.appendChild(input);
      axes.appendChild(lab);
    }
    row.appendChild(axes);
    row.addEventListener("pointerdown", () => focusTextBox(i));
    host.appendChild(row);
  });
  const add = $("text-add");
  if (add) add.hidden = !boxes.some((b, i) => i >= 2 && !b.on);
}

$("text-add")?.addEventListener("click", () => {
  ensureTextBoxes(state.settings);
  const i = state.settings.text_boxes.findIndex((b, idx) => idx >= 2 && !b.on);
  if (i < 0) return;
  state.settings.text_boxes[i].on = true;
  state.textFocus = i;
  mirrorPrimary(state.settings);
  persistClipSettings();
  preview.setTextFocus(i);
  preview.setSettings(state.settings);
  paintTextBoxes();
});

const vizCanvas = $("viz");
let textDrag = null;
function canvasNorm(e) {
  const r = vizCanvas.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return { x: 0.5, y: 0.5 };
  return {
    x: (e.clientX - r.left) / r.width,
    y: (e.clientY - r.top) / r.height,
  };
}
vizCanvas.addEventListener("pointerdown", (e) => {
  const p = canvasNorm(e);
  const hit = preview.hitText(p.x, p.y);
  if (hit < 0) return;
  textDrag = hit;
  focusTextBox(hit);
  try { vizCanvas.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
  vizCanvas.style.cursor = "grabbing";
  e.preventDefault();
});
vizCanvas.addEventListener("pointermove", (e) => {
  const p = canvasNorm(e);
  if (textDrag == null) {
    vizCanvas.style.cursor = preview.hitText(p.x, p.y) >= 0 ? "grab" : "";
    return;
  }
  const b = state.settings.text_boxes[textDrag];
  if (!b) return;
  b.x = clamp(p.x, 0.02, 0.98);
  b.y = clamp(p.y, 0.02, 0.98);
  updateTextReadout(textDrag);
  mirrorPrimary(state.settings);
  persistClipSettings();
  preview.setSettings(state.settings);
});
function endTextDrag() {
  textDrag = null;
  vizCanvas.style.cursor = "";
}
vizCanvas.addEventListener("pointerup", endTextDrag);
vizCanvas.addEventListener("pointercancel", endTextDrag);

$("add-clip").addEventListener("click", () => {
  const t = audioEl.currentTime || 0;
  wave.defaultLen = Number($("clip-len").value);
  wave.addClipAt(t, wave.defaultLen);
});
$("del-clip").addEventListener("click", () => wave.removeSelected());
window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) return;
  if (e.code === "Space") {
    e.preventDefault();
    $("play").click();
  }
  if (e.key === "Backspace" || e.key === "Delete") wave.removeSelected();
});

$("suggest").addEventListener("click", async () => {
  if (!state.track) return;
  try {
    const body = {
      count: Number($("clip-count").value),
      length: Number($("clip-len").value),
    };
    const res = await api(`/api/tracks/${state.track.id}/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    wave.fromSuggestions(res.suggestions);
  } catch (err) {
    toast(err.message);
  }
});

$("render").addEventListener("click", async () => {
  if (!state.track || !wave.clips.length) return;
  $("render").disabled = true;
  $("cancel").hidden = false;
  $("outputs").innerHTML = "";
  try {
    const job = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        track_id: state.track.id,
        format: state.output.format,
        quality: state.output.quality,
        fps: state.output.fps,
        clips: wave.clips.map((c) => ({
          start: c.start,
          end: c.end,
          fade_in: c.fade_in || 0,
          fade_out: c.fade_out || 0,
          settings: stripOutput(cloneSettings(c.settings || state.settings)),
        })),
        settings: stripOutput(cloneSettings(state.settings)),
      }),
    });
    state.job = job;
    scheduleSave();
    pollJob(job.id);
  } catch (err) {
    $("render").disabled = false;
    $("cancel").hidden = true;
    toast(err.message);
  }
});

$("cancel").addEventListener("click", async () => {
  if (!state.job) return;
  try {
    await api(`/api/jobs/${state.job.id}/cancel`, { method: "POST" });
  } catch (err) {
    toast(err.message);
  }
});

function pollJob(id) {
  clearInterval(state.poll);
  const tickJob = async () => {
    try {
      const job = await api(`/api/jobs/${id}`);
      state.job = job;
      $("job-pill").textContent = job.status;
      $("job-pill").className = "pill " + (job.status === "done" ? "done" : "busy");
      $("job-msg").textContent = `${job.message}  ·  ${Math.round(job.progress * 100)}%`;
      if (job.outputs?.length) {
        $("outputs").innerHTML = job.outputs
          .map(
            (o) =>
              `<a href="/api/jobs/${id}/files/${encodeURIComponent(o.name)}" download="${o.name}">${o.name} · ${formatTime(o.start)}–${formatTime(o.end)} · ${(o.bytes / 1e6).toFixed(1)} MB</a>`
          )
          .join("");
      }
      if (job.status === "done" || job.status === "error" || job.status === "cancelled") {
        clearInterval(state.poll);
        $("render").disabled = false;
        $("cancel").hidden = true;
        loadRecent();
        if (job.status === "error") toast(job.error || "Render failed");
        if (job.status === "done") $("job-pill").className = "pill done";
        if (job.status !== "done") $("job-pill").className = "pill";
      }
    } catch (err) {
      clearInterval(state.poll);
      $("render").disabled = false;
      toast(err.message);
    }
  };
  tickJob();
  state.poll = setInterval(tickJob, 600);
}

function jobLabel(job) {
  const when = job.created ? new Date(job.created * 1000) : null;
  const stamp = when
    ? `${when.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ${when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
    : "";
  const src = job.track_name || job.track_id || "";
  return `${stamp} · ${src} · ${job.format || ""}/${job.quality || ""}`;
}

async function loadRecent() {
  const box = $("recent");
  if (!box) return;
  try {
    const res = await api("/api/jobs?limit=8");
    const jobs = (res.jobs || []).filter((j) => j.outputs?.length || j.status === "error");
    box.innerHTML = "";
    if (!jobs.length) {
      box.innerHTML = `<span class="faint">no renders yet</span>`;
      return;
    }
    for (const job of jobs) {
      const head = document.createElement("div");
      head.className = "recent-head";
      head.textContent = jobLabel(job) + (job.status === "error" ? " · failed" : "");
      box.appendChild(head);
      for (const o of job.outputs || []) {
        const a = document.createElement("a");
        a.href = `/api/jobs/${job.id}/files/${encodeURIComponent(o.name)}`;
        a.download = o.name;
        a.textContent = `${o.name} · ${formatTime(o.start)}–${formatTime(o.end)} · ${(o.bytes / 1e6).toFixed(1)} MB`;
        box.appendChild(a);
      }
    }
  } catch {
    /* offline or old server */
  }
}

async function restoreSession() {
  let ses;
  try {
    ses = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    ses = null;
  }
  if (!ses) return;
  if (ses.settings) Object.assign(state.settings, ses.settings);
  ensureTextBoxes(state.settings);
  mirrorPrimary(state.settings);
  // sessions saved before output moved to the job carry format inside settings
  for (const k of OUTPUT_KEYS) {
    if (ses.settings?.[k] !== undefined && !ses.output) state.output[k] = ses.settings[k];
  }
  if (ses.output) Object.assign(state.output, ses.output);
  stripOutput(state.settings);
  for (const c of ses.clips || []) {
    stripOutput(c.settings);
    if (c.settings) ensureTextBoxes(c.settings);
  }
  state.safeArea = Boolean(ses.safeArea);
  state.bgNames = ses.bgNames || {};
  state.bgKinds = ses.bgKinds || {};
  state.fontNames = ses.fontNames || {};
  state.logoNames = ses.logoNames || {};
  if (ses.track_id) {
    try {
      const meta = await api(`/api/tracks/${ses.track_id}`);
      await loadTrack(meta, { clips: ses.clips, selected: ses.selected });
    } catch {
      /* track expired on disk */
    }
  }
  if (ses.job_id) {
    try {
      const job = await api(`/api/jobs/${ses.job_id}`);
      if (job.status === "queued" || job.status === "running") {
        state.job = job;
        $("render").disabled = true;
        $("cancel").hidden = false;
        pollJob(job.id);
      }
    } catch {
      /* job gone */
    }
  }
}

async function boot() {
  state.catalog = await api("/api/presets");
  if (state.catalog.defaults) Object.assign(state.settings, state.catalog.defaults);
  installCatalogFonts(state.catalog.fonts);
  preview.setCatalog(state.catalog);
  await restoreSession();
  ensureTextBoxes(state.settings);
  mirrorPrimary(state.settings);
  const safe = $("safe-area");
  if (safe) {
    safe.checked = Boolean(state.safeArea);
    preview.setSafeArea(Boolean(state.safeArea));
  }
  syncControls();
  preview.setSettings(state.settings);
  preview.start();
  loadRecent();
}

$("look-save")?.addEventListener("click", () => {
  const label = ($("look-name")?.value || "").trim();
  if (!label) {
    toast("Name the look first");
    return;
  }
  const list = loadUserLooks();
  const existing = list.find((l) => l.label.toLowerCase() === label.toLowerCase());
  const entry = {
    id: existing?.id || `u-${Date.now().toString(16)}`,
    label,
    bundled: false,
    settings: lookOf(state.settings),
  };
  const next = existing ? list.map((l) => (l.id === existing.id ? entry : l)) : [...list, entry];
  storeUserLooks(next);
  $("look-name").value = "";
  paintLooks();
  toast(`Saved look “${label}”`);
});

$("safe-area")?.addEventListener("change", (e) => {
  state.safeArea = Boolean(e.target.checked);
  preview.setSafeArea(state.safeArea);
  scheduleSave();
});

boot().catch((err) => toast(err.message));
