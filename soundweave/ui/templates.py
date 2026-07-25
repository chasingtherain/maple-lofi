"""HTML templates for the mashup-ui subcommand."""

INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - Mashup</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; color: #222; }
  textarea { width: 100%; height: 160px; font-family: monospace; font-size: 13px; box-sizing: border-box; }
  label { display: block; margin-top: 16px; font-weight: 600; }
  input[type=file], input[type=number] { margin-top: 4px; }
  .row { display: flex; gap: 24px; align-items: center; margin-top: 12px; }
  .mode-row { display: flex; gap: 20px; align-items: center; margin-top: 8px; font-weight: 400; }
  .mode-row label { display: inline-flex; align-items: center; gap: 6px; margin-top: 0; font-weight: 400; }
  .mode-panel { margin-top: 8px; }
  button { margin-top: 24px; padding: 10px 20px; font-size: 15px; cursor: pointer; }
  .hint { color: #666; font-size: 13px; margin-top: 4px; }
  .nav { font-size: 14px; margin-bottom: 16px; }
  .nav span { color: #999; }
</style>
</head>
<body>
<div class="nav"><a href="/">Mashup</a> <span>|</span> <a href="/loop">Loop</a></div>
<h1>Soundweave - Mashup</h1>
<p class="hint">Paste YouTube URLs (one per line) and optionally add video.
Runs locally via the existing <code>soundweave mashup</code> command - nothing leaves this machine.</p>
<form method="post" action="/run" enctype="multipart/form-data">
  <label for="urls">YouTube URLs</label>
  <textarea id="urls" name="urls" placeholder="https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=...&#10;# comments and blank lines are fine" required></textarea>

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
    <p class="hint">One image per track (select all at once) - shown in filename order, one per track, for that track's actual duration. Needs at least as many images as tracks.</p>
  </div>
  <div class="mode-panel" id="panel-animated_background" style="display:none">
    <input type="file" id="animated_background" name="animated_background" accept="video/mp4">
    <p class="hint">A short, seamlessly-looping video (e.g. tools/ambient_bg/composite.sh's output) - looped to cover the full audio duration.</p>
  </div>

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
  silence gap between reps (e.g. for a long-running loop video from several songs). Chapters and
  track-cards repeat once per rep. Not supported together with "Per-track images" below.</p>

  <button type="submit">Run mashup</button>
</form>
<script>
const panels = { image: "panel-image", images: "panel-images", animated_background: "panel-animated_background" };
const loopCountInput = document.getElementById("loop_count");
for (const radio of document.querySelectorAll('input[name="video_mode"]')) {
  radio.addEventListener("change", () => {
    for (const [mode, panelId] of Object.entries(panels)) {
      document.getElementById(panelId).style.display = (mode === radio.value) ? "" : "none";
    }
    const imagesMode = radio.value === "images";
    loopCountInput.disabled = imagesMode;
    if (imagesMode) loopCountInput.value = "";
  });
}
</script>
</body>
</html>
"""

LOOP_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - Loop</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; color: #222; }
  label { display: block; margin-top: 16px; font-weight: 600; }
  input[type=file], input[type=number] { margin-top: 4px; }
  .row { display: flex; gap: 24px; align-items: center; margin-top: 12px; }
  .mode-row { display: flex; gap: 20px; align-items: center; margin-top: 8px; font-weight: 400; }
  .mode-row label { display: inline-flex; align-items: center; gap: 6px; margin-top: 0; font-weight: 400; }
  .mode-panel { margin-top: 8px; }
  input[type=text] { width: 100%; box-sizing: border-box; padding: 6px; font-size: 14px; }
  button { margin-top: 24px; padding: 10px 20px; font-size: 15px; cursor: pointer; }
  .hint { color: #666; font-size: 13px; margin-top: 4px; }
  .nav { font-size: 14px; margin-bottom: 16px; }
  .nav span { color: #999; }
</style>
</head>
<body>
<div class="nav"><a href="/">Mashup</a> <span>|</span> <a href="/loop">Loop</a></div>
<h1>Soundweave - Loop</h1>
<p class="hint">Repeat one track N times with a silence gap between reps
(e.g. for a 1-hour loop video). Runs locally via the existing <code>soundweave loop</code>
command - nothing leaves this machine.</p>
<form method="post" action="/run-loop" enctype="multipart/form-data">
  <label>Source</label>
  <div class="mode-row">
    <label><input type="radio" name="source_mode" value="upload" checked> Upload file</label>
    <label><input type="radio" name="source_mode" value="url"> YouTube URL</label>
  </div>

  <div class="mode-panel" id="panel-upload">
    <input type="file" id="audio" name="audio" accept=".mp3,.wav,.m4a,.flac" required>
  </div>
  <div class="mode-panel" id="panel-url" style="display:none">
    <input type="text" id="url" name="url" placeholder="https://youtube.com/watch?v=...">
    <p class="hint">Downloads the video's audio via yt-dlp, then loops it.</p>
  </div>

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

  <button type="submit">Run loop</button>
</form>
<script>
const audioInput = document.getElementById("audio");
const panels = { upload: "panel-upload", url: "panel-url" };
for (const radio of document.querySelectorAll('input[name="source_mode"]')) {
  radio.addEventListener("change", () => {
    for (const [mode, panelId] of Object.entries(panels)) {
      document.getElementById(panelId).style.display = (mode === radio.value) ? "" : "none";
    }
    audioInput.required = (radio.value === "upload");
  });
}
</script>
</body>
</html>
"""

JOB_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - Run</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 16px; }
  pre { background: #111; color: #ddd; padding: 16px; border-radius: 6px; height: 480px;
        overflow-y: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; }
  #status { font-weight: 600; margin-bottom: 8px; }
  .running { color: #b58900; }
  .ok { color: #2e7d32; }
  .fail { color: #c62828; }
</style>
</head>
<body>
<h1>Soundweave run</h1>
<div id="status" class="running">Running...</div>
<pre id="log"></pre>
<script>
const jobId = "__JOB_ID__";
const logEl = document.getElementById("log");
const statusEl = document.getElementById("status");
let done = false;

async function poll() {
  if (done) return;
  const res = await fetch(`/api/status/${jobId}`);
  const data = await res.json();
  logEl.textContent = data.log;
  logEl.scrollTop = logEl.scrollHeight;
  if (!data.running) {
    done = true;
    if (data.returncode === 0) {
      statusEl.textContent = `Done - output in ${data.output_dir}`;
      statusEl.className = "ok";
    } else {
      statusEl.textContent = `Failed (exit code ${data.returncode}) - see log above`;
      statusEl.className = "fail";
    }
    return;
  }
  setTimeout(poll, 1000);
}
poll();
</script>
</body>
</html>
"""
