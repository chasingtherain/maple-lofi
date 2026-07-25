"""Local web UI for the mashup and loop subcommands.

Stdlib-only HTTP server, bound to 127.0.0.1 only. Two forms:

- `/` (mashup): paste YouTube URLs and choose a video source (a single cover
  image, one image per track, or a looping animated background -- the same
  three mutually-exclusive modes as the CLI's
  `--image`/`--images`/`--animated-background`), then shells out to
  `python -m soundweave mashup`.
- `/loop`: upload one audio file and a repeat count, then shells out to
  `python -m soundweave loop`.

Either form runs the exact CLI subcommand you'd type by hand as a subprocess
and streams its combined stdout/stderr back to the browser. The browser is a
thin front-end over the CLI, not a second pipeline implementation.
"""

import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from soundweave.loop_config import AUDIO_EXTENSIONS as _AUDIO_EXTENSIONS
from soundweave.loop_config import DEFAULT_GAP_MS, DEFAULT_TRIM_DB
from soundweave.mashup_config import DEFAULT_FADE_MS
from soundweave.ui.templates import INDEX_HTML, JOB_HTML, LOOP_HTML

_LOG_TAIL_BYTES = 60_000
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_JOB_ID_TZ = timezone(timedelta(hours=8))  # GMT+8, for human-readable job-id timestamps


def _parse_multipart(content_type: str, body: bytes) -> dict[str, list[Message]]:
    """Parse a multipart/form-data body into {field_name: [Message, ...]}.

    Reuses the stdlib `email` package to do the actual parsing (there is no
    `cgi.FieldStorage` anymore as of Python 3.13) by prepending a synthetic
    MIME header so the body parses as a standard multipart message.
    """
    header = f"Content-Type: {content_type}\r\n\r\n".encode("ascii", "replace")
    msg = BytesParser(policy=policy.compat32).parsebytes(header + body)
    fields: dict[str, list[Message]] = {}
    if not msg.is_multipart():
        return fields
    for part in msg.get_payload():
        name = part.get_param("name", header="content-disposition")
        if name is None:
            continue
        fields.setdefault(name, []).append(part)
    return fields


def _field_text(fields: dict[str, list[Message]], name: str, default: str = "") -> str:
    parts = fields.get(name)
    if not parts:
        return default
    payload = parts[0].get_payload(decode=True) or b""
    return payload.decode("utf-8", errors="replace")


class _Job:
    def __init__(self, job_id: str, job_dir: Path, process: subprocess.Popen, log_path: Path):
        self.job_id = job_id
        self.job_dir = job_dir
        self.process = process
        self.log_path = log_path
        # Set once a failed run's directory has been removed (see
        # _close_when_done below) -- holds the log's final bytes so the
        # browser's last poll can still show them after the file is gone.
        self.final_log: bytes | None = None
        self.removed = False

    def status(self) -> dict:
        returncode = self.process.poll()
        if self.final_log is not None:
            data = self.final_log
        else:
            try:
                data = self.log_path.read_bytes()[-_LOG_TAIL_BYTES:]
            except FileNotFoundError:
                data = b""
        return {
            "running": returncode is None,
            "returncode": returncode,
            "log": data.decode("utf-8", errors="replace"),
            "output_dir": None if self.removed else str(self.job_dir),
        }


