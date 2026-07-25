# TASK.md — Parallel work breakdown

Scoped units of work sized for independent agents running in separate worktrees, with explicit file ownership so diffs don't collide. This is the task list behind the Stage 2 ("Parallel") orchestration exercise described in `AI-stages.md` — see the chat for the walkthrough of how to actually run it.

## Ground rules for every task

- One task = one worktree = one branch = one diff to review. Don't touch files outside your task's "Owns" list — if you find you need to, stop and flag it rather than routing around it; that means the task boundary was wrong.
- Before a task is "ready for review": `.venv/bin/pytest tests/` and `.venv/bin/ruff check soundweave/` both pass.
- Every diff gets `/code-review` before merging. Non-negotiable — this is what makes reviewing a finished diff take two minutes instead of twenty.
- Reference `CLAUDE.md` for architecture/conventions and `PRD.md` for the mashup feature spec before starting.

---

## Tier 0 — solo, sequential, do first

### T0: Lint cleanup

**Owns**: `soundweave/pipeline.py`, `soundweave/utils/validators.py`, `soundweave/logging/manifest.py`, `soundweave/ffmpeg/probe.py`, `soundweave/ffmpeg/executor.py`, `soundweave/stages/ingest.py`, `soundweave/utils/youtube.py`, `soundweave/logging/logger.py`, and only the two `except Exception` findings in `soundweave/cli.py`'s top-level error handling (not the argparse sections).

**Why this runs alone, first**: `ruff check soundweave/` findings are scattered across nearly every existing file, including `cli.py`, which T2 also edits. Run this in parallel with anything else and every other task ends up rebasing against a moving target.

**Acceptance**: `ruff check soundweave/` reports 0 findings. Pipeline still runs end-to-end against `real_input/` (or a fixture) with unchanged behavior.

**Merge before starting Tier 1.**

---

## Tier 1 — parallel batch (separate worktrees, run together)

### T1: Unit tests for existing pure functions

**Owns (new files only)**: `tests/test_natural_sort.py`, `tests/test_ingest.py`, `tests/test_merge.py`, `tests/test_youtube.py`

**Scope**: cover the pure, FFmpeg-free functions —
- `soundweave/utils/natural_sort.py::natural_sort`
- `soundweave/stages/ingest.py::parse_order_file`, `validate_ordering`, `determine_track_order`
- `soundweave/stages/merge.py::calculate_crossfade_durations`
- `soundweave/utils/youtube.py::clean_track_name`, `format_timestamp`, `generate_youtube_timestamps`, `format_youtube_description`

Edge cases already implied by existing docstrings: `order.txt` duplicates/comments/blank lines, short-track crossfade reduction to 50%, numbered-prefix filenames (`"1-05. Littleroot Town_.mp3"`).

**Conflict surface**: none — only adds new files under `tests/`.

**Acceptance**: `pytest tests/ -v` passes, one test file per module above.

### T2: Mashup Phase 1 — YouTube download stage

**Owns (new files)**: `soundweave/ytdlp/executor.py`, `soundweave/ytdlp/commands.py`, `soundweave/stages/download.py`, `soundweave/mashup_config.py`

**Owns (existing file, additive only)**: `soundweave/cli.py` — add `parse_mashup_args()` / `_run_mashup_subcommand()` / dispatch, mirroring the existing `loop` subcommand exactly (`parse_loop_args`/`_run_loop_subcommand`). Don't touch the `main`/`loop` code paths.

**Spec**: `PRD.md` §5-6. `yt-dlp` runs as an external subprocess binary, not a pip dependency — mirror the `ffmpeg/` module's `executor.py`/`commands.py` split. `urls.txt` format matches `order.txt` (one URL per line, `#` comments). Default order = as-listed, no shuffle. Reuses `merge_stage`/MP3 encoding unchanged — don't modify `merge.py` or `pipeline.py`.

**Acceptance**: `soundweave mashup --urls urls.txt --output output` runs end-to-end against a short real `urls.txt` (2-3 public videos) and produces `merged.mp3` + `youtube_description.txt` with real video titles. Automated tests mock the `yt-dlp` subprocess call — no network access in the test suite.

### T3: Mashup Phase 2 — per-track video image swap

**Owns**: `soundweave/stages/video.py` (additive — new function, e.g. `video_sequence_stage()`; don't change the existing single-image path/signature), `soundweave/ffmpeg/commands.py` (new `build_video_sequence_command()`; don't modify `build_video_command()`)

**Owns (new file)**: `tests/test_video.py` (timing-calculation logic only — not actual FFmpeg execution)

**Spec**: `PRD.md` §7. `--images <dir>` holds one image per track, held for that track's actual measured duration; error at pre-flight if there are fewer images than tracks.

**Does not touch `cli.py`.** The `--images` flag wiring into the mashup subcommand is deliberately deferred to Tier 2, so T2 and T3 never compete for the same file. Build and test this against a hand-constructed list of `(image_path, duration_s)` pairs, independent of the CLI.

---

## Tier 2 — integration (solo, after T2 and T3 both merge)

Wire T3's `--images` flag into T2's mashup subcommand in `cli.py` — the one deliberate point of contact between the two tasks, a few lines, done once both sides exist.
