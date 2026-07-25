"""Tests for soundweave/ytdlp/executor.py — subprocess execution, fully mocked.

No network access / real yt-dlp invocation happens here: subprocess.run is
monkeypatched in every test.
"""

import logging
import subprocess
from unittest.mock import patch

import pytest

from soundweave.utils.validators import ValidationError
from soundweave.ytdlp.executor import YtDlpError, run_ytdlp, validate_ytdlp


@pytest.fixture
def logger():
    log = logging.getLogger("test-ytdlp-executor")
    log.addHandler(logging.NullHandler())
    return log


class TestRunYtdlp:
    def test_success_returns_completed_process(self, logger):
        fake_result = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0, stdout='{"id": "abc"}', stderr=""
        )
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            result = run_ytdlp(["yt-dlp", "--dump-json", "url"], logger, "fetch metadata")

        mock_run.assert_called_once()
        assert result.returncode == 0
        assert result.stdout == '{"id": "abc"}'

    def test_nonzero_exit_raises_ytdlp_error(self, logger):
        fake_result = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=1, stdout="", stderr="ERROR: video unavailable"
        )
        with patch("subprocess.run", return_value=fake_result), pytest.raises(YtDlpError):
            run_ytdlp(["yt-dlp", "url"], logger, "download")

    def test_timeout_raises_ytdlp_error(self, logger):
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="yt-dlp", timeout=5)),
            pytest.raises(YtDlpError),
        ):
            run_ytdlp(["yt-dlp", "url"], logger, "download", timeout=5)

    def test_missing_binary_raises_ytdlp_error(self, logger):
        with patch("subprocess.run", side_effect=FileNotFoundError()), pytest.raises(YtDlpError):
            run_ytdlp(["yt-dlp", "url"], logger, "download")

    def test_passes_command_through_to_subprocess(self, logger):
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        command = ["yt-dlp", "--dump-json", "https://youtube.com/watch?v=xyz"]
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            run_ytdlp(command, logger, "fetch metadata")

        called_command = mock_run.call_args[0][0]
        assert called_command == command


class TestValidateYtdlp:
    def test_success_returns_version_string(self):
        fake_result = subprocess.CompletedProcess(
            args=["yt-dlp", "--version"], returncode=0, stdout="2024.03.10\n", stderr=""
        )
        with patch("subprocess.run", return_value=fake_result):
            version = validate_ytdlp()
        assert version == "2024.03.10"

    def test_missing_binary_raises_validation_error(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()), pytest.raises(ValidationError):
            validate_ytdlp()

    def test_nonzero_exit_raises_validation_error(self):
        fake_result = subprocess.CompletedProcess(
            args=["yt-dlp", "--version"], returncode=1, stdout="", stderr="boom"
        )
        with patch("subprocess.run", return_value=fake_result), pytest.raises(ValidationError):
            validate_ytdlp()

    def test_timeout_raises_validation_error(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="yt-dlp", timeout=10),
        ), pytest.raises(ValidationError):
            validate_ytdlp()
