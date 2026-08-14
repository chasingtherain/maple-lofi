"""HTML templates for the mashup-ui subcommand.

Design system (Radix Colors Slate/Indigo/Green/Amber/Red, hardcoded as CSS
custom properties -- no build step, no new dependency, per PRD_LAUNCH.md
Sec 5): dark-first, but `prefers-color-scheme: light` is honored, not
overridden. `_BASE_CSS` holds the shared tokens/components so all three
pages look like one system rather than three independently-styled pages.
"""

_BASE_CSS = """
:root {
  --bg: #101012;
  --card-bg: #17181b;
  --border: #2b2e33;
  --text: #f4f5f6;
  --text-dim: #9a9ea3;
  --accent: #5875f5;
  --accent-hover: #6c86f7;
  --accent-text: #a9bbff;
  --accent-soft: rgba(88, 117, 245, 0.14);
  --success: #30a46c;
  --success-text: #3dd68c;
  --warning: #ffc53d;
  --warning-text: #ffca16;
  --error: #e5484d;
  --error-text: #ff9592;
  --radius: 14px;
  --radius-sm: 8px;
  --shadow-card: 0 1px 2px rgba(0, 0, 0, .3), 0 10px 30px -14px rgba(0, 0, 0, .55);
  --shadow-btn: 0 2px 6px -1px rgba(0, 0, 0, .4), 0 6px 18px -6px rgba(88, 117, 245, .55);
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #fafafb;
    --card-bg: #ffffff;
    --border: #e3e4e8;
    --text: #1c2024;
    --text-dim: #66696f;
    --accent: #4a63e0;
    --accent-hover: #3d54cc;
    --accent-text: #3a51c9;
    --accent-soft: rgba(74, 99, 224, 0.08);
    --success: #30a46c;
    --success-text: #218358;
    --warning: #ffc53d;
    --warning-text: #ab6400;
    --error: #e5484d;
    --error-text: #ce2c31;
    --shadow-card: 0 1px 2px rgba(20, 20, 30, .04), 0 8px 24px -12px rgba(20, 20, 30, .12);
    --shadow-btn: 0 2px 6px -1px rgba(74, 99, 224, .25), 0 8px 20px -8px rgba(74, 99, 224, .35);
  }
}
* { box-sizing: border-box; }
html { color-scheme: dark light; }
body {
  font-family: var(--font-ui);
  background:
    radial-gradient(900px 420px at 20% -10%, var(--accent-soft), transparent 60%),
    var(--bg);
  color: var(--text);
  max-width: 760px;
  margin: 48px auto 80px;
  padding: 0 20px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.brand svg { flex-shrink: 0; color: var(--accent); }
h1 { font-size: 22px; font-weight: 700; letter-spacing: -.01em; margin: 0; }
.hint { color: var(--text-dim); font-size: 13px; line-height: 1.55; }
.nav { display: flex; gap: 6px; font-size: 13px; margin-bottom: 26px; }
.nav a {
  color: var(--text-dim); text-decoration: none; padding: 6px 10px; border-radius: 999px;
  transition: background .15s ease, color .15s ease;
}
.nav a:hover { color: var(--text); background: var(--card-bg); }
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 22px;
  margin-top: 16px;
  box-shadow: var(--shadow-card);
}
label { display: block; margin-top: 14px; font-weight: 600; font-size: 13px; letter-spacing: .01em; }
label:first-child { margin-top: 0; }
textarea, input[type=text], input[type=number] {
  width: 100%; box-sizing: border-box; padding: 10px 12px; font-size: 14px;
  margin-top: 6px; background: var(--bg); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  transition: border-color .15s ease, box-shadow .15s ease;
}
textarea:focus, input[type=text]:focus, input[type=number]:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft);
}
textarea { height: 140px; font-family: var(--font-mono); font-size: 13px; }
input::placeholder, textarea::placeholder { color: var(--text-dim); opacity: .8; }
input[type=checkbox], input[type=radio] { accent-color: var(--accent); width: 15px; height: 15px; }
input[type=file] { margin-top: 8px; font-size: 13px; color: var(--text-dim); }
input[type=file]::file-selector-button, input[type=file]::-webkit-file-upload-button {
  font-size: 13px; font-weight: 600; padding: 7px 14px; margin-right: 10px;
  border-radius: var(--radius-sm); border: 1px solid var(--border);
  background: var(--bg); color: var(--text); cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}
input[type=file]::file-selector-button:hover, input[type=file]::-webkit-file-upload-button:hover {
  border-color: var(--accent); color: var(--accent-text);
}
.row { display: flex; gap: 24px; align-items: flex-start; margin-top: 14px; }
.row > div { flex: 1; }
.mode-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.mode-row label {
  display: inline-flex; align-items: center; gap: 7px; margin-top: 0; font-weight: 500; font-size: 13px;
  padding: 8px 14px; border: 1px solid var(--border); border-radius: 999px; cursor: pointer;
  background: var(--bg); color: var(--text-dim);
  transition: border-color .15s ease, background .15s ease, color .15s ease;
}
.mode-row label:hover { border-color: var(--accent); color: var(--text); }
.mode-row label:has(input:checked) {
  background: var(--accent-soft); border-color: var(--accent); color: var(--accent-text); font-weight: 600;
}
.mode-row input[type=checkbox], .mode-row input[type=radio] { margin: 0; }
.mode-panel { margin-top: 14px; }
.tabs {
  display: inline-flex; gap: 2px; margin-bottom: 24px; padding: 4px;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 999px;
}
.tab {
  padding: 7px 18px; font-size: 13px; font-weight: 600; cursor: pointer;
  color: var(--text-dim); border: none; border-radius: 999px; background: none;
  transition: background .15s ease, color .15s ease;
}
.tab:hover { color: var(--text); }
.tab.active { color: #fff; background: var(--accent); }
button.submit {
  margin-top: 22px; padding: 11px 22px; font-size: 14px; font-weight: 600;
  cursor: pointer; background: var(--accent); color: #fff; border: none;
  border-radius: var(--radius-sm); box-shadow: var(--shadow-btn);
  transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
}
button.submit:hover { background: var(--accent-hover); transform: translateY(-1px); }
button.submit:active { transform: translateY(0); }
.tracker { display: flex; margin: 30px 0 26px; }
.step {
  flex: 1; text-align: center; font-size: 11px; font-weight: 700; color: var(--text-dim);
  position: relative; padding-top: 24px; text-transform: uppercase; letter-spacing: .04em;
}
.step::before {
  content: ""; position: absolute; top: 4px; left: 50%; width: 12px; height: 12px;
  border-radius: 999px; background: var(--card-bg); border: 2px solid var(--border);
  transform: translateX(-50%); z-index: 1; transition: all .2s ease;
}
.step::after {
  content: ""; position: absolute; top: 9px; left: -50%; width: 100%; height: 2px; background: var(--border);
}
.step:first-child::after { display: none; }
.step.done { color: var(--success-text); }
.step.done::before { background: var(--success); border-color: var(--success); }
.step.done::after { background: var(--success); }
.step.current { color: var(--warning-text); }
.step.current::before { background: var(--warning); border-color: var(--warning); box-shadow: 0 0 0 4px rgba(255, 197, 61, .18); }
.step.failed { color: var(--error-text); }
.step.failed::before { background: var(--error); border-color: var(--error); }
.status-line { font-weight: 600; font-size: 15px; margin: 4px 0 20px; display: flex; align-items: center; gap: 8px; }
.status-line::before { content: ""; width: 8px; height: 8px; border-radius: 999px; background: currentColor; flex-shrink: 0; }
.status-line.running { color: var(--warning-text); }
.status-line.ok { color: var(--success-text); }
.status-line.fail { color: var(--error-text); }
details { margin-top: 24px; }
summary { cursor: pointer; font-size: 13px; color: var(--text-dim); font-weight: 600; }
summary:hover { color: var(--text); }
pre.log {
  background: #0a0a0b; color: #ddd; padding: 16px; border-radius: var(--radius-sm);
  height: 360px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
  font-family: var(--font-mono); font-size: 12px; margin-top: 10px;
  border: 1px solid var(--border);
}
.output-card { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-top: 1px solid var(--border); }
.output-card:first-of-type { border-top: none; }
.output-name { font-family: var(--font-mono); font-size: 13px; }
.output-size { color: var(--text-dim); font-size: 12px; margin-left: 8px; }
.dl-btn, .copy-btn {
  font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border);
  background: var(--bg); color: var(--text); text-decoration: none; cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}
.dl-btn:hover, .copy-btn:hover { border-color: var(--accent); color: var(--accent-text); }
.desc-text {
  font-family: var(--font-mono); font-size: 12px; white-space: pre-wrap;
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 12px; max-height: 240px; overflow-y: auto; margin-top: 8px;
}
.history-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-top: 1px solid var(--border); }
.history-item:first-of-type { border-top: none; }
.history-item a { color: var(--accent-text); }
.url-row-wrap { margin-top: 10px; }
.url-row-wrap:first-child { margin-top: 0; }
.url-row-wrap.dragging { opacity: 0.4; }
.url-row { display: flex; align-items: center; gap: 8px; }
.drag-handle {
  cursor: grab; color: var(--text-dim); flex-shrink: 0; padding: 6px;
  display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm);
  transition: color .15s ease, background .15s ease;
}
.drag-handle:hover { color: var(--text); background: var(--bg); }
.drag-handle:active { cursor: grabbing; }
.url-row input[type=text] { margin-top: 0; flex: 1; }
.remove-row-btn {
  background: none; border: 1px solid var(--border); color: var(--text-dim);
  border-radius: 999px; width: 30px; height: 30px; cursor: pointer;
  flex-shrink: 0; display: flex; align-items: center; justify-content: center;
  transition: border-color .15s ease, color .15s ease, background .15s ease;
}
.remove-row-btn:hover { border-color: var(--error); color: var(--error-text); background: rgba(229, 72, 77, .08); }
.add-row-btn {
  margin-top: 12px; background: none; border: 1px dashed var(--border); color: var(--text-dim);
  border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; font-weight: 600; cursor: pointer; width: 100%;
  transition: border-color .15s ease, color .15s ease, background .15s ease;
}
.add-row-btn:hover { border-color: var(--accent); color: var(--accent-text); background: var(--accent-soft); }
.urls-error { color: var(--error-text); }
.url-preview {
  display: none; align-items: center; gap: 10px; margin: 8px 0 0 38px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg);
  animation: fadeIn .15s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: translateY(0); } }
.url-preview img { width: 64px; height: 36px; object-fit: cover; border-radius: 5px; flex-shrink: 0; }
.url-preview-title {
  font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.url-preview.error .url-preview-title { color: var(--text-dim); font-style: italic; }
"""

