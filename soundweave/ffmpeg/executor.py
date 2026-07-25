"""FFmpeg command execution with logging."""

import logging
import subprocess
import threading
import time


class ProcessingError(Exception):
    """Raised when FFmpeg processing fails (exit code 2)."""


def _parse_out_time_seconds(value: str) -> float | None:
    """Parse ffmpeg `-progress`'s `out_time=HH:MM:SS.ffffff` value into seconds.

    Deliberately does NOT use `out_time_ms` / `out_time_us` -- at least one
    common ffmpeg build (8.0, verified on this machine) reports
    `out_time_ms` in *microseconds* despite the name, a known long-standing
    ffmpeg inconsistency across versions. `out_time`'s HH:MM:SS.ffffff
    string form is unambiguous.

    Returns None (rather than raising) for missing/unparseable values --
    ffmpeg emits `out_time=N/A` in the first progress block before any
    output has been produced yet.
    """
    value = value.strip()
    if not value or value == "N/A":
        return None
    try:
        hms, _, frac = value.partition(".")
        h, m, s = (int(part) for part in hms.split(":"))
        seconds = h * 3600 + m * 60 + s
        if frac:
            seconds += int(frac[:6].ljust(6, "0")) / 1_000_000
        return float(seconds)
    except (ValueError, AttributeError):
        return None


