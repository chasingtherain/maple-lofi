# TASK.md — Work breakdown

Scoped units of work sized for independent agents running in separate worktrees, with explicit file ownership so diffs don't collide. This is the task list behind the Stage 2 ("Parallel") orchestration exercise described in `AI-stages.md`.

## Ground rules for every task

- One task = one worktree = one branch = one diff to review. Don't touch files outside your task's "Owns" list — if you find you need to, stop and flag it rather than routing around it; that means the task boundary was wrong.
- Before a task is "ready for review": `.venv/bin/pytest tests/` and `.venv/bin/ruff check soundweave/` both pass.
- Every diff gets `/code-review` before merging. Non-negotiable — this is what makes reviewing a finished diff take two minutes instead of twenty.
- Reference `CLAUDE.md` for architecture/conventions and `PRD.md` for the mashup feature spec before starting.

---

## Completed

The original parallel-orchestration batch (T0-T3) plus its Tier 2 integration step are done and merged to `main`. Kept here as a record of what shipped; not actionable.

- **T0 — Lint cleanup** ✅ `cf851e3`. `ruff check soundweave/` clean; 8 remaining blind-except findings configured off in `pyproject.toml` (documented rationale) rather than papered over per-line.
- **T1 — Unit tests for existing pure functions** ✅ `4e7000e`. `natural_sort`, `ingest.py` order.txt parsing, `merge.py` crossfade-duration calc, `youtube.py` track-name/timestamp formatting. 76 tests.
- **T2 — Mashup Phase 1 (YouTube download stage)** ✅ `877548b`. `soundweave/ytdlp/`, `soundweave/stages/download.py`, `soundweave/mashup_config.py`, `mashup` subcommand in `cli.py`. Verified against real YouTube URLs.
- **T3 — Mashup Phase 2 (per-track video image swap)** ✅ `5fcf82f`. `video_sequence_stage()`, `build_video_sequence_command()`, `match_images_to_tracks()`.
- **Tier 2 integration — wire `--image`/`--images` into `mashup`** ✅ `60f498a`. `MashupConfig.static_image`/`images_dir`, mutually-exclusive CLI flags.
- **Real-world validation run** ✅ 2026-07-25. 3 real YouTube URLs + a static background image → verified playable `final_video.mp4` (correct streams, correct duration, correct tracklist) via independent `ffprobe`/frame inspection, not just agent self-report.

---

## Next up

### T1: On-video "Now Playing" track cards

**Status**: not started. Renumbered from T4 (2026-07-25) — the "branded thumbnail" half of that task is dropped: the user will provide their own thumbnail, so thumbnail generation is out of scope entirely, not just deferred.

**Owns**: `soundweave/stages/video.py` (additive), `soundweave/ffmpeg/commands.py` (additive — new `drawtext`-based command builder), `soundweave/cli.py` (additive — wire into the `mashup` subcommand).

**Scope**: burn the track title into the video at each track's actual start timestamp (reuse the same per-track timestamp data that already drives `youtube_description.txt` — do not recompute), fading in/out over ~4-5s via ffmpeg's `drawtext` filter (one `enable='between(t,start,start+5)'` clause per track). Requires: a font available at render time, and correct escaping of special characters (quotes/colons) in track titles passed to `drawtext`.

**Out of scope**: thumbnail generation (user-provided) and YouTube Data API auto-upload (separate, bigger future task — OAuth, quota, metadata push).

**Acceptance**: a mashup run produces a video with visible, correctly-timed track-title overlays matching `youtube_description.txt`'s timestamps. Existing single-image/per-track-image video modes (`video_stage()`/`video_sequence_stage()`) unchanged in behavior when this feature is off.