_BRAND_ICON = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="9" width="3" height="6" rx="1.5" fill="currentColor"/>
  <rect x="7.5" y="5" width="3" height="14" rx="1.5" fill="currentColor"/>
  <rect x="13" y="2" width="3" height="20" rx="1.5" fill="currentColor"/>
  <rect x="18.5" y="7" width="3" height="10" rx="1.5" fill="currentColor"/>
</svg>"""

INDEX_HTML = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave</title>
<style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
<div class="nav"><a href="/history">History</a></div>
<div class="brand">"""
    + _BRAND_ICON
    + """<h1>Soundweave</h1></div>
<p class="hint">Runs locally via the existing <code>soundweave</code> CLI as a subprocess -- nothing leaves this machine.</p>

<div class="tabs">
  <button type="button" class="tab active" data-tab="mashup">Mashup</button>
  <button type="button" class="tab" data-tab="loop">Loop</button>
</div>

<div id="panel-mashup">
<p class="hint">Add YouTube links, crossfade them into one track, and optionally add video.</p>
<form method="post" action="/run" enctype="multipart/form-data">
  <div class="card">
    <label>YouTube URLs</label>
    <p class="hint">Add one link per song. Drag the handle to reorder -- that's the order they'll be crossfaded in.</p>
    <div id="url-rows"></div>
    <button type="button" class="add-row-btn" id="add-url-row">+ Add another link</button>
    <p class="hint urls-error" id="urls-error" style="display:none">Add at least one YouTube link before running.</p>
    <textarea name="urls" id="urls-hidden" style="display:none"></textarea>
  </div>

  <div class="card">
    <label>Video (optional)</label>
    <div class="mode-row">
      <label><input type="radio" name="video_mode" value="image" checked> Single cover image</label>
      <label><input type="radio" name="video_mode" value="images"> Per-track images</label>
      <label><input type="radio" name="video_mode" value="animated_background"> Animated background</label>
    </div>
    <div class="mode-panel" id="panel-image">
      <input type="file" id="image" name="image" accept="image/png,image/jpeg,image/webp">
      <p class="hint">One image, shown for the whole video.</p>
    </div>
    <div class="mode-panel" id="panel-images" style="display:none">
      <input type="file" id="images" name="images" accept="image/png,image/jpeg,image/webp" multiple>
      <p class="hint">One image per track (select all at once) -- shown in filename order, one per track, for that track's actual duration. Needs at least as many images as tracks.</p>
    </div>
    <div class="mode-panel" id="panel-animated_background" style="display:none">
      <input type="file" id="animated_background" name="animated_background" accept="video/mp4">
      <p class="hint">A short, seamlessly-looping video -- looped to cover the full audio duration.</p>
    </div>
  </div>

  <div class="card">
    <div class="row">
      <div>
        <label for="fade_ms">Crossfade (ms)</label>
        <input type="number" id="fade_ms" name="fade_ms" value="4500" min="0" step="100">
      </div>
      <div>
        <label><input type="checkbox" name="shuffle"> Shuffle order</label>
        <label><input type="checkbox" name="strict"> Abort on failed URL</label>
      </div>
    </div>
    <label for="loop_count">Repeat count (optional)</label>
    <input type="number" id="loop_count" name="loop_count" min="1" step="1" placeholder="leave blank for no repeat">
    <p class="hint" id="loop_count_hint">Repeat the whole crossfaded set this many times end-to-end, with a
    silence gap between reps. Not supported together with "Per-track images" above.</p>
  </div>

  <button type="submit" class="submit">Run mashup</button>
</form>
</div>

<div id="panel-loop" style="display:none">
<p class="hint">Repeat one track N times with a silence gap between reps (e.g. for a 1-hour loop video).</p>
<form method="post" action="/run-loop" enctype="multipart/form-data">
  <div class="card">
    <label>Source</label>
    <div class="mode-row">
      <label><input type="radio" name="source_mode" value="upload" checked> Upload file</label>
      <label><input type="radio" name="source_mode" value="url"> YouTube URL</label>
    </div>
    <div class="mode-panel" id="loop-panel-upload">
      <input type="file" id="audio" name="audio" accept=".mp3,.wav,.m4a,.flac">
    </div>
    <div class="mode-panel" id="loop-panel-url" style="display:none">
      <input type="text" id="url" name="url" placeholder="https://youtube.com/watch?v=...">
      <p class="hint">Downloads the video's audio via yt-dlp, then loops it.</p>
    </div>
  </div>

  <div class="card">
    <div class="row">
      <div>
        <label for="count">Repeat count</label>
        <input type="number" id="count" name="count" value="5" min="1" step="1" required>
      </div>
      <div>
        <label for="gap_ms">Gap between reps (ms)</label>
        <input type="number" id="gap_ms" name="gap_ms" value="3500" min="0" step="100">
      </div>
      <div>
        <label for="trim_db">Trim threshold (dB)</label>
        <input type="number" id="trim_db" name="trim_db" value="-40" step="1">
      </div>
    </div>
  </div>

  <button type="submit" class="submit">Run loop</button>
</form>
</div>

<script>
// Top-level Mashup/Loop tabs
const tabs = document.querySelectorAll(".tab");
const panels = { mashup: "panel-mashup", loop: "panel-loop" };
for (const tab of tabs) {
  tab.addEventListener("click", () => {
    for (const t of tabs) t.classList.remove("active");
    tab.classList.add("active");
    for (const [name, id] of Object.entries(panels)) {
      document.getElementById(id).style.display = (name === tab.dataset.tab) ? "" : "none";
    }
  });
}

// Mashup video-mode sub-toggle (unchanged behavior from the original form)
const videoPanels = { image: "panel-image", images: "panel-images", animated_background: "panel-animated_background" };
const loopCountInput = document.getElementById("loop_count");
for (const radio of document.querySelectorAll('input[name="video_mode"]')) {
  radio.addEventListener("change", () => {
    for (const [mode, panelId] of Object.entries(videoPanels)) {
      document.getElementById(panelId).style.display = (mode === radio.value) ? "" : "none";
    }
    const imagesMode = radio.value === "images";
    loopCountInput.disabled = imagesMode;
    if (imagesMode) loopCountInput.value = "";
  });
}

// YouTube URL rows: add/remove/drag-reorder, paste-splitting, sync into
// the hidden "urls" textarea (newline-separated, same format the server
// has always expected) right before the form submits.
const urlRows = document.getElementById("url-rows");
const addUrlRowBtn = document.getElementById("add-url-row");
const urlsHidden = document.getElementById("urls-hidden");
const urlsError = document.getElementById("urls-error");

// Per-row title/thumbnail preview via YouTube's public oEmbed endpoint
// (no API key, CORS-enabled) -- this is the one request in the app that
// leaves 127.0.0.1, purely to fetch a video's title/thumbnail for display.
function looksLikeYouTubeUrl(value) {
  return /youtube\\.com\\/|youtu\\.be\\//i.test(value);
}

function renderPreview(previewEl, state, data) {
  previewEl.classList.toggle("error", state === "error");
  previewEl.innerHTML = "";
  if (state === "hidden") {
    previewEl.style.display = "none";
    return;
  }
  previewEl.style.display = "flex";
  if (state === "ok") {
    const img = document.createElement("img");
    img.src = data.thumbnail_url;
    img.alt = "";
    const title = document.createElement("span");
    title.className = "url-preview-title";
    title.textContent = data.title;
    previewEl.append(img, title);
  } else {
    const title = document.createElement("span");
    title.className = "url-preview-title";
    title.textContent = state === "loading" ? "Loading preview..." : "Couldn't load a preview for this link";
    previewEl.appendChild(title);
  }
}

function fetchPreview(input, previewEl) {
  const url = input.value.trim();
  if (input._previewAbort) input._previewAbort.abort();
  if (!url || !looksLikeYouTubeUrl(url)) {
    renderPreview(previewEl, "hidden");
    return;
  }
  const controller = new AbortController();
  input._previewAbort = controller;
  renderPreview(previewEl, "loading");
  const oembedUrl = "https://www.youtube.com/oembed?url=" + encodeURIComponent(url) + "&format=json";
  fetch(oembedUrl, { signal: controller.signal })
    .then((res) => {
      if (!res.ok) throw new Error("oEmbed request failed");
      return res.json();
    })
    .then((data) => renderPreview(previewEl, "ok", data))
    .catch((err) => {
      if (err.name === "AbortError") return;
      renderPreview(previewEl, "error");
    });
}

function makeUrlRow(value) {
  const wrap = document.createElement("div");
  wrap.className = "url-row-wrap";
  wrap.innerHTML = `<div class="url-row">
      <span class="drag-handle" title="Drag to reorder">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
          <circle cx="4" cy="3" r="1.3"/><circle cx="10" cy="3" r="1.3"/>
          <circle cx="4" cy="7" r="1.3"/><circle cx="10" cy="7" r="1.3"/>
          <circle cx="4" cy="11" r="1.3"/><circle cx="10" cy="11" r="1.3"/>
        </svg>
      </span>
      <input type="text" class="url-input" placeholder="https://youtube.com/watch?v=...">
      <button type="button" class="remove-row-btn" title="Remove">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
          <path d="M2 2l8 8M10 2l-8 8"/>
        </svg>
      </button>
    </div>
    <div class="url-preview"></div>`;
  const input = wrap.querySelector(".url-input");
  const previewEl = wrap.querySelector(".url-preview");
  input.value = value || "";
  const handle = wrap.querySelector(".drag-handle");
  handle.draggable = true;

  let debounceTimer;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => fetchPreview(input, previewEl), 700);
  });
  input.addEventListener("paste", (e) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\\n")) return;
    e.preventDefault();
    const lines = text.split("\\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return;
    input.value = lines[0];
    fetchPreview(input, previewEl);
    let after = wrap;
    for (const line of lines.slice(1)) {
      const newRow = makeUrlRow(line);
      after.after(newRow);
      after = newRow;
    }
  });

  wrap.querySelector(".remove-row-btn").addEventListener("click", () => {
    if (input._previewAbort) input._previewAbort.abort();
    wrap.remove();
    if (!urlRows.querySelector(".url-row-wrap")) urlRows.appendChild(makeUrlRow(""));
  });

  handle.addEventListener("dragstart", (e) => {
    wrap.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setDragImage(wrap, 10, 10);
  });
  handle.addEventListener("dragend", () => wrap.classList.remove("dragging"));

  return wrap;
}

urlRows.addEventListener("dragover", (e) => {
  e.preventDefault();
  const dragging = urlRows.querySelector(".dragging");
  if (!dragging) return;
  const after = [...urlRows.querySelectorAll(".url-row-wrap:not(.dragging)")].find((el) => {
    const rect = el.getBoundingClientRect();
    return e.clientY < rect.top + rect.height / 2;
  });
  if (after) urlRows.insertBefore(dragging, after);
  else urlRows.appendChild(dragging);
});

addUrlRowBtn.addEventListener("click", () => urlRows.appendChild(makeUrlRow("")));

urlRows.appendChild(makeUrlRow(""));

document.querySelector('form[action="/run"]').addEventListener("submit", (e) => {
  const values = [...urlRows.querySelectorAll(".url-input")]
    .map((el) => el.value.trim())
    .filter(Boolean);
  if (!values.length) {
    e.preventDefault();
    urlsError.style.display = "";
    return;
  }
  urlsError.style.display = "none";
  urlsHidden.value = values.join("\\n");
});

// Loop source sub-toggle
const audioInput = document.getElementById("audio");
const loopSourcePanels = { upload: "loop-panel-upload", url: "loop-panel-url" };
for (const radio of document.querySelectorAll('input[name="source_mode"]')) {
  radio.addEventListener("change", () => {
    for (const [mode, panelId] of Object.entries(loopSourcePanels)) {
      document.getElementById(panelId).style.display = (mode === radio.value) ? "" : "none";
    }
  });
}
</script>
</body>
</html>
"""
)

