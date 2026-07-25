# PRD — YouTube Song Mashup Mode

## 1. Problem

Today Soundweave takes a **folder of local audio files** (game OST rips) and produces a shuffled, crossfaded longplay with an optional static-image video. It has no way to source audio from YouTube.

The actual want: pick 10 YouTube videos of songs, hand Soundweave the links, and get back one continuous crossfaded track (in the order chosen) paired with a video (static or per-song image) that's ready to upload to YouTube — reusing the audio pipeline that already exists.

## 2. User workflow (target)

1. User collects 10 YouTube URLs into a text file (`urls.txt`), one per line, in the order they want them to play.
2. User runs one command, pointing at that file and (optionally) a cover image or folder of per-song images.
3. Soundweave downloads audio for each URL, crossfades them in the given order (reusing the existing merge stage), encodes MP3, generates YouTube chapter timestamps (using real video titles instead of filenames), and renders a video.
4. User uploads `final_video.mp4` + `youtube_description.txt` to YouTube.

## 3. Decisions already made (from discussion)

- **Mashup style**: full songs, crossfaded back-to-back — not clipped snippets. This is exactly what Stage 2 (`merge_stage`) already does; no new audio-blending logic needed.
- **"BGM"**: turned out to mean the *visual*, not a second audio layer. No audio ducking/mixing work required — scope stays audio-simple.
- **Video visual**: flexible — must support both a single static image (today's behavior) and swapping an image per song. This is new work in Stage 4.

## 4. What's reusable vs. new

| Capability | Status |
|---|---|
| Crossfade merge, loudness normalization, MP3 encoding | Reuse as-is (Stage 2/3) |
| YouTube description/timestamp generation | Reuse, but feed it real video titles instead of filenames |
| Static-image video rendering | Reuse as-is (single-image mode) |
| Per-track image swap in video | **New** — Stage 4 needs a timed-image-sequence mode |
| Fetching audio from a YouTube URL | **New** — no downloader exists in the codebase today, despite the `youtube.py` filename |
| Ordering by "the order I listed them" instead of shuffle/natural-sort | **New default**, but trivial — reuse ingest's ordering scaffold |

## 5. New component: download stage

- Add a **new external dependency: `yt-dlp`**, invoked as a subprocess binary — same pattern as FFmpeg (Python orchestrates, external binary does the work; no pip audio libraries). This preserves ADR-003's "FFmpeg abstraction" philosophy rather than breaking it.
- New module pair mirroring `ffmpeg/`: `soundweave/ytdlp/executor.py` + `commands.py` (build/run `yt-dlp` commands, parse JSON metadata).
- New stage `soundweave/stages/download.py` (Stage 0, runs before ingest/merge):
  - Input: ordered list of URLs.
  - For each URL: fetch metadata (title, uploader, duration, video ID) + download best-audio-only stream, extract to a normalized format (e.g. `.m4a`/`.wav`) into a working directory.
  - Cache downloads by video ID under a cache dir (e.g. `.cache/youtube/<id>.*`) so re-runs of a mashup (tweaking crossfade or images) don't re-download.
  - Failure handling: a single bad/unavailable URL should log a warning and skip, not abort the whole run (mirrors existing "skip corrupted file" behavior in ingest) — but since the user explicitly curated 10 songs, consider making this configurable (`--strict` to abort instead of skip).
  - Downloaded tracks feed into the *existing* `AudioTrack` dataclass, extended with optional `source_url` / `video_title` / `uploader` fields so the manifest and description generator can use real titles.

## 6. New CLI surface

Follow the precedent already set by the `loop` subcommand (a dedicated subcommand with its own config dataclass), rather than overloading `--input`:

```bash
soundweave mashup --urls urls.txt --output output --image cover.png
soundweave mashup --urls urls.txt --output output --images covers/   # per-track swap
soundweave mashup --urls urls.txt --output output                   # audio only
```

- `urls.txt` format matches the existing `order.txt` convention (one entry per line, `#` comments, blank lines ignored) for consistency.
- New `MashupConfig` dataclass (parallel to `LoopConfig`), not a bolt-on to `PipelineConfig`, since sourcing model (URLs vs. directory) genuinely differs.
- Default ordering = the order URLs are listed (no shuffle) — opposite of the game-OST pipeline's default, because a hand-picked 10-song list has an intentional order. `--shuffle` available as an opt-in override.

## 7. Video stage extension (per-track images)

- `--image <path>`: unchanged, single static image for full duration.
- `--images <dir>`: new — directory of images (one per track, matched by order or filename prefix). Video stage builds a timed sequence: each image holds for its track's duration (using the same actual-duration measurements already computed for timestamps), crossfading or hard-cutting at track boundaries.
- If `--images` has fewer images than tracks, error at pre-flight (explicit is better than silently reusing/looping) rather than degrading silently.

## 8. Out of scope for v1

- Downloading full videos / using YouTube video (not just audio) content.
- Separate instrumental/background audio track mixed under the songs (ruled out in discussion).
- Short-clip/snippet mashups (true DJ-style overlapping mashup) — only full-song crossfade for v1.
- Automatic copyright/Content-ID risk assessment. **Flagging as a real risk, not a feature**: downloading and re-uploading commercial copyrighted music to YouTube will very likely trigger Content ID claims (muting/monetization redirect, not necessarily a strike, but worth knowing going in). This is a usage risk for the user, not something the tool should try to solve — recommend treating outputs as personal-use/unlisted unless the user has rights to the material.
- Resumable/partial-failure re-runs (nice-to-have, not blocking).

## 9. Housekeeping (done)

- **Lofi scope dropped entirely.** `SPECIFICATION.md`, `TESTING_GUIDE.md`, and `docs/PIPELINE_CONTRACT.md` described a lofi-processing stage (texture/drums mixing, EQ, compression) that no longer exists in code. Rather than reconcile them, they were deleted — lofi is not a direction this project is pursuing; the scope is strictly stitching tracks together (crossfade/loudnorm/encode) plus optional video. `docs/ARCHITECTURE.md`/`docs/DEBUGGING.md` were trimmed to match reality instead of deleted, since most of their content is still accurate. See `CLAUDE.md`'s "Non-goals" section.
- `.gitignore` now uses a `test_*/` glob instead of enumerating specific test-output directories.
- The `loop` subcommand work-in-progress has been committed (it was already complete, just uncommitted).

## 10. Phased plan

**Phase 1 — MVP (audio only)**
- `yt-dlp` download stage + `MashupConfig` + `mashup` subcommand.
- Reuse merge/encode stages unchanged.
- Output: merged MP3/WAV + description with real track titles. No video yet.

**Phase 2 — Video**
- Single static image mode (thin wrapper around existing `video_stage`).
- Per-track image swap mode (new timed-sequence logic).

**Phase 3 — Polish**
- Download caching by video ID.
- `--strict` vs. skip-on-failure behavior for unavailable videos.
- Manifest fields for source URLs/titles/uploaders (audit trail).

**Alongside / before Phase 1**: doc reconciliation (Section 9).

## 11. Decisions

- **Crossfade default for `mashup`: 4.5s (`--fade-ms 4500`)**. Verified by ear against a 4-track local sample (see `test_crossfade_4500/`) — reads as a clean song-to-song transition rather than a DJ-style overlap. Still overridable via `--fade-ms`.

## 12. Open questions for the user

- Should failed/unavailable URLs abort the run or just be skipped with a warning (given only 10 curated songs, a silent skip changes the mashup meaningfully)?
