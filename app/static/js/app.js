import { api, uploadWav } from "./api.js";
import { Preview } from "./preview.js";
import { Waveform, formatTime } from "./waveform.js";

const $ = (id) => document.getElementById(id);

const state = {
  catalog: null,
  track: null,
  settings: {
    scene: "mixed",
    bg_color: "#050303",
    effect_color: "#d63d24",
    text_color: "#ede6dc",
    format: "reels",
    quality: "standard",
    fps: 30,
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
    text_size: 0.65,
    text_opacity: 0.92,
    seed: 1,
  },
  job: null,
  poll: null,
};

const audioEl = new Audio();
audioEl.preload = "auto";
const preview = new Preview($("viz"));
const wave = new Waveform($("wave"), ({ clips, selected }) => {
  renderClipList(clips, selected);
  updatePlayRange();
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
  container.innerHTML = "";
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = item[labelKey] || item.id;
    b.title = item.blurb || "";
    b.className = item.id === current ? "on" : "";
    b.addEventListener("click", () => onPick(item.id));
    container.appendChild(b);
  }
}

function applyPalette(p) {
  state.settings.bg_color = p.bg_color;
  state.settings.effect_color = p.effect_color;
  state.settings.text_color = p.text_color;
  syncControls();
}

function bindColor(inputId, hexId, key) {
  const input = $(inputId);
  const hex = $(hexId);
  input.value = state.settings[key];
  hex.textContent = state.settings[key];
  input.oninput = () => {
    state.settings[key] = input.value;
    hex.textContent = input.value;
    preview.setSettings(state.settings);
    paintSwatches();
  };
}

function paintSwatches() {
  const box = $("swatches");
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
  const c = state.catalog;
  paintSwatches();
  bindColor("bg-color", "bg-hex", "bg_color");
  bindColor("effect-color", "effect-hex", "effect_color");
  bindColor("text-color", "text-hex", "text_color");
  seg($("scenes"), c.scenes, s.scene, (id) => {
    s.scene = id;
    syncControls();
  });
  seg($("formats"), c.formats, s.format, (id) => {
    s.format = id;
    $("stage").dataset.format = id;
    const f = c.formats.find((x) => x.id === id);
    $("format-tag").textContent = f?.ratio || id;
    preview.draw();
    syncControls();
  });
  seg($("qualities"), c.qualities, s.quality, (id) => {
    s.quality = id;
    syncControls();
  });
  seg(
    $("textpos"),
    [
      { id: "top", label: "Top" },
      { id: "center", label: "Center" },
      { id: "lower", label: "Lower" },
    ],
    s.text_position,
    (id) => {
      s.text_position = id;
      syncControls();
    }
  );

  const box = $("sliders");
  box.innerHTML = "";
  for (const sl of c.sliders) {
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
      preview.setSettings(s);
    });
    wrap.appendChild(input);
    box.appendChild(wrap);
  }
  $("text").value = s.text;
  $("subtext").value = s.subtext;
  $("text-size").value = String(s.text_size);
  preview.setSettings(s);
  $("stage").dataset.format = s.format;
}

function renderClipList(clips, selected) {
  const el = $("clip-list");
  el.innerHTML = "";
  clips.forEach((c, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "clip-chip" + (c.id === selected ? " on" : "");
    const len = (c.end - c.start).toFixed(1);
    b.innerHTML = `${i + 1} · ${formatTime(c.start)}–${formatTime(c.end)} <span class="why">${len}s ${c.reason || ""}</span>`;
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
  $("workspace").hidden = !on;
}

async function loadTrack(meta) {
  state.track = meta;
  $("track-label").textContent = `${meta.filename}  ·  ${formatTime(meta.duration)}  ·  ${meta.sample_rate} Hz  ·  ${meta.channels}ch`;
  wave.setTrack(meta);
  wave.fromSuggestions(meta.suggestions || []);
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
  if (f) handleFile(f);
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
  if (!audioEl.paused && $("loop").checked && t >= w.end - 0.03) {
    audioEl.currentTime = w.start;
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

$("text").addEventListener("input", (e) => {
  state.settings.text = e.target.value;
  preview.setSettings(state.settings);
});
$("subtext").addEventListener("input", (e) => {
  state.settings.subtext = e.target.value;
  preview.setSettings(state.settings);
});
$("text-size").addEventListener("input", (e) => {
  state.settings.text_size = Number(e.target.value);
  preview.setSettings(state.settings);
});

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
        clips: wave.clips.map((c) => ({ start: c.start, end: c.end })),
        settings: state.settings,
      }),
    });
    state.job = job;
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
              `<a href="/api/jobs/${id}/files/${o.name}" download>${o.name} · ${formatTime(o.start)}–${formatTime(o.end)} · ${(o.bytes / 1e6).toFixed(1)} MB</a>`
          )
          .join("");
      }
      if (job.status === "done" || job.status === "error" || job.status === "cancelled") {
        clearInterval(state.poll);
        $("render").disabled = false;
        $("cancel").hidden = true;
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

async function boot() {
  state.catalog = await api("/api/presets");
  if (state.catalog.defaults) Object.assign(state.settings, state.catalog.defaults);
  syncControls();
  preview.setSettings(state.settings);
  preview.start();
}

boot().catch((err) => toast(err.message));
