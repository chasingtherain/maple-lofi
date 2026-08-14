"""Tests for soundweave.ui.progress.infer_phase.

Log samples below are drawn from real captured output (the shape logged by
cli.py's mashup/loop runners -- see PRD_LAUNCH.md Sec 2 for which stage
markers actually exist today), not invented strings, so a change to the
real log format is more likely to be caught here.
"""

from soundweave.ui.progress import infer_phase

_REAL_LOOP_LOG = """\
INFO: ============================================================
INFO: Soundweave - Loop Subcommand
INFO: ============================================================
INFO: Run ID:    f959714b-bf5e-48dc-80d3-8fb378e82d17
INFO: Timestamp: 2026-08-14T05:58:24.452058+00:00
INFO:
INFO: === Loop Stage ===
INFO: Input:    input.wav
INFO: Count:    2x
INFO: Running FFmpeg loop command...
INFO: FFmpeg completed in 0.1s
INFO: Output: input_x2.mp3 (0.2MB)
INFO: Loop stage complete.
INFO:
INFO: ============================================================
INFO: Loop completed successfully!
INFO: ============================================================
"""

_REAL_MASHUP_ENCODING_LOG = """\
INFO: ============================================================
INFO: Soundweave - Mashup Subcommand
INFO: ============================================================
INFO: Run ID:    abc123
INFO:
INFO: === Stage 3: MP3 Encoding & YouTube Timestamps ===
INFO: Encoding to MP3 (320kbps)...
"""

_REAL_MASHUP_VIDEO_LOG = (
    _REAL_MASHUP_ENCODING_LOG
    + """\
INFO:   merged.mp3 (4.1MB)
INFO: Generating YouTube timestamps...
INFO:   youtube_description.txt
INFO:
INFO: === Stage 4: Video Rendering ===
INFO: Rendering video...
"""
)


class TestInferPhaseWhileRunning:
    def test_no_stage_markers_yet_is_preparing(self):
        log = "INFO: Soundweave - Mashup Subcommand\nINFO: Downloading track 1/5...\n"
        assert infer_phase(log, running=True, returncode=None) == "preparing"

    def test_empty_log_is_preparing(self):
        assert infer_phase("", running=True, returncode=None) == "preparing"

    def test_stage_3_marker_is_encoding(self):
        assert infer_phase(_REAL_MASHUP_ENCODING_LOG, running=True, returncode=None) == "encoding"

    def test_stage_4_marker_is_video(self):
        assert infer_phase(_REAL_MASHUP_VIDEO_LOG, running=True, returncode=None) == "video"

    def test_stage_4_wins_when_both_markers_present(self):
        # Both stage 3 and stage 4 headers are in the log by the time
        # stage 4 starts -- video (the later stage) must win, not encoding.
        log = _REAL_MASHUP_ENCODING_LOG + "=== Stage 4: Video Rendering ===\n"
        assert infer_phase(log, running=True, returncode=None) == "video"


class TestInferPhaseWhenFinished:
    def test_returncode_zero_is_done_regardless_of_log_content(self):
        # Deliberately an empty/irrelevant log -- done/failed must come from
        # the returncode, not from string-matching "completed successfully"
        # or similar (a video title could coincidentally contain that text).
        assert infer_phase("", running=False, returncode=0) == "done"

    def test_real_loop_completion_log_with_returncode_zero_is_done(self):
        assert infer_phase(_REAL_LOOP_LOG, running=False, returncode=0) == "done"

    def test_nonzero_returncode_is_failed(self):
        assert infer_phase("Traceback (most recent call last):\n", running=False, returncode=1) == "failed"

    def test_nonzero_returncode_is_failed_even_with_a_clean_looking_log(self):
        # A log that never got far enough to hit any error text, but the
        # process still exited nonzero (e.g. killed) -- returncode wins.
        assert infer_phase("INFO: Starting...\n", running=False, returncode=2) == "failed"
