"""Tests for soundweave/ffmpeg/executor.py — run_ffmpeg's two execution
paths: the original subprocess.run() fast path (total_duration_s omitted)
and the Popen-based progress-reporting path (total_duration_s supplied).

The progress path is exercised against fake stream objects rather than a
real subprocess -- fast, deterministic, and lets us assert on exactly
which progress lines get logged and at what throttling. A real end-to-end
run against actual ffmpeg (verifying no deadlock and real mid-run log
output) is done separately, outside pytest, per the task's verification
standard -- see TASK.md / the commit message for that evidence.
"""

import logging
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from soundweave.ffmpeg.executor import (
    ProcessingError,
    _format_hms,
    _parse_out_time_seconds,
    run_ffmpeg,
)


@pytest.fixture
def logger():
    return MagicMock(spec=logging.Logger)


class _FakeStream:
    """Minimal stand-in for a Popen pipe's text-mode file object.

    `readline()` pops one queued line per call and returns "" once
    exhausted (matching real pipe EOF behavior), which is what
    `iter(stream.readline, "")` in the executor relies on.
    """

    def __init__(self, lines: list[str]):
        self._lines = list(lines)
        self.closed = False

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        return ""

    def close(self) -> None:
        self.closed = True


def _make_fake_popen(stdout_lines, stderr_lines, wait_return=0, wait_side_effect=None):
    """Build a MagicMock standing in for a subprocess.Popen instance."""
    fake_proc = MagicMock()
    fake_proc.stdout = _FakeStream(stdout_lines)
    fake_proc.stderr = _FakeStream(stderr_lines)
    if wait_side_effect is not None:
        fake_proc.wait.side_effect = wait_side_effect
    else:
        fake_proc.wait.return_value = wait_return
    return fake_proc


# ---------------------------------------------------------------------------
# Helper parsing functions
# ---------------------------------------------------------------------------


class TestParseOutTimeSeconds:
    def test_parses_hms_with_fraction(self):
        assert _parse_out_time_seconds("00:01:05.500000") == pytest.approx(65.5)

    def test_parses_zero(self):
        assert _parse_out_time_seconds("00:00:00.000000") == 0.0

    def test_parses_hours(self):
        assert _parse_out_time_seconds("01:02:03.000000") == pytest.approx(3723.0)

    def test_na_returns_none(self):
        assert _parse_out_time_seconds("N/A") is None

    def test_empty_returns_none(self):
        assert _parse_out_time_seconds("") is None

    def test_garbage_returns_none(self):
        assert _parse_out_time_seconds("not-a-time") is None


class TestFormatHms:
    def test_under_an_hour_omits_hour_field(self):
        assert _format_hms(125) == "2:05"

    def test_over_an_hour_includes_hour_field(self):
        assert _format_hms(3725) == "1:02:05"

    def test_zero(self):
        assert _format_hms(0) == "0:00"

    def test_negative_clamped_to_zero(self):
        assert _format_hms(-5) == "0:00"


# ---------------------------------------------------------------------------
# Backward-compatible fast path (total_duration_s omitted)
# ---------------------------------------------------------------------------


class TestRunFfmpegNoProgress:
    def test_success_returns_completed_process(self, logger):
        fake_result = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout="", stderr=""
        )
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            result = run_ffmpeg(["ffmpeg", "-i", "in.wav", "out.wav"], logger, "encode")

        mock_run.assert_called_once()
        assert result.returncode == 0

    def test_uses_subprocess_run_not_popen(self, logger):
        """No total_duration_s => no Popen/threads, exactly today's path."""
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("subprocess.run", return_value=fake_result) as mock_run,
            patch("subprocess.Popen") as mock_popen,
        ):
            run_ffmpeg(["ffmpeg", "out.wav"], logger, "encode")

        mock_run.assert_called_once()
        mock_popen.assert_not_called()

    def test_command_not_mutated_with_progress_flag(self, logger):
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        command = ["ffmpeg", "-i", "in.wav", "out.wav"]
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            run_ffmpeg(command, logger, "encode")

        called_command = mock_run.call_args[0][0]
        assert called_command == command
        assert "-progress" not in called_command

    def test_nonzero_exit_raises_processing_error(self, logger):
        fake_result = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=1, stdout="", stderr="Error: bad input"
        )
        with patch("subprocess.run", return_value=fake_result), pytest.raises(ProcessingError):
            run_ffmpeg(["ffmpeg", "-i", "bad.wav", "out.wav"], logger, "encode")

    def test_timeout_raises_processing_error(self, logger):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5)),
            pytest.raises(ProcessingError),
        ):
            run_ffmpeg(["ffmpeg", "out.wav"], logger, "encode", timeout=5)

    def test_missing_binary_raises_processing_error(self, logger):
        with patch("subprocess.run", side_effect=FileNotFoundError()), pytest.raises(ProcessingError):
            run_ffmpeg(["ffmpeg", "out.wav"], logger, "encode")


# ---------------------------------------------------------------------------
# Progress-reporting path (total_duration_s supplied)
# ---------------------------------------------------------------------------