JOB_HTML = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - Run</title>
<style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
<div class="nav"><a href="/">New run</a> <a href="/history">History</a></div>
<div class="brand">"""
    + _BRAND_ICON
    + """<h1>Soundweave run</h1></div>

<div class="tracker" id="tracker">
  <div class="step" data-phase="preparing">Preparing</div>
  <div class="step" data-phase="encoding">Encoding</div>
  <div class="step" data-phase="video">Video</div>
  <div class="step" data-phase="done">Done</div>
</div>

<div id="status" class="status-line running">Starting...</div>

<div id="results"></div>

<details>
  <summary>View full log</summary>
  <pre class="log" id="log"></pre>
</details>

<script>
const jobId = "__JOB_ID__";
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const resultsEl = document.getElementById("results");
const trackerSteps = document.querySelectorAll("#tracker .step");
const PHASE_ORDER = ["preparing", "encoding", "video", "done"];
let done = false;

function renderTracker(phase) {
  if (phase === "failed") {
    for (const el of trackerSteps) el.classList.remove("done", "current");
    return;
  }
  const idx = PHASE_ORDER.indexOf(phase);
  trackerSteps.forEach((el, i) => {
    el.classList.remove("done", "current", "failed");
    if (i < idx) el.classList.add("done");
    else if (i === idx) el.classList.add("current");
  });
}

