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
- **T2 — DepthFlow ambient background pipeline** ✅ `9f779bb` (2026-07-25). Standalone tool at `tools/ambient_bg/`, not part of `soundweave`. Full writeup below (result summary + original spec) since this one has enough tuning/verification detail worth keeping, not just a one-liner.

---

## Next up

### T1: On-video "Now Playing" track cards

**Status**: not started. Renumbered from T4 (2026-07-25) — the "branded thumbnail" half of that task is dropped: the user will provide their own thumbnail, so thumbnail generation is out of scope entirely, not just deferred.

**Owns**: `soundweave/stages/video.py` (additive), `soundweave/ffmpeg/commands.py` (additive — new `drawtext`-based command builder), `soundweave/cli.py` (additive — wire into the `mashup` subcommand).

**Scope**: burn the track title into the video at each track's actual start timestamp (reuse the same per-track timestamp data that already drives `youtube_description.txt` — do not recompute), fading in/out over ~4-5s via ffmpeg's `drawtext` filter (one `enable='between(t,start,start+5)'` clause per track). Requires: a font available at render time, and correct escaping of special characters (quotes/colons) in track titles passed to `drawtext`.

**Out of scope**: thumbnail generation (user-provided) and YouTube Data API auto-upload (separate, bigger future task — OAuth, quota, metadata push).

**Acceptance**: a mashup run produces a video with visible, correctly-timed track-title overlays matching `youtube_description.txt`'s timestamps. Existing single-image/per-track-image video modes (`video_stage()`/`video_sequence_stage()`) unchanged in behavior when this feature is off.

---

## T2: DepthFlow ambient background pipeline — full record (done, kept for reference)

**Status**: ✅ done `9f779bb` (2026-07-25). Implemented and verified end-to-end on this machine (M1 Pro, no NVIDIA, MPS-only). Scoped 2026-07-25. This grew out of the "how to animate a static background without it looking artificial" discussion earlier — DepthFlow's depth-based 2.5D parallax is a materially different (and better-suited) technique than the `zoompan` Ken Burns experiment that was tried and rejected as "too artificial."

**Result summary**: all four stages built and independently re-run during verification (not just executed once end-to-end). Used the input image at `real_assets/c3387f31601b9a2f95b61bf63496f8ab.jpg` (735x416 anime landscape painting) since `./scene.png` was never user-supplied — referenced directly via `--scene` (default), not duplicated.

- **GPU/hardware finding, the important surprise**: this genuinely was expected to be the risky part (M1 Pro, no dedicated GPU, MPS-only per the original brief) but turned out not to be a blocker at all. DepthFlow's rendering is `moderngl`/OpenGL over GLFW, which runs on Apple's Metal-backed OpenGL just fine — a full 20s 1920x1080 30fps parallax render took **~5.7s** (2-4x realtime), and the 20s particle layer took **~9s**. Depth estimation (DepthAnythingV2-small) is <1s once the model is loaded. No CPU fallback, no multi-minute renders, nothing close to "prohibitively long." `setup_check.py`'s NVIDIA and CPU-only code paths were verified by exercising `detect_gpu_mode()` with the other two hardware scenarios simulated (monkeypatched `platform.machine`/`shutil.which`/`subprocess.run`), since only the Apple Silicon path is real on this hardware — both returned immediately with correct mode and no hang.
- **Real bug hit and fixed during verification, not glossed over**: `particles.py`'s alpha channel was initially all-zero in the exported `.mov` — the compositing math left alpha in `[0,1]` while RGB was scaled to `[0,255]`, so every alpha value truncated to 0 on the `uint8` cast. Caught by actually inspecting the raw pixel bytes (not trusting "ffmpeg exited 0"), fixed, re-verified nonzero alpha (max 126/255) and a real particle layer visible when composited over a solid background.
- **Real artifact hit and fixed during tuning**: at `zoom=1.0` (full image, no crop margin), the parallax offset revealed a hard black line/seam at the image's out-of-bounds edge on a test render. Fixed with `--zoom-crop 0.90` (crops in 10%, matching DepthFlow's own example presets which use 0.95-0.98) — confirmed gone on the next render.
- **Depth map quality on this specific low-res source**: good, not a problem. `output/depth_map.png` is a clean near-to-far gradient (bright foreground boulders/grass, dark distant mountains/sky) with clean edges around the foreground rocks — no noisy/warped edges despite the 735x416 source resolution being called out as a risk upfront.
- **Verification standard actually applied**: `ffprobe` confirmed `base.mp4`/`particles.mov`/`final.mp4` are real streams at the correct resolution/fps/duration (not zero-byte/corrupt); frame checksums at multiple timeline positions were distinct (confirming actual motion, not a static frame repeated); first-vs-last-frame pixel diffs were computed for both `base.mp4` (~1.0/255 mean) and `final.mp4` (~1.5/255 mean) to confirm a clean loop seam, not just eyeballed.
- **No structural blockers hit.** Everything in TASK.md's original scope shipped.