def _format_hms(seconds: float) -> str:
    """Format a duration in seconds as H:MM:SS, omitting the hour field when zero."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _drain_progress_pipe(
    stream,
    logger: logging.Logger,
    description: str,
    total_duration_s: float,
    interval_s: float,
) -> None:
    """Consume ffmpeg's `-progress pipe:1` stdout stream, logging a
    throttled percentage/ETA line periodically (not on every progress
    block -- ffmpeg emits one roughly every output frame, far too often).

    Runs on its own thread, started alongside a stderr-draining thread.
    ffmpeg writes `-progress` key=value lines to stdout while its normal
    human-readable status/error output still goes to stderr; OS pipe
    buffers are small (historically ~64KB), so reading one stream to
    completion before touching the other can deadlock if ffmpeg fills the
    other pipe's buffer while we're blocked here. Both streams must be
    drained concurrently -- this function must never be called in a way
    that blocks stderr from also being read.
    """
    out_time_s = 0.0
    speed_x = None
    last_logged = 0.0

    try:
        for raw_line in iter(stream.readline, ""):
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()

            if key == "out_time":
                parsed = _parse_out_time_seconds(value)
                if parsed is not None:
                    out_time_s = parsed
            elif key == "speed":
                stripped = value.rstrip("x")
                try:
                    speed_x = float(stripped) if stripped else None
                except ValueError:
                    speed_x = None
            elif key == "progress":
                now = time.monotonic()
                is_final = value == "end"
                if is_final or (now - last_logged) >= interval_s:
                    last_logged = now
                    pct = (
                        min(100.0, (out_time_s / total_duration_s) * 100.0)
                        if total_duration_s > 0
                        else 0.0
                    )
                    parts = [
                        (
                            f"{description}: {pct:.0f}% "
                            f"({_format_hms(out_time_s)}/{_format_hms(total_duration_s)})"
                        )
                    ]
                    if speed_x:
                        parts.append(f"speed {speed_x:.2f}x")
                        remaining_s = total_duration_s - out_time_s
                        if not is_final and remaining_s > 0:
                            parts.append(f"ETA {_format_hms(remaining_s / speed_x)}")
                    logger.info(", ".join(parts))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _drain_text_pipe(stream, chunks: list[str]) -> None:
    """Consume a text stream to completion, collecting each line.

    Used for stderr while stdout carries `-progress` output on its own
    thread -- see `_drain_progress_pipe`'s docstring for why this must run
    concurrently with, not before or after, the other stream's reader.
    """
    try:
        chunks.extend(iter(stream.readline, ""))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def run_ffmpeg(
    command: list[str],
    logger: logging.Logger,
    description: str,
    timeout: int | None = None,
    total_duration_s: float | None = None,
    progress_interval_s: float = 5.0,
) -> subprocess.CompletedProcess:
    """Execute an FFmpeg command with logging and error handling.

    Args:
        command: FFmpeg command as list of arguments
        logger: Logger instance
        description: Human-readable description of what this command does
        timeout: Optional timeout in seconds (None = no timeout)
        total_duration_s: If provided (and > 0), enables periodic progress
            logging (percentage + ETA) for the duration of this command,
            driven by ffmpeg's own `-progress pipe:1` output. Pass the
            command's expected output duration in seconds. Omit (the
            default, None) to get exactly today's behavior: no `-progress`
            flag added, no extra threads, a single `subprocess.run()` call.
        progress_interval_s: Minimum seconds between logged progress lines
            when total_duration_s is set. Ignored otherwise.

    Returns:
        CompletedProcess result. When total_duration_s is set, `.stdout`
        is `""` rather than ffmpeg's real stdout -- the stdout pipe in
        that mode carries `-progress` key=value spam, not meaningful
        output, and no caller in this codebase inspects `.stdout` or
        `.returncode` after a successful call (only side effects --
        raising ProcessingError on failure -- are relied on). `.stderr`
        is preserved in both modes.

    Raises:
        ProcessingError: If FFmpeg returns a non-zero exit code, times
            out, or the executable is not found.
    """
    logger.debug(f"Running FFmpeg: {description}")
    logger.debug(f"Command: {' '.join(command)}")

    if not total_duration_s:
        # Unchanged fast path: today's exact behavior, byte for byte.
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {description}")
                logger.error(f"Exit code: {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                raise ProcessingError(f"FFmpeg failed: {description}")

            logger.debug(f"FFmpeg succeeded: {description}")
            if result.stderr:
                logger.debug(f"FFmpeg stderr: {result.stderr[:500]}")

            return result

        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timed out after {timeout}s: {description}")
            raise ProcessingError(f"FFmpeg timed out: {description}")

        except FileNotFoundError:
            logger.error("FFmpeg executable not found")
            raise ProcessingError("FFmpeg not found in PATH")

    # Progress-reporting path: subprocess.Popen + two concurrent reader
    # threads. subprocess.run(capture_output=True) blocks until the
    # process exits and only hands back output afterward -- there is no
    # way to observe progress mid-run through it. See _drain_progress_pipe
    # for why both stdout and stderr must be drained concurrently rather
    # than one after the other (deadlock risk on filled pipe buffers).
    progress_command = [command[0], "-progress", "pipe:1", *command[1:]]
    logger.debug(f"Progress-enabled command: {' '.join(progress_command)}")

    try:
        proc = subprocess.Popen(
            progress_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        logger.error("FFmpeg executable not found")
        raise ProcessingError("FFmpeg not found in PATH")

    stderr_lines: list[str] = []

    stdout_thread = threading.Thread(
        target=_drain_progress_pipe,
        args=(proc.stdout, logger, description, total_duration_s, progress_interval_s),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_text_pipe,
        args=(proc.stderr, stderr_lines),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)
        logger.error(f"FFmpeg timed out after {timeout}s: {description}")
        raise ProcessingError(f"FFmpeg timed out: {description}")

    # proc.wait() only waits on the process, not the pipes -- give the
    # reader threads a bounded moment to hit EOF (the process exiting
    # closes its ends of both pipes, so this should be near-instant) and
    # finish flushing collected stderr.
    stdout_thread.join(timeout=10)
    stderr_thread.join(timeout=10)

    result = subprocess.CompletedProcess(
        progress_command, returncode, stdout="", stderr="".join(stderr_lines)
    )

    if result.returncode != 0:
        logger.error(f"FFmpeg failed: {description}")
        logger.error(f"Exit code: {result.returncode}")
        logger.error(f"stderr: {result.stderr}")
        raise ProcessingError(f"FFmpeg failed: {description}")

    logger.debug(f"FFmpeg succeeded: {description}")
    if result.stderr:
        logger.debug(f"FFmpeg stderr: {result.stderr[:500]}")

    return result
