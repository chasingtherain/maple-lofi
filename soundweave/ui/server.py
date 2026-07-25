"""Local web UI for the mashup subcommand.

Stdlib-only HTTP server, bound to 127.0.0.1 only: serves a form to paste
YouTube URLs and upload a cover image, then shells out to
`python -m soundweave mashup` (the exact CLI subcommand you'd run by hand)
and streams its combined stdout/stderr back to the browser. The browser is
a thin front-end over the CLI, not a second pipeline implementation.
"""

import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from soundweave.mashup_config import DEFAULT_FADE_MS
from soundweave.ui.templates import INDEX_HTML, JOB_HTML

_LOG_TAIL_BYTES = 60_000
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


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

    def status(self) -> dict:
        returncode = self.process.poll()
        try:
            data = self.log_path.read_bytes()[-_LOG_TAIL_BYTES:]
        except FileNotFoundError:
            data = b""
        return {
            "running": returncode is None,
            "returncode": returncode,
            "log": data.decode("utf-8", errors="replace"),
            "output_dir": str(self.job_dir),
        }


class _MashupUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler_cls, output_base: Path):
        super().__init__(address, handler_cls)
        self.output_base = output_base
        self.jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def start_job(self, content_type: str, body: bytes) -> str:
        fields = _parse_multipart(content_type, body)
        urls_text = _field_text(fields, "urls").strip()
        if not urls_text:
            raise ValueError("No URLs provided")

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]
        job_dir = self.output_base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

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

        log_path = job_dir / "process.log"
        # Must stay open past this function's return — the child process
        # writes to it for the lifetime of the subprocess, closed below by
        # the watcher thread once it exits.
        logf = open(log_path, "wb")  # noqa: SIM115
        process = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)

        def _close_when_done() -> None:
            process.wait()
            logf.close()

        threading.Thread(target=_close_when_done, daemon=True).start()

        job = _Job(job_id, job_dir, process, log_path)
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
        if self.path != "/run":
            self._send(b"<h1>Not found</h1>", status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        try:
            job_id = self.server.start_job(content_type, body)
        except ValueError as e:
            self._send(f"<h1>Bad request</h1><p>{escape(str(e))}</p>".encode(), status=400)
            return
        self.send_response(303)
        self.send_header("Location", f"/job/{job_id}")
        self.end_headers()


def run_server(port: int, output_base: Path, open_browser: bool = True) -> None:
    """Start the mashup web UI and block until interrupted (Ctrl+C).

    Args:
        port: Port to listen on, bound to 127.0.0.1 only.
        output_base: Base directory under which each submitted run gets its
            own timestamped subdirectory (urls.txt, cover image, and all of
            `mashup`'s normal output land there).
        open_browser: Whether to auto-open a browser tab on startup.
    """
    output_base.mkdir(parents=True, exist_ok=True)
    server = _MashupUIServer(("127.0.0.1", port), _Handler, output_base)
    url = f"http://127.0.0.1:{port}/"
    print(f"Soundweave mashup UI running at {url}")
    print(f"Run output will be written under {output_base}/<job-id>/")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