function renderResults(data) {
  let html = "";
  if (data.description_text) {
    html += `<div class="card">
      <div class="row" style="align-items:center; justify-content:space-between">
        <label style="margin:0">YouTube description</label>
        <button class="copy-btn" id="copy-desc">Copy</button>
      </div>
      <div class="desc-text" id="desc-text">${escapeHtml(data.description_text)}</div>
    </div>`;
  }
  if (data.outputs && data.outputs.length) {
    html += `<div class="card"><label style="margin:0 0 4px">Output files</label>`;
    for (const o of data.outputs) {
      html += `<div class="output-card">
        <span class="output-name">${escapeHtml(o.name)}<span class="output-size">(${o.size_mb} MB)</span></span>
        <a class="dl-btn" href="${o.path}" download>Download</a>
      </div>`;
    }
    html += `</div>`;
  }
  resultsEl.innerHTML = html;
  const copyBtn = document.getElementById("copy-desc");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(data.description_text);
      copyBtn.textContent = "Copied";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
    });
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function poll() {
  if (done) return;
  const res = await fetch(`/api/status/${jobId}`);
  const data = await res.json();
  logEl.textContent = data.log;
  logEl.scrollTop = logEl.scrollHeight;
  renderTracker(data.phase);

  if (data.phase === "failed") {
    statusEl.textContent = `Failed (exit code ${data.returncode}) - see log below`;
    statusEl.className = "status-line fail";
  } else if (data.phase === "done") {
    statusEl.textContent = "Done";
    statusEl.className = "status-line ok";
  } else {
    const label = data.phase.charAt(0).toUpperCase() + data.phase.slice(1);
    statusEl.textContent = `${label}...`;
    statusEl.className = "status-line running";
  }

  if (!data.running) {
    done = true;
    renderResults(data);
    return;
  }
  setTimeout(poll, 1000);
}
poll();
</script>
</body>
</html>
"""
)

HISTORY_HTML = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - History</title>
<style>"""
    + _BASE_CSS
    + """</style>
</head>
<body>
<div class="nav"><a href="/">New run</a></div>
<div class="brand">"""
    + _BRAND_ICON
    + """<h1>Run history</h1></div>
<div class="card" id="history-list">__HISTORY_ITEMS__</div>
</body>
</html>
"""
)
