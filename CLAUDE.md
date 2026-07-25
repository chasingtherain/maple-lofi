# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Soundweave is a local CLI that turns a folder of audio files into a single crossfaded, loudness-normalized longplay, with an optional static-image YouTube video and auto-generated chapter timestamps. There's also a `loop` subcommand that repeats one file N times with silence gaps (for 1-hour loop videos). No cloud services, no GUI — Python orchestrates, FFmpeg does all audio/video processing via subprocess.

A YouTube-sourced "mashup" mode (download audio from a list of URLs instead of reading a local folder) is planned — see `PRD.md` before touching anything related to that.

## Commands

```bash
# Setup (creates .venv/, installs pytest/ruff/black)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Run the main pipeline
python3 -m soundweave --input input --output output --image cover.png

# Run the loop subcommand
python3 -m soundweave loop mysong.mp3 --count 5

# Tests (none exist yet beyond tests/__init__.py — the scaffolding is there but empty)
.venv/bin/pytest tests/
.venv/bin/pytest tests/test_foo.py::test_bar   # single test, once tests exist

# Lint / format
.venv/bin/ruff check soundweave/
.venv/bin/black soundweave/
```

FFmpeg 4.0+ must be installed and on `PATH` (validated at pipeline startup via `validate_ffmpeg()`).

## Architecture

**Flow**: CLI (`cli.py`) parses args → builds a `PipelineConfig` (`config.py`) → `Pipeline.run()` (`pipeline.py`) executes stages in order → each stage is a pure function `stage(inputs, config, logger) -> output_path`, reads/writes only what's passed in, no global state.

**Stages, in order** (`soundweave/stages/`):
1. `ingest.py` — discover audio files in `--input` dir (top-level only), order them via `order.txt` if present (else natural sort), optionally shuffle, probe metadata via ffprobe. `order.txt` format: one filename per line, `#` comments, duplicates allowed, blank lines ignored — see `parse_order_file()`.
2. `merge.py` — crossfade all tracks into one file via FFmpeg's `acrossfade` filter graph. Crossfade duration auto-shrinks to 50% of the shorter track when a track is shorter than the configured `--fade-ms`.
3. (inline in `pipeline.py`, not its own stage file) — MP3 encoding (320kbps) + YouTube chapter-timestamp generation. Timestamps are computed from **actual post-loudnorm durations** (measured via `probe_loudnorm_duration`), not nominal file durations, because loudness normalization can shift length slightly.
4. `video.py` — optional; pairs the merged audio with one static image, letterboxed to 1920x1080 @ 1fps. Skipped entirely if `--image` isn't passed.

The `loop` subcommand is a parallel, separate entry point (`_run_loop_subcommand` in `cli.py`) with its own `LoopConfig` (`loop_config.py`) and its own stage (`stages/loop.py`) — it does not go through `Pipeline`/`PipelineConfig`. This is the established pattern for adding a subcommand that doesn't fit the main folder-of-tracks pipeline shape (relevant precedent for the planned `mashup` subcommand in `PRD.md`).

**FFmpeg abstraction** (`soundweave/ffmpeg/`): `commands.py` has pure functions that *build* command argument lists (`build_merge_command`, `build_mp3_command`, `build_loop_command`, `build_video_command`) — they return `list[str]`, never execute anything. `executor.py`'s `run_ffmpeg()` actually runs them via `subprocess`, logs the command, and raises `ProcessingError` on failure. `probe.py` wraps `ffprobe` for metadata. Adding new FFmpeg-backed behavior means adding a `build_*_command()` here, not shelling out from inside a stage.

**Exit codes are meaningful and load-bearing**: `0` success, `1` `ValidationError` (bad input, missing FFmpeg — caught in `cli.py`/`pipeline.py`), `2` `ProcessingError` (FFmpeg failure), `3` output error (disk full etc.). Preserve this contract when adding new failure paths.

**Dual output on every run**: `run_log.txt` (human-readable, via `logging/logger.py`) and `manifest.json` (machine-readable audit trail — inputs, outputs with SHA256/size, per-stage timing, every FFmpeg command executed, warnings/errors — built incrementally via `ManifestBuilder` in `logging/manifest.py`). The manifest is written even on failure (partial state) for debugging. Any new stage should report itself into both.

**No external Python packages in production code** — stdlib only (`argparse`, `subprocess`, `dataclasses`, `pathlib`, `logging`, `json`, `hashlib`). `pytest`/`ruff`/`black` are dev-only, under `[project.optional-dependencies].dev` in `pyproject.toml`. If the planned YouTube-download feature needs `yt-dlp`, the existing convention is to shell out to it as an external binary via a `commands.py`/`executor.py` pair mirroring `ffmpeg/`, not add it as a pip dependency — see `PRD.md` §5.

## Known drift / gaps (don't be surprised by these)

- `SPECIFICATION.md` and some ADR/architecture docs describe a "lofi" processing stage (texture/drums mixing, EQ, compression) that **does not exist in the code** — it was removed in an earlier refactor (`ca155e6`) that transformed this from a lofi-specific processor into a general random-track-selector/mashup tool, but the docs weren't fully updated. Don't assume `docs/` and `SPECIFICATION.md` are ground truth for current behavior; the stage modules in `soundweave/stages/` are.
- `tests/` has no actual test files yet, only `__init__.py`. `pyproject.toml` is already configured for pytest (`testpaths = ["tests"]`), so adding `tests/test_*.py` files just works.
