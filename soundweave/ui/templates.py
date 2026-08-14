"""HTML templates for the mashup-ui subcommand.

Design system (Radix Colors Slate/Indigo/Green/Amber/Red, hardcoded as CSS
custom properties -- no build step, no new dependency, per PRD_LAUNCH.md
Sec 5): dark-first, but `prefers-color-scheme: light` is honored, not
overridden. `_BASE_CSS` holds the shared tokens/components so all three
pages look like one system rather than three independently-styled pages.
"""

_BASE_CSS = """
:root {
  --bg: #111113;
  --card-bg: #18191b;
  --border: #43484e;
  --text: #edeef0;
  --text-dim: #9a9ea3;
  --accent: #3e63dd;
  --accent-text: #9eb1ff;
  --success: #30a46c;
  --success-text: #3dd68c;
  --warning: #ffc53d;
  --warning-text: #ffca16;
  --error: #e5484d;
  --error-text: #ff9592;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #fcfcfd;
    --card-bg: #f9f9fb;
    --border: #cdced6;
    --text: #1c2024;
    --text-dim: #60646c;
    --accent: #3e63dd;
    --accent-text: #3a5bc7;
    --success: #30a46c;
    --success-text: #218358;
    --warning: #ffc53d;
    --warning-text: #ab6400;
    --error: #e5484d;
    --error-text: #ce2c31;
  }
}
* { box-sizing: border-box; }
body {
  font-family: var(--font-ui);
  background: var(--bg);
  color: var(--text);
  max-width: 720px;
  margin: 40px auto;
  padding: 0 16px;
}
h1 { font-size: 20px; margin-bottom: 4px; }
.hint { color: var(--text-dim); font-size: 13px; line-height: 1.5; }
.nav { display: flex; gap: 16px; font-size: 14px; margin-bottom: 20px; }
.nav a { color: var(--text-dim); text-decoration: none; }
.nav a:hover { color: var(--accent-text); }
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  margin-top: 16px;
}
label { display: block; margin-top: 12px; font-weight: 600; font-size: 14px; }
label:first-child { margin-top: 0; }
textarea, input[type=text], input[type=number] {
  width: 100%; box-sizing: border-box; padding: 8px; font-size: 14px;
  margin-top: 4px; background: var(--bg); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px;
}
textarea { height: 140px; font-family: var(--font-mono); font-size: 13px; }
input[type=file] { margin-top: 6px; font-size: 13px; color: var(--text-dim); }
.row { display: flex; gap: 24px; align-items: flex-start; margin-top: 12px; }
.row > div { flex: 1; }
.mode-row { display: flex; gap: 20px; align-items: center; margin-top: 8px; font-weight: 400; }
.mode-row label { display: inline-flex; align-items: center; gap: 6px; margin-top: 0; font-weight: 400; }
.mode-panel { margin-top: 10px; }
.tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.tab {
  padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer;
  color: var(--text-dim); border-bottom: 2px solid transparent; background: none;
}
.tab.active { color: var(--accent-text); border-bottom-color: var(--accent); }
button.submit {
  margin-top: 20px; padding: 10px 20px; font-size: 15px; font-weight: 600;
  cursor: pointer; background: var(--accent); color: #fff; border: none;
  border-radius: 6px;
}
button.submit:hover { opacity: 0.9; }
.tracker { display: flex; gap: 0; margin: 20px 0; }
.step {
  flex: 1; text-align: center; padding: 10px 4px; font-size: 12px;
  font-weight: 600; color: var(--text-dim); border-bottom: 3px solid var(--border);
}
.step.done { color: var(--success-text); border-bottom-color: var(--success); }
.step.current { color: var(--warning-text); border-bottom-color: var(--warning); }
.step.failed { color: var(--error-text); border-bottom-color: var(--error); }
.status-line { font-weight: 600; font-size: 15px; margin: 4px 0 16px; display: flex; align-items: center; gap: 8px; }
.status-line.running { color: var(--warning-text); }
.status-line.ok { color: var(--success-text); }
.status-line.fail { color: var(--error-text); }
details { margin-top: 20px; }
summary { cursor: pointer; font-size: 13px; color: var(--text-dim); font-weight: 600; }
pre.log {
  background: #0a0a0b; color: #ddd; padding: 14px; border-radius: 6px;
  height: 360px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
  font-family: var(--font-mono); font-size: 12px; margin-top: 8px;
}
.output-card { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-top: 1px solid var(--border); }
.output-card:first-of-type { border-top: none; }
.output-name { font-family: var(--font-mono); font-size: 13px; }
.output-size { color: var(--text-dim); font-size: 12px; margin-left: 8px; }
.dl-btn, .copy-btn {
  font-size: 13px; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg); color: var(--text); text-decoration: none; cursor: pointer;
}
.dl-btn:hover, .copy-btn:hover { border-color: var(--accent); }
.desc-text {
  font-family: var(--font-mono); font-size: 12px; white-space: pre-wrap;
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 12px; max-height: 240px; overflow-y: auto; margin-top: 8px;
}
.history-item { display: flex; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--border); }
.history-item:first-of-type { border-top: none; }
.history-item a { color: var(--accent-text); }
"""

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
<h1>Soundweave</h1>
<p class="hint">Runs locally via the existing <code>soundweave</code> CLI as a subprocess -- nothing leaves this machine.</p>

<div class="tabs">
  <button type="button" class="tab active" data-tab="mashup">Mashup</button>
  <button type="button" class="tab" data-tab="loop">Loop</button>
</div>

<div id="panel-mashup">
<p class="hint">Paste YouTube URLs (one per line), crossfade them into one track, and optionally add video.</p>
<form method="post" action="/run" enctype="multipart/form-data">
  <div class="card">
    <label for="urls">YouTube URLs</label>
    <textarea id="urls" name="urls" placeholder="https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=...&#10;# comments and blank lines are fine" required></textarea>
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
<h1>Soundweave run</h1>

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
<h1>Run history</h1>
<div class="card" id="history-list">__HISTORY_ITEMS__</div>
</body>
</html>
"""
)
