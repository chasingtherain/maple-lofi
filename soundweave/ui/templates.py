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
  button { margin-top: 24px; padding: 10px 20px; font-size: 15px; cursor: pointer; }
  .hint { color: #666; font-size: 13px; margin-top: 4px; }
</style>
</head>
<body>
<h1>Soundweave - Mashup</h1>
<p class="hint">Paste YouTube URLs (one per line) and optionally upload a cover image.
Runs locally via the existing <code>soundweave mashup</code> command - nothing leaves this machine.</p>
<form method="post" action="/run" enctype="multipart/form-data">
  <label for="urls">YouTube URLs</label>
  <textarea id="urls" name="urls" placeholder="https://youtube.com/watch?v=...&#10;https://youtube.com/watch?v=...&#10;# comments and blank lines are fine" required></textarea>

  <label for="image">Cover image (optional)</label>
  <input type="file" id="image" name="image" accept="image/png,image/jpeg">

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

  <button type="submit">Run mashup</button>
</form>
</body>
</html>
"""

JOB_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Soundweave - Mashup run</title>
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
<h1>Mashup run</h1>
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