class TestRunFfmpegWithProgress:
    def test_injects_progress_flag_after_executable(self, logger):
        fake_proc = _make_fake_popen(["progress=end\n"], [], wait_return=0)
        command = ["ffmpeg", "-i", "in.wav", "out.wav"]
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            run_ffmpeg(command, logger, "encode", total_duration_s=10.0)

        called_command = mock_popen.call_args[0][0]
        assert called_command == ["ffmpeg", "-progress", "pipe:1", "-i", "in.wav", "out.wav"]
        # Original command list must be untouched (no in-place mutation).
        assert command == ["ffmpeg", "-i", "in.wav", "out.wav"]

    def test_success_returns_completed_process(self, logger):
        fake_proc = _make_fake_popen(
            ["out_time=00:00:10.000000\n", "speed=1.0x\n", "progress=end\n"],
            ["frame=1\n"],
            wait_return=0,
        )
        with patch("subprocess.Popen", return_value=fake_proc):
            result = run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"], logger, "encode", total_duration_s=10.0
            )

        assert result.returncode == 0
        assert "frame=1" in result.stderr

    def test_progress_lines_are_logged_with_percentage(self, logger):
        stdout_lines = [
            "out_time=00:00:25.000000\n",
            "speed=2.50x\n",
            "progress=continue\n",
            "out_time=00:00:50.000000\n",
            "speed=2.50x\n",
            "progress=continue\n",
            "out_time=00:01:40.000000\n",
            "speed=2.50x\n",
            "progress=end\n",
        ]
        fake_proc = _make_fake_popen(stdout_lines, [], wait_return=0)

        with patch("subprocess.Popen", return_value=fake_proc):
            run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"],
                logger,
                "encode",
                total_duration_s=100.0,
                progress_interval_s=0,  # log every block for this assertion
            )

        info_messages = [call.args[0] for call in logger.info.call_args_list]
        assert any("25%" in m for m in info_messages)
        assert any("50%" in m for m in info_messages)
        assert any("100%" in m for m in info_messages)
        # Speed should be surfaced too.
        assert any("2.50x" in m for m in info_messages)

    def test_progress_logging_is_throttled(self, logger):
        # 20 rapid blocks; with a large interval, only the very first block
        # (logged immediately so the user gets early confirmation it's
        # running) and the final "end" block (always logged) should
        # produce a line -- proving we are not logging on every single
        # progress block ffmpeg emits (18 of the 20 blocks here are
        # suppressed by throttling).
        stdout_lines = []
        for i in range(1, 20):
            stdout_lines += [f"out_time=00:00:{i:02d}.000000\n", "progress=continue\n"]
        stdout_lines += ["out_time=00:00:20.000000\n", "progress=end\n"]

        fake_proc = _make_fake_popen(stdout_lines, [], wait_return=0)

        with patch("subprocess.Popen", return_value=fake_proc):
            run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"],
                logger,
                "encode",
                total_duration_s=20.0,
                progress_interval_s=3600,  # effectively "only log first + last"
            )

        assert logger.info.call_count == 2
        assert "100%" in logger.info.call_args_list[-1].args[0]

    def test_nonzero_exit_raises_processing_error(self, logger):
        fake_proc = _make_fake_popen(
            ["progress=end\n"], ["Error: something broke\n"], wait_return=1
        )
        with patch("subprocess.Popen", return_value=fake_proc), pytest.raises(ProcessingError):
            run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"], logger, "encode", total_duration_s=10.0
            )
        assert logger.error.called

    def test_timeout_raises_processing_error_and_kills_process(self, logger):
        def wait_side_effect(timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)
            return -9

        fake_proc = _make_fake_popen(["progress=end\n"], [], wait_side_effect=wait_side_effect)

        with patch("subprocess.Popen", return_value=fake_proc), pytest.raises(ProcessingError):
            run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"],
                logger,
                "encode",
                timeout=5,
                total_duration_s=10.0,
            )

        fake_proc.kill.assert_called_once()

    def test_missing_binary_raises_processing_error(self, logger):
        with patch("subprocess.Popen", side_effect=FileNotFoundError()), pytest.raises(ProcessingError):
            run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"], logger, "encode", total_duration_s=10.0
            )

    def test_zero_duration_does_not_use_progress_path(self, logger):
        """total_duration_s=0 is falsy -- treated the same as None/omitted,
        since there's nothing meaningful to compute a percentage against."""
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("subprocess.run", return_value=fake_result) as mock_run,
            patch("subprocess.Popen") as mock_popen,
        ):
            run_ffmpeg(["ffmpeg", "out.wav"], logger, "encode", total_duration_s=0)

        mock_run.assert_called_once()
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Concurrent stream draining (deadlock-avoidance) — a lighter-weight,
# still-real check that both pipes are read on separate, live threads
# rather than one being read to completion before the other is touched.
# ---------------------------------------------------------------------------


class TestConcurrentStreamDraining:
    def test_stdout_and_stderr_are_drained_on_separate_threads(self, logger):
        """A stream that blocks until release is only unblocked by a
        separate thread proving the other stream's reader started
        independently -- if the implementation read stdout to completion
        before starting on stderr (or vice versa), this test would hang
        and fail on the join timeout below.
        """
        stderr_release = threading.Event()

        class _BlockingThenLines(_FakeStream):
            def __init__(self, lines, release_event):
                super().__init__(lines)
                self._release = release_event
                self._blocked_once = False

            def readline(self):
                if not self._blocked_once:
                    self._blocked_once = True
                    # Block here until the *other* thread signals it has
                    # started reading -- only possible if both threads run
                    # concurrently.
                    if not self._release.wait(timeout=5):
                        raise AssertionError("stderr reader never started concurrently")
                return super().readline()

        fake_proc = MagicMock()
        fake_proc.stdout = _BlockingThenLines(["progress=end\n"], stderr_release)

        class _SignalingStderr(_FakeStream):
            def readline(self):
                stderr_release.set()
                return super().readline()

        fake_proc.stderr = _SignalingStderr(["log line\n"])
        fake_proc.wait.return_value = 0

        with patch("subprocess.Popen", return_value=fake_proc):
            result = run_ffmpeg(
                ["ffmpeg", "-i", "in.wav", "out.wav"],
                logger,
                "encode",
                total_duration_s=10.0,
            )

        assert result.returncode == 0
