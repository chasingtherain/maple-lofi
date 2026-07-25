"""yt-dlp command execution with logging.

Mirrors soundweave/ffmpeg/executor.py: run_ytdlp() executes a command built by
commands.py via subprocess, logs it, and raises YtDlpError on failure.
"""

import logging
import subprocess

from soundweave.utils.validators import ValidationError


class YtDlpError(Exception):
    """Raised when a yt-dlp invocation fails (analogous to ProcessingError)."""


def run_ytdlp(
    command: list[str],
    logger: logging.Logger,
    description: str,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Execute a yt-dlp command with logging and error handling.

    Args:
        command: yt-dlp command as a list of arguments (from commands.py).
        logger: Logger instance.
        description: Human-readable description of what this command does.
        timeout: Optional timeout in seconds (None = no timeout).

    Returns:
        CompletedProcess result (stdout/stderr captured as text).

    Raises:
        YtDlpError: If yt-dlp returns a non-zero exit code, times out, or the
            `yt-dlp` executable can't be found on PATH.
    """
    logger.debug(f"Running yt-dlp: {description}")
    logger.debug(f"Command: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {description}")
            logger.error(f"Exit code: {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            raise YtDlpError(f"yt-dlp failed: {description}")

        logger.debug(f"yt-dlp succeeded: {description}")

        if result.stderr:
            logger.debug(f"yt-dlp stderr: {result.stderr[:500]}")

        return result

    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp timed out after {timeout}s: {description}")
        raise YtDlpError(f"yt-dlp timed out: {description}")

    except FileNotFoundError:
        logger.error("yt-dlp executable not found")
        raise YtDlpError(
            "yt-dlp not found in PATH. Install it as a dev-only tool "
            "(e.g. '.venv/bin/pip install yt-dlp') — it is not a project "
            "dependency, it's shelled out to as an external binary."
        )


def validate_ytdlp() -> str:
    """Check that yt-dlp is installed and available on PATH.

    Mirrors soundweave.utils.validators.validate_ffmpeg()'s pre-flight-check
    shape, kept local to this module since yt-dlp isn't yet a dependency of
    the main pipeline's pre-flight checks.

    Returns:
        yt-dlp version string (e.g. "2024.03.10").

    Raises:
        ValidationError: If yt-dlp is not found or the version check fails.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            raise ValidationError("yt-dlp --version command failed")

        return result.stdout.strip()

    except FileNotFoundError:
        raise ValidationError(
            "yt-dlp not found. Install it as a dev-only tool "
            "(e.g. '.venv/bin/pip install yt-dlp') or via your OS package "
            "manager, and ensure it's on PATH. It is shelled out to as an "
            "external binary, not a project dependency."
        )
    except subprocess.TimeoutExpired:
        raise ValidationError("yt-dlp --version timed out")