**Addendum, 2026-07-25 — real feedback: the "low intensity, gentle" defaults were too subtle to notice at all.** The spec's own 5-15% motion-intensity / ~20-30% particle-opacity guidance, verified above as producing a clean loop with real (if faint) motion, turned out to be genuinely invisible on actual playback. Quantified before changing anything: parallax mean pixel diff was only 3.0/255 a quarter-cycle in; the particle layer changed only 0.109% of frame pixels (max delta 23/255). Raised the actual script defaults (not just documented as available flags): `motion-intensity` 0.10→0.40, `depth-intensity` 0.15→0.35, `zoom-crop` 0.90→0.75 (more margin for the stronger motion; reverified 0% black-edge border pixels), particle `count` 90→200, `max-opacity` 0.55→0.9, a new `radius-min`/`radius-max` pair (was hardcoded 1.5-5.0px, now 5.0-14.0px default — **size mattered more than count or opacity** for actually reading as visible at 1920x1080), composite `opacity` 0.25→0.55. Reverified after: parallax mean diff 3.0→12.5/255 (4.2x), particle-affected pixels 0.109%→2.322% (21x), max delta 23→97/255, loop seam still clean (2.206/255, threshold 3.0). Full pipeline re-run with zero extra flags to confirm the new numbers are the actual defaults, not a one-off manual tune. Commit `35c05f0`.

**Placement decision (made deliberately, not defaulted into)**: lives at `tools/ambient_bg/` — **outside** the `soundweave` package, with its own dependencies, not added to `pyproject.toml`. Reasoning: this pipeline is exploratory right now (adjustable intensity because the right look isn't known yet, a depth-map checkpoint specifically so bad output can be caught before a full render, independently re-runnable stages for tuning) — that's research-tool ergonomics, not finished-feature ergonomics. DepthFlow also pulls in a genuinely heavy, GPU-dependent chain (PyTorch, OpenGL rendering, depth-estimation models), unlike `ffmpeg`/`yt-dlp` which are single binaries shelled out to. Bolting it onto the core package before the output quality is validated would be the wrong order of operations. **Not** wired into the `loop` subcommand or the mashup pipeline — if this proves out, pairing `final.mp4` with `loop`'s looped audio into a combined stream is a separate, later, much smaller task.

**Prerequisite**: `./scene.png` (the input image) doesn't exist yet — user-supplied, not part of this task. ~~Resolved for implementation/verification purposes by pointing `--scene`'s default at `real_assets/c3387f31601b9a2f95b61bf63496f8ab.jpg`, the same low-res (735x416) landscape painting used elsewhere in this project, referenced directly rather than duplicated.~~

**Structure**: separate, independently re-runnable scripts, not one monolithic pipeline — `setup_check.py`, `depth_render.py`, `particles.py`, `composite.sh` (or equivalent). Each prints its own render time.

**Step 0 — `setup_check.py`**:
- `pip install depthflow` (PyPI package from `github.com/BrokenSource/DepthFlow` — explicitly **not** depthflow.io, an unrelated paid SaaS product; verify the installed package actually resolves to the right project, don't just trust the package name).
- Confirm `ffmpeg` is on PATH.
- GPU detection, in order: NVIDIA (`nvidia-smi` succeeds → use NVENC for encoding) → Apple Silicon (`PYTORCH_ENABLE_MPS_FALLBACK=1`, since some depth-model ops aren't implemented on MPS yet — warn it'll be slower) → no GPU/no OpenGL (fall back to CPU, **warn explicitly that render times will be much longer, don't silently hang**). This machine is an M1 Pro (confirmed earlier this session) — the Apple Silicon path is what'll actually run here first.
- Print a short summary of detected mode before any render starts.
- **Open technical question to resolve here, not pre-decided**: whether DepthFlow exposes a CLI (in which case shell out to it via subprocess, keeping the same pattern as `ffmpeg`/`yt-dlp` even in this standalone tool) or is Python-library-only (in which case it must be imported directly) — verify against the real installed package rather than assuming either way.

**Step 1 — `depth_render.py`** (depth parallax base video):
- Input `./scene.png` → DepthFlow depth estimation (DepthAnything2 or similar) → 2.5D parallax render.
- Motion: slow/gentle drift-orbit, low-intensity preset (~5-15% of default) — this sits behind an hour of music, nothing dramatic.
- Save the intermediate depth map to `./output/depth_map.png` for visual inspection **before** committing to a full render — flag if edges around foreground objects look noisy/warped (the known common failure mode for large near-camera objects in monocular depth estimation).
- Output: 1920x1080, 30fps, 20s seamless loop → `./output/base.mp4`.
- Depth intensity, motion speed/preset, and loop duration must be adjustable via CLI args or a config file, without editing code.

**Step 2 — `particles.py`** (ambient particle overlay, independent of Step 1 — can be built/tuned in parallel with it):
- Soft, small floating particles (dust motes/pollen), slow upward drift, gentle sway, varied size/opacity, low density.
- Build with OpenCV or a headless-browser HTML canvas render — implementer's choice, based on what's actually reliable given what's installed (not pre-decided here).
- Same resolution/fps/loop length as Step 1.
- **Real technical constraint the spec's own fallback clause anticipates**: MP4/H.264 does not support an alpha channel. "Export with alpha" needs a specific codec (e.g. `.mov` with `qtrle`/ProRes 4444, or `.webm` with VP9 `yuva420p`) — plan for this explicitly rather than discovering it mid-implementation, or use the spec's own suggested fallback (a separate matte + compositing step in Step 3 instead of a true alpha video).

**Step 3 — composite** (`composite.sh` or similar):
- ffmpeg overlay of the particle layer onto the parallax base at ~20-30% opacity.
- Export to `./output/final.mp4`.
- Verify the loop point: first and last frame should blend cleanly; add a short crossfade if there's a visible seam.

**Acceptance**: `setup_check.py` correctly detects and reports GPU mode without hanging on any of the three paths (NVIDIA/Apple Silicon/CPU-only); `depth_map.png` is produced and inspectable before the full render commits; `final.mp4` is a seamless 20s loop at 1920x1080/30fps with visibly gentle (not dramatic) parallax motion and a subtle particle layer; all four stages are independently re-runnable without re-running the others.