class _MashupUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler_cls, output_base: Path):
        super().__init__(address, handler_cls)
        self.output_base = output_base
        self.jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def _new_job_dir(self) -> Path:
        job_id = datetime.now(_JOB_ID_TZ).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]
        job_dir = self.output_base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def start_job(self, content_type: str, body: bytes) -> str:
        fields = _parse_multipart(content_type, body)
        urls_text = _field_text(fields, "urls").strip()
        if not urls_text:
            raise ValueError("No URLs provided")

        job_dir = self._new_job_dir()
        urls_path = job_dir / "urls.txt"
        urls_path.write_text(urls_text + "\n", encoding="utf-8")

        cmd = [
            sys.executable,
            "-m",
            "soundweave",
            "mashup",
            "--urls",
            str(urls_path),
            "--output",
            str(job_dir),
        ]

        fade_ms_text = _field_text(fields, "fade_ms", str(DEFAULT_FADE_MS)).strip()
        try:
            fade_ms = int(fade_ms_text) if fade_ms_text else DEFAULT_FADE_MS
        except ValueError:
            fade_ms = DEFAULT_FADE_MS
        cmd += ["--fade-ms", str(fade_ms)]

        if _field_text(fields, "shuffle") == "on":
            cmd.append("--shuffle")
        if _field_text(fields, "strict") == "on":
            cmd.append("--strict")

        # Exactly one of --image/--images/--animated-background, matching
        # cli.py's mutually-exclusive argparse group. `video_mode` (a radio
        # button, not "any field with bytes in it") is the source of truth
        # for which one -- a browser could in principle submit more than one
        # file field, and only the selected mode's field should be honored.
        video_mode = _field_text(fields, "video_mode", "image")

        if video_mode == "image":
            image_parts = fields.get("image")
            if image_parts:
                part = image_parts[0]
                filename = part.get_filename()
                image_bytes = part.get_payload(decode=True) or b""
                if filename and image_bytes:
                    ext = Path(filename).suffix.lower()
                    if ext not in _IMAGE_EXTENSIONS:
                        ext = ".png"
                    cover_path = job_dir / f"cover{ext}"
                    cover_path.write_bytes(image_bytes)
                    cmd += ["--image", str(cover_path)]

        elif video_mode == "images":
            image_parts = fields.get("images") or []
            written_any = False
            images_dir = job_dir / "images"
            for part in image_parts:
                filename = part.get_filename()
                image_bytes = part.get_payload(decode=True) or b""
                if not filename or not image_bytes:
                    continue
                # Path(...).name strips any directory components a
                # maliciously-crafted filename might carry -- this server is
                # 127.0.0.1-only, but writing under job_dir with an
                # untrusted filename is cheap to get right regardless.
                safe_name = Path(filename).name
                if not safe_name:
                    continue
                images_dir.mkdir(parents=True, exist_ok=True)
                (images_dir / safe_name).write_bytes(image_bytes)
                written_any = True
            if written_any:
                # cli.py's _run_mashup_subcommand natural-sorts the
                # directory listing itself when it processes --images, so
                # order here doesn't need to be re-derived -- just get each
                # file onto disk with its original name.
                cmd += ["--images", str(images_dir)]

        elif video_mode == "animated_background":
            bg_parts = fields.get("animated_background")
            if bg_parts:
                part = bg_parts[0]
                filename = part.get_filename()
                video_bytes = part.get_payload(decode=True) or b""
                if filename and video_bytes:
                    ext = Path(filename).suffix.lower() or ".mp4"
                    bg_path = job_dir / f"animated_background{ext}"
                    bg_path.write_bytes(video_bytes)
                    cmd += ["--animated-background", str(bg_path)]

        return self._launch_job(job_dir, cmd)

    def start_loop_job(self, content_type: str, body: bytes) -> str:
        fields = _parse_multipart(content_type, body)
        audio_parts = fields.get("audio")
        if not audio_parts:
            raise ValueError("No audio file provided")
        part = audio_parts[0]
        filename = part.get_filename()
        audio_bytes = part.get_payload(decode=True) or b""
        if not filename or not audio_bytes:
            raise ValueError("No audio file provided")

        count_text = _field_text(fields, "count").strip()
        try:
            count = int(count_text)
        except ValueError:
            raise ValueError("Repeat count must be a whole number") from None
        if count < 1:
            raise ValueError("Repeat count must be at least 1")

        ext = Path(filename).suffix.lower()
        if ext not in _AUDIO_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio file type '{ext or filename}' "
                f"(expected one of: {', '.join(sorted(_AUDIO_EXTENSIONS))})"
            )

        job_dir = self._new_job_dir()
        audio_path = job_dir / f"input{ext}"
        audio_path.write_bytes(audio_bytes)

        cmd = [
            sys.executable,
            "-m",
            "soundweave",
            "loop",
            str(audio_path),
            "--count",
            str(count),
            "--output",
            str(job_dir),
        ]

        gap_ms_text = _field_text(fields, "gap_ms", str(DEFAULT_GAP_MS)).strip()
        try:
            gap_ms = int(gap_ms_text) if gap_ms_text else DEFAULT_GAP_MS
        except ValueError:
            gap_ms = DEFAULT_GAP_MS
        cmd += ["--gap-ms", str(gap_ms)]

        trim_db_text = _field_text(fields, "trim_db", str(DEFAULT_TRIM_DB)).strip()
        try:
            trim_db = float(trim_db_text) if trim_db_text else DEFAULT_TRIM_DB
        except ValueError:
            trim_db = DEFAULT_TRIM_DB
        cmd += ["--trim-db", str(trim_db)]

        return self._launch_job(job_dir, cmd)

    def _launch_job(self, job_dir: Path, cmd: list[str]) -> str:
        job_id = job_dir.name
        log_path = job_dir / "process.log"
        # Must stay open past this function's return — the child process
        # writes to it for the lifetime of the subprocess, closed below by
        # the watcher thread once it exits.
        logf = open(log_path, "wb")  # noqa: SIM115
        process = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        job = _Job(job_id, job_dir, process, log_path)

        def _close_when_done() -> None:
            process.wait()
            logf.close()
            if process.returncode != 0:
                # A failed run has no real output worth keeping -- capture
                # the log's tail in memory for the browser's last poll,
                # then remove the job dir instead of leaving a stray folder
                # (uploaded input, partial logs) behind.
                try:
                    job.final_log = log_path.read_bytes()[-_LOG_TAIL_BYTES:]
                except FileNotFoundError:
                    job.final_log = b""
                shutil.rmtree(job_dir, ignore_errors=True)
                job.removed = True

        threading.Thread(target=_close_when_done, daemon=True).start()

        with self._lock:
            self.jobs[job_id] = job
        return job_id


