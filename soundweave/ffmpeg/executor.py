"""FFmpeg command execution with logging."""

import logging
import subprocess
from pathlib import Path


class ProcessingError(Exception):
    """Raised when FFmpeg processing fails (exit code 2)."""
    pass


def run_ffmpeg(
    command: list[str],
    logger: logging.Logger,
    description: str,
    timeout: int | None = None
) -> subprocess.CompletedProcess:
    """Execute an FFmpeg command with logging and error handling.

    Args:
        command: FFmpeg command as list of arguments
        logger: Logger instance
        description: Human-readable description of what this command does
        timeout: Optional timeout in seconds (None = no timeout)

    Returns:
        CompletedProcess result

    Raises:
        ProcessingError: If FFmpeg returns non-zero exit code
    """
    # Log the command being run
    logger.debug(f"Running FFmpeg: {description}")
    logger.debug(f"Command: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Check exit code
        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {description}")
            logger.error(f"Exit code: {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            raise ProcessingError(f"FFmpeg failed: {description}")

        # Log success
        logger.debug(f"FFmpeg succeeded: {description}")

        # Log warnings from stderr (FFmpeg writes progress info to stderr)
        if result.stderr:
            logger.debug(f"FFmpeg stderr: {result.stderr[:500]}")  # First 500 chars

        return result

    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg timed out after {timeout}s: {description}")
        raise ProcessingError(f"FFmpeg timed out: {description}")

    except FileNotFoundError:
        logger.error("FFmpeg executable not found")
        raise ProcessingError("FFmpeg not found in PATH")
