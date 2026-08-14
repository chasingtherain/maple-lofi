"""Coarse phase inference for mashup/loop UI job status.

Ground truth (verified against the code, see PRD_LAUNCH.md Sec 2): stage-
boundary log lines exist for Stage 3 (MP3 encoding) and Stage 4 (video
rendering) in both the `mashup` and `loop` subcommand runners, but not for
earlier stages (download/merge) -- those are only code comments today. This
means phase detection is necessarily coarse (preparing/encoding/video), not
a linear percentage, and this module does not try to fake finer granularity
by guessing at unstated stage boundaries.

"done"/"failed" are read from the subprocess's actual return code, not
inferred from log text -- a returncode is authoritative, whereas string-
matching a log for "error"/"traceback" risks false positives (e.g. a video
title that happens to contain the word "error").
"""

import re

_STAGE_3_RE = re.compile(r"=== Stage 3: MP3 Encoding")
_STAGE_4_RE = re.compile(r"=== Stage 4: Video Rendering")


def infer_phase(log_text: str, running: bool, returncode: int | None) -> str:
    """Infer a coarse UI phase from a job's captured log text and process state.

    Args:
        log_text: The job's captured stdout/stderr so far (or in full, once
            finished).
        running: Whether the subprocess is still running.
        returncode: The subprocess's exit code, or None while still running.

    Returns:
        One of "preparing", "encoding", "video", "done", "failed".
    """
    if not running:
        return "done" if returncode == 0 else "failed"
    if _STAGE_4_RE.search(log_text):
        return "video"
    if _STAGE_3_RE.search(log_text):
        return "encoding"
    return "preparing"