class _Handler(BaseHTTPRequestHandler):
    server: _MashupUIServer

    def log_message(self, format: str, *args) -> None:
        pass

    def _send(
        self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(INDEX_HTML.encode("utf-8"))
        elif parsed.path == "/loop":
            self._send(LOOP_HTML.encode("utf-8"))
        elif parsed.path.startswith("/job/"):
            job_id = parsed.path[len("/job/") :]
            if job_id not in self.server.jobs:
                self._send(b"<h1>Unknown job</h1>", status=404)
                return
            page = JOB_HTML.replace("__JOB_ID__", escape(job_id))
            self._send(page.encode("utf-8"))
        elif parsed.path.startswith("/api/status/"):
            job_id = parsed.path[len("/api/status/") :]
            job = self.server.jobs.get(job_id)
            if job is None:
                self._send(
                    json.dumps({"error": "unknown job"}).encode("utf-8"),
                    status=404,
                    content_type="application/json",
                )
                return
            self._send(json.dumps(job.status()).encode("utf-8"), content_type="application/json")
        else:
            self._send(b"<h1>Not found</h1>", status=404)

    def do_POST(self) -> None:
        if self.path == "/run":
            starter = self.server.start_job
        elif self.path == "/run-loop":
            starter = self.server.start_loop_job
        else:
            self._send(b"<h1>Not found</h1>", status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        try:
            job_id = starter(content_type, body)
        except ValueError as e:
            self._send(f"<h1>Bad request</h1><p>{escape(str(e))}</p>".encode(), status=400)
            return
        self.send_response(303)
        self.send_header("Location", f"/job/{job_id}")
        self.end_headers()


def run_server(port: int, output_base: Path, open_browser: bool = True) -> None:
    """Start the mashup/loop web UI and block until interrupted (Ctrl+C).

    Args:
        port: Port to listen on, bound to 127.0.0.1 only.
        output_base: Base directory under which each submitted run gets its
            own timestamped subdirectory (urls.txt/uploaded audio, cover
            image, and all of `mashup`'s or `loop`'s normal output land
            there).
        open_browser: Whether to auto-open a browser tab on startup.
    """
    output_base.mkdir(parents=True, exist_ok=True)
    server = _MashupUIServer(("127.0.0.1", port), _Handler, output_base)
    url = f"http://127.0.0.1:{port}/"
    print(f"Soundweave mashup/loop UI running at {url}")
    print(f"Run output will be written under {output_base}/<job-id>/")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
