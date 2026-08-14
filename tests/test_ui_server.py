"""Tests for soundweave.ui.server.

Covers _list_output_files() as a pure unit (no server needed), plus real
HTTP-level integration tests against a live _MashupUIServer bound to an
ephemeral port (0) -- genuine requests over a real socket via urllib,
not mocked. Jobs are launched via a cheap real subprocess
(`sys.executable -c ...`) instead of a real ffmpeg/yt-dlp run, so these
stay fast and don't need either binary installed, while still exercising
the real subprocess -> _Job -> HTTP status pipeline end to end.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from soundweave.ui.server import _Handler, _list_output_files, _MashupUIServer


class TestListOutputFiles:
    def test_excludes_known_input_and_internal_files(self, tmp_path):
        (tmp_path / "urls.txt").write_text("x")
        (tmp_path / "process.log").write_text("x")
        (tmp_path / "manifest.json").write_text("{}")
        (tmp_path / "cover.png").write_bytes(b"x")
        (tmp_path / "input.wav").write_bytes(b"x")
        (tmp_path / "animated_background.mp4").write_bytes(b"x")
        (tmp_path / "mashup_log.txt").write_text("x")
        (tmp_path / "merged.mp3").write_bytes(b"real output")

        outputs = _list_output_files("job1", tmp_path)

        assert [o["name"] for o in outputs] == ["merged.mp3"]

    def test_excludes_description_file_it_has_its_own_dedicated_card(self, tmp_path):
        (tmp_path / "youtube_description.txt").write_text("0:00 Track 1\n")
        (tmp_path / "merged.mp3").write_bytes(b"x")

        outputs = _list_output_files("job1", tmp_path)

        assert [o["name"] for o in outputs] == ["merged.mp3"]

    def test_excludes_subdirectories(self, tmp_path):
        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "1.png").write_bytes(b"x")
        (tmp_path / "merged.mp3").write_bytes(b"x")

        outputs = _list_output_files("job1", tmp_path)

        assert [o["name"] for o in outputs] == ["merged.mp3"]

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert _list_output_files("job1", tmp_path / "does-not-exist") == []

    def test_path_is_a_url_not_a_filesystem_path(self, tmp_path):
        (tmp_path / "final_video.mp4").write_bytes(b"x")

        outputs = _list_output_files("job1", tmp_path)

        assert outputs[0]["path"] == "/download/job1/final_video.mp4"

    def test_size_mb_is_real_computed_size(self, tmp_path):
        (tmp_path / "merged.mp3").write_bytes(b"x" * (2 * 1024 * 1024))

        outputs = _list_output_files("job1", tmp_path)

        assert outputs[0]["size_mb"] == 2.0

    def test_filename_containing_traversal_sequence_is_just_a_normal_filename(self, tmp_path):
        # _list_output_files only ever iterates real directory entries --
        # there's no user-controlled path construction here, so a filename
        # can't "escape" tmp_path. The traversal-safety property lives in
        # _handle_download() re-deriving names from this list (see
        # TestDownloadSafety below), not here.
        (tmp_path / "merged.mp3").write_bytes(b"x")
        outputs = _list_output_files("job1", tmp_path)
        assert all(".." not in o["name"] for o in outputs)


@pytest.fixture
def live_server(tmp_path):
    """A real _MashupUIServer on an ephemeral port, torn down after the test."""
    server = _MashupUIServer(("127.0.0.1", 0), _Handler, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    yield server, base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _get(url: str) -> tuple[int, bytes, str | None]:
    """GET url, following no redirects, returning (status, body, location)."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        resp = opener.open(url)
        return resp.status, resp.read(), None
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Location")


class TestRoutes:
    def test_index_serves_mashup_and_loop_tabs(self, live_server):
        _, base_url = live_server
        status, body, _ = _get(f"{base_url}/")
        assert status == 200
        assert b'data-tab="mashup"' in body
        assert b'data-tab="loop"' in body

    def test_loop_redirects_to_index(self, live_server):
        _, base_url = live_server
        status, _, location = _get(f"{base_url}/loop")
        assert status == 302
        assert location == "/"

    def test_history_empty_says_no_runs_yet(self, live_server):
        _, base_url = live_server
        status, body, _ = _get(f"{base_url}/history")
        assert status == 200
        assert b"No runs yet" in body

    def test_unknown_path_is_404(self, live_server):
        _, base_url = live_server
        status, _, _ = _get(f"{base_url}/nonsense")
        assert status == 404

    def test_status_for_unknown_job_is_404(self, live_server):
        _, base_url = live_server
        status, _, _ = _get(f"{base_url}/api/status/does-not-exist")
        assert status == 404


class TestDownloadSafety:
    def test_traversal_attempt_is_404_not_the_real_file(self, live_server):
        server, base_url = live_server
        job_dir = server._new_job_dir()
        (job_dir / "merged.mp3").write_bytes(b"real output")
        job_id = job_dir.name

        status, _, _ = _get(f"{base_url}/download/{job_id}/..%2f..%2f..%2fetc%2fpasswd")

        assert status == 404

    def test_internal_file_is_not_downloadable(self, live_server):
        server, base_url = live_server
        job_dir = server._new_job_dir()
        (job_dir / "process.log").write_text("internal")
        (job_dir / "merged.mp3").write_bytes(b"real output")
        job_id = job_dir.name

        status, _, _ = _get(f"{base_url}/download/{job_id}/process.log")

        assert status == 404

    def test_real_output_file_downloads_correctly(self, live_server):
        server, base_url = live_server
        job_dir = server._new_job_dir()
        (job_dir / "merged.mp3").write_bytes(b"real output bytes")
        job_id = job_dir.name

        status, body, _ = _get(f"{base_url}/download/{job_id}/merged.mp3")

        assert status == 200
        assert body == b"real output bytes"

    def test_download_survives_no_in_memory_job_entry(self, live_server):
        # Simulates "history" from a previous server process: a job_dir on
        # disk with no corresponding entry in server.jobs at all.
        server, base_url = live_server
        job_dir = server._new_job_dir()
        (job_dir / "merged.mp3").write_bytes(b"from a previous run")
        job_id = job_dir.name
        assert job_id not in server.jobs

        status, body, _ = _get(f"{base_url}/download/{job_id}/merged.mp3")

        assert status == 200
        assert body == b"from a previous run"


class TestFullJobLifecycle:
    """Real subprocess -> _Job -> HTTP status, using a cheap Python
    one-liner instead of ffmpeg/yt-dlp so this stays fast and needs
    neither binary installed."""

    def test_successful_job_reports_done_with_real_outputs_and_description(self, live_server):
        server, base_url = live_server
        job_dir = server._new_job_dir()
        (job_dir / "urls.txt").write_text("http://example.com\n")
        (job_dir / "merged.mp3").write_bytes(b"fake but real bytes")
        (job_dir / "youtube_description.txt").write_text("0:00 Track 1\n0:30 Track 2\n")
        job_id = server._launch_job(job_dir, [sys.executable, "-c", "print('done')"])

        deadline = time.time() + 5
        data = None
        while time.time() < deadline:
            _status, body, _ = _get(f"{base_url}/api/status/{job_id}")
            data = json.loads(body)
            if not data["running"]:
                break
            time.sleep(0.05)

        assert data is not None
        assert data["running"] is False
        assert data["returncode"] == 0
        assert data["phase"] == "done"
        assert data["outputs"] == [
            {"name": "merged.mp3", "path": f"/download/{job_id}/merged.mp3", "size_mb": 0.0}
        ]
        assert data["description_text"] == "0:00 Track 1\n0:30 Track 2\n"
        assert data["output_dir"] == str(job_dir)

    def test_failed_job_reports_failed_and_removes_job_dir(self, live_server):
        server, base_url = live_server
        job_dir = server._new_job_dir()
        job_id = server._launch_job(job_dir, [sys.executable, "-c", "import sys; sys.exit(1)"])

        # The subprocess exiting (what "running" reflects, via poll()) and
        # the background cleanup thread actually removing job_dir are two
        # separate events -- poll here until cleanup has genuinely finished
        # (output_dir settles to None) rather than assuming they're
        # simultaneous, which would make this test racy.
        deadline = time.time() + 5
        data = None
        while time.time() < deadline:
            _status, body, _ = _get(f"{base_url}/api/status/{job_id}")
            data = json.loads(body)
            if not data["running"] and data["output_dir"] is None:
                break
            time.sleep(0.05)

        assert data is not None
        assert data["returncode"] == 1
        assert data["phase"] == "failed"
        assert data["outputs"] == []
        assert data["description_text"] is None
        assert data["output_dir"] is None
        assert not job_dir.exists()
