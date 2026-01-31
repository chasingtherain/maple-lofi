# Maple Lofi Project — Project Specification (v2)

## 1. Project Overview

The Maple Lofi Project is a local, agent-driven audio + video production pipeline that converts multiple MapleStory background music tracks into a single, YouTube-ready lofi longplay.

The system is designed to be:

- **hands-free** (drop files → run one command)
- **deterministic** (same inputs + settings → same outputs)
- **auditable** (every run produces logs and manifests)
- **educational** (architecture and decisions are clearly documented)

This project prioritizes engineering clarity, reliability, and repeatability over novelty or full automation of music creation.

---

## 2. End Output (Primary Artifact)

A single command produces:

**🎧 Lofi-enhanced longform audio**
- `merged_clean.wav` (48kHz, 16-bit PCM master)
- `merged_lofi.wav` (48kHz, 16-bit PCM with lofi processing)
- `merged_lofi.mp3` (320kbps CBR distribution)

**🎥 YouTube-uploadable video** (if `--cover` provided)
- Static image persisted for full duration
- 1920x1080, H.264 video + AAC audio, 1fps
- Duration exactly matches audio length

**🖼️ Static image**
- Provided as input (`--cover`)
- Copied to output as `thumbnail.png/jpg` for convenience

**📄 Run documentation**
- `run_log.txt` (human-readable)
- `manifest.json` (machine-readable, see schema below)

---

## 3. Explicit Pipeline Stages

The agent must implement the pipeline using clear, explicit stages, each with defined inputs and outputs.

### **Stage 1 — Ingest**

**Purpose**: Discover and order audio files

**Behavior**:
1. Scan `--input` directory for audio files (top-level only, non-recursive)
2. Supported formats: `.mp3`, `.wav`, `.m4a`, `.flac`
3. Determine playback order:
   - If `order.txt` exists in input directory, use it
   - Otherwise, sort by filename (natural sort, case-insensitive)
4. Validate files:
   - Log warning and skip corrupted/unreadable files
   - Continue pipeline with remaining valid files
   - Error if zero valid files found
5. Log resolved order

**order.txt format**:
```
ellinia.mp3
henesys.wav
kerning_city.mp3
ellinia.mp3  # Duplicates allowed - this will play ellinia twice
# kerning_city.mp3  # Commented out - won't be processed
```

**Rules**:
- One filename per line (with extension)
- Just the filename, not full paths
- Lines starting with `#` are ignored (no inline comments)
- Blank lines are ignored
- **If order.txt exists**: It MUST list all audio files in the input directory
  - Missing files in order.txt → Error and abort
  - Extra files in order.txt (not in input dir) → Error and abort
  - This ensures explicit, intentional ordering
- **Duplicates allowed**: Same file can be listed multiple times (will be processed each time)

**Output**: Ordered list of valid audio tracks

---

### **Stage 2 — Merge**

**Purpose**: Combine tracks into seamless longform audio

**Behavior**:
1. **Normalize loudness** for each track:
   - Target: -20 LUFS (standard streaming level)
   - True Peak: -1.5 dBTP
   - Loudness Range: 11 LU
   - Ensures consistent volume across all tracks
2. Resample all tracks to 48kHz, 16-bit PCM (if needed)
3. Apply crossfade between consecutive tracks (default: 15s, configurable via `--fade-ms`)
4. **Short track handling**:
   - If track duration < crossfade duration:
     - Reduce crossfade to 50% of track duration
     - Log the adjustment
   - Minimum effective crossfade: 1 second
5. No hard cuts or dead air between tracks
6. Output single merged file

**Output**: `merged_clean.wav` (48kHz, 16-bit PCM, loudness-normalized)

---

### **Stage 3 — Lofi Transformation**

**Purpose**: Apply lofi aesthetic to merged audio

**Default behavior**: Runs by default, but all lofi assets are optional

**Processing steps**:
1. **Optional texture overlay** (if `--texture` provided):
   - Loop texture file seamlessly for full duration
   - Mix at specified gain (default: -26dB)
2. **Optional drum loop** (if `--drums` provided):
   - Loop drums seamlessly for full duration
   - Start at specified time (default: 0s)
   - Mix at specified gain (default: -22dB)
3. **Tone shaping** (always applied):
   - High-pass filter at 35Hz (remove sub-bass rumble)
   - Low-pass filter at 11kHz (warm, muffled character)
4. **Gentle compression** (always applied):
   - Ratio: 3:1
   - Threshold: -18dB
   - Attack: 5ms
   - Release: 50ms
   - Makeup gain: auto
5. **Peak limiting** (always applied):
   - Limit at -1dB to prevent clipping
   - Log warning if clipping detected

**Skip entire stage**: Use `--skip-lofi` flag

**Error handling**:
- If asset path specified but file missing: error and abort
- If no assets specified: apply EQ + compression only

**Outputs**:
- `merged_lofi.wav` (48kHz, 16-bit PCM)
- `merged_lofi.mp3` (320kbps CBR)

---

### **Stage 4 — Video Render**

**Purpose**: Combine final audio with static image for YouTube

**Behavior**:
1. Scale/pad cover image to 1920x1080:
   - Preserve aspect ratio (never stretch)
   - Letterbox with black bars if not 16:9
2. Render static video:
   - Frame rate: 1fps (minimal file size)
   - Video codec: H.264 (yuv420p, high profile)
   - Audio codec: AAC (192kbps)
3. Duration matches audio exactly
4. Copy cover image to output as `thumbnail.png/jpg`

**Skip entire stage**: Omit `--cover` flag

**Outputs**:
- `final_video.mp4`
- `thumbnail.png` or `thumbnail.jpg`

---

## 4. Inputs (v2)

**Required**:
- `input/` — directory containing audio files (`.mp3`, `.wav`, `.m4a`, `.flac`)

**Optional**:
- `input/order.txt` — custom playback order
- `--cover <path>` — cover image for video (any resolution, will be scaled)
- `--texture <path>` — ambient texture audio (e.g., `assets/rain.wav`)
- `--drums <path>` — drum loop audio (e.g., `assets/drums.wav`)

---

## 5. Outputs (v2)

**In `output/` directory**:

**Audio**:
- `merged_clean.wav` (pre-lofi master)
- `merged_lofi.wav` (lofi-processed master)
- `merged_lofi.mp3` (distribution format)

**Video** (if `--cover` provided):
- `final_video.mp4`
- `thumbnail.png` or `thumbnail.jpg`

**Documentation**:
- `run_log.txt` (human-readable log)
- `manifest.json` (machine-readable metadata)

**Partial outputs retained on failure** (for debugging)

---

## 6. CLI Contract (Single Command)

### **Required Flags**
```bash
--input <dir>    # Directory containing input audio files
--output <dir>   # Directory for output files
```

### **Optional Flags (with defaults)**
```bash
# Lofi Processing
--skip-lofi                  # Skip lofi stage entirely (default: false)
--texture <path>             # Ambient texture file (default: none)
--texture-gain <db>          # Texture volume in dB (default: -26)
--drums <path>               # Drum loop file (default: none)
--drums-gain <db>            # Drums volume in dB (default: -22)
--drums-start <seconds>      # Drums start delay (default: 0)
--highpass <hz>              # High-pass filter frequency (default: 35)
--lowpass <hz>               # Low-pass filter frequency (default: 11000)

# Merging
--fade-ms <milliseconds>     # Crossfade duration (default: 15000)

# Video
--cover <path>               # Cover image (default: none, skips video)
```

### **Examples**

**Minimal (audio only, with lofi)**:
```bash
python -m maple_lofi --input input --output output
```

**Full (with video and custom assets)**:
```bash
python -m maple_lofi \
  --input input \
  --output output \
  --cover assets/cover.png \
  --texture assets/rain.wav --texture-gain -26 \
  --drums assets/drums.wav --drums-gain -22 --drums-start 20 \
  --fade-ms 15000
```

**Skip lofi (just merge tracks)**:
```bash
python -m maple_lofi --input input --output output --skip-lofi
```

**Audio with lofi, no video**:
```bash
python -m maple_lofi \
  --input input \
  --output output \
  --texture assets/rain.wav \
  --drums assets/drums.wav --drums-start 20
```

---

## 7. Technical Constraints

**Language**: Python 3.10+

**Execution**: Local CLI only (no cloud services)

**Audio + video engine**: FFmpeg 4.4+ (verify on startup)

**Orchestration**: `subprocess` or lightweight wrappers (Python orchestrates, FFmpeg processes)

**Dependencies**: Managed via `pyproject.toml`

**Must handle**: Long audio (60+ minutes, up to 4 hours with warning)

**Must be auditable**: Every run produces logs and manifests

---

## 8. Technical Defaults & Rationale

### **Audio Formats**
- **Sample rate**: 48kHz (YouTube's native rate, better compatibility than 44.1kHz)
- **Bit depth**: 16-bit (sufficient quality, smaller files than 24-bit)
- **MP3 encoding**: 320kbps CBR (highest standard quality, simple)

### **Crossfade**
- **Default**: 15 seconds (smooth transitions, not too aggressive)
- **Short track handling**: Reduce to 50% of track duration (prevents overlap issues)

### **Lofi Filters**
- **High-pass @ 35Hz**: Remove sub-bass rumble and DC offset
- **Low-pass @ 11kHz**: Warm, muffled lofi character (mimics vinyl/tape)
- **Texture gain**: -26dB (subtle ambient layer, not overpowering)
- **Drums gain**: -22dB (present but not dominant)

### **Loudness Normalization**
- **Target**: -20 LUFS (standard streaming level for platforms like YouTube, Spotify)
- **True Peak**: -1.5 dBTP (prevents clipping on all playback systems)
- **Loudness Range**: 11 LU (preserves dynamics while ensuring consistency)
- **Rationale**: Ensures consistent perceived volume across all tracks in the merge

### **Compression**
- **Ratio 3:1**: Gentle compression, preserves dynamics
- **Threshold -18dB**: Catches peaks without over-compressing
- **Fast attack/medium release**: Transparent, musical compression

### **Video**
- **1920x1080**: YouTube standard HD
- **1fps**: Static image, minimal file size
- **H.264 + AAC**: Universal YouTube compatibility

---

## 9. Manifest Schema

**File**: `output/manifest.json`

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-01T14:30:00Z",
  "python_version": "3.10.12",
  "ffmpeg_version": "4.4.2",

  "inputs": {
    "audio_files": [
      {"filename": "ellinia.mp3", "duration_s": 180.5, "sample_rate": 44100},
      {"filename": "henesys.wav", "duration_s": 240.0, "sample_rate": 48000}
    ],
    "order_source": "order.txt",
    "cover_image": "assets/cover.png",
    "texture": "assets/rain.wav",
    "drums": "assets/drums.wav"
  },

  "parameters": {
    "fade_ms": 15000,
    "highpass_hz": 35,
    "lowpass_hz": 11000,
    "texture_gain_db": -26,
    "drums_gain_db": -22,
    "drums_start_s": 20,
    "skip_lofi": false
  },

  "outputs": {
    "merged_clean": {
      "path": "output/merged_clean.wav",
      "duration_s": 3600.5,
      "sample_rate": 48000,
      "channels": 2,
      "file_size_mb": 480.2,
      "sha256": "abc123..."
    },
    "merged_lofi_wav": {
      "path": "output/merged_lofi.wav",
      "duration_s": 3600.5,
      "sample_rate": 48000,
      "channels": 2,
      "file_size_mb": 480.2,
      "sha256": "def456..."
    },
    "merged_lofi_mp3": {
      "path": "output/merged_lofi.mp3",
      "duration_s": 3600.5,
      "bitrate_kbps": 320,
      "file_size_mb": 82.1,
      "sha256": "ghi789..."
    },
    "final_video": {
      "path": "output/final_video.mp4",
      "duration_s": 3600.5,
      "resolution": "1920x1080",
      "fps": 1,
      "file_size_mb": 95.3,
      "sha256": "jkl012..."
    }
  },

  "stages": [
    {"name": "ingest", "status": "success", "duration_s": 0.3, "tracks_found": 12},
    {"name": "merge", "status": "success", "duration_s": 42.1, "crossfades_applied": 11},
    {"name": "lofi", "status": "success", "duration_s": 180.5},
    {"name": "video", "status": "success", "duration_s": 15.2}
  ],

  "ffmpeg_commands": [
    "ffmpeg -i input/ellinia.mp3 -i input/henesys.wav ...",
    "ffmpeg -i merged_clean.wav -i assets/rain.wav ..."
  ],

  "warnings": [
    "Track 'short_jingle.wav' duration (8s) < crossfade (15s), reduced to 4s"
  ],

  "errors": []
}
```

---

## 10. Error Handling & Exit Codes

### **Exit Codes**
- `0`: Success (all stages completed)
- `1`: Input validation error (no files, missing required assets)
- `2`: Processing error (FFmpeg failure, corruption)
- `3`: Output error (disk full, permissions)

### **Error Behaviors**

| Scenario | Behavior |
|----------|----------|
| Empty input directory | Error immediately, exit code 1 |
| Corrupted audio file | Log warning, skip file, continue |
| Zero valid audio files | Error, exit code 1 |
| Missing specified asset (e.g., `--texture missing.wav`) | Error, exit code 1 |
| FFmpeg command fails | Log error, keep partial outputs, exit code 2 |
| Disk space insufficient | Pre-flight check fails, exit code 3 |
| Duration >4 hours | Log warning, continue processing |
| Clipping detected (despite limiter) | Log warning, continue (shouldn't happen) |

### **Pre-flight Checks**
- Python version >= 3.10
- FFmpeg version >= 4.4
- Input directory exists and readable
- Estimated disk space available (input size × 3)
- Output directory writable (create if missing)

---

## 11. Design Principles

- Prefer simple, deterministic solutions over clever heuristics
- Separate decision logic from execution
- Python orchestrates; FFmpeg processes
- Avoid unnecessary frameworks or abstractions
- Optimize for a clean, understandable v1
- Make sensible defaults; support override via flags
- Log everything; make debugging straightforward

---

## 12. Learning Artifacts (Required Deliverables)

To maximize learning, the agent must generate the following documentation as part of the project.

### **12.1 Architecture & Decisions**

**`docs/ARCHITECTURE.md`**
- Written as senior engineer → junior engineer
- Explains system layout, flow, and mental models
- Why this structure? Why these stages?

**`docs/ADRs/`** (Architecture Decision Records)
- `001-ffmpeg-vs-python-dsp.md` — Why FFmpeg over pure Python audio libs
- `002-cli-flags-vs-config-files.md` — Why CLI-first design
- `003-manifest-logging-rationale.md` — Why JSON manifests + text logs
- `004-audio-format-defaults.md` — Why 48kHz, 16-bit, 320kbps

### **12.2 Debugging & Observability**

**`docs/DEBUGGING.md`**
- Common failure modes (missing files, FFmpeg errors, corruption)
- How to reproduce issues
- How to inspect intermediate outputs (`merged_clean.wav`, etc.)
- How to read logs and manifests
- How to test individual pipeline stages

### **12.3 Testing & Validation**

**`docs/TEST_PLAN.md`**
- Minimal automated tests:
  - Ordering logic (with/without `order.txt`, natural sort)
  - Short-track crossfade handling
  - Manifest generation and schema validation
  - Video duration == audio duration
  - Clipping detection
- Manual validation checklist

**`scripts/smoke_test.sh`**
- Quick end-to-end test with sample assets

### **12.4 Pipeline Contracts**

**`docs/PIPELINE_CONTRACT.md`**
- Inputs/outputs per stage
- Error behavior per stage
- Invariants guaranteed by each stage:
  - Ingest: ordered list, valid files only
  - Merge: 48kHz, 16-bit, no gaps
  - Lofi: same duration as input, no clipping
  - Video: duration matches audio exactly

### **12.5 Defaults & Rationale**

**`docs/DEFAULTS.md`**
- Why 15s crossfades? (smooth, not too long)
- Why these gains? (-26dB texture, -22dB drums)
- Why these filters? (35Hz HP, 11kHz LP)
- Why MP4 H.264 + AAC? (YouTube compatibility)
- Why 48kHz? (YouTube native, video standard)

### **12.6 Quality Evaluation**

**`docs/QUALITY_CHECKLIST.md`**
- What to listen for:
  - Smooth crossfades (no hard cuts)
  - No clipping or distortion
  - Balanced lofi mix (music still audible under texture/drums)
  - Consistent volume throughout
- How to sample long tracks efficiently (listen at 0:00, transitions, random spots)
- What constitutes "good enough" for publish

### **12.7 Sample Assets**

**`sample_assets/`**
- Non-copyrighted audio samples (Creative Commons or public domain)
- Placeholder cover image
- Sample `rain.wav` and `drums.wav`
- `README.md` explaining how to swap in real assets

### **12.8 Learning Path**

**`docs/LEARNING_PATH.md`**
- What to learn next to extend this project:
  - FFmpeg filters (advanced audio processing)
  - CLI design patterns (argparse, subcommands, config files)
  - Audio fundamentals (sample rates, bit depth, compression)
  - Python async for parallel processing
  - Automated loudness normalization (LUFS)

### **12.9 Run Reflection**

**`docs/RUN_POSTMORTEM_TEMPLATE.md`**
- Short reflection template for each iteration:
  - What worked well?
  - What didn't sound right?
  - What would you tweak next time?
  - What did you learn?

---

## 13. What Not to Do (Constraints)

- ❌ No cloud services or streaming APIs
- ❌ No web apps or UI frameworks
- ❌ No per-segment loudness adjustments (simple per-track normalization is sufficient)
- ❌ No monetization or copyright enforcement logic
- ❌ No animated video (static image only for v1)
- ❌ No real-time processing or streaming
- ❌ No machine learning or AI-based audio enhancement

---

## 14. Definition of Success

A successful v1 means:

✅ **One command produces**:
- Lofi-enhanced audio (WAV + MP3)
- YouTube-ready MP4 video (if cover provided)

✅ **Audio quality**:
- No clipping, no hard cuts, no dead air
- Smooth crossfades between tracks
- Balanced lofi mix (music still clear)

✅ **Video quality**:
- Video duration matches audio exactly
- 1920x1080, proper letterboxing
- Clean, professional-looking output

✅ **Documentation quality**:
- Logs + manifest clearly explain what happened
- Repo teaches a junior engineer why the system is built this way
- All ADRs and docs are clear and helpful

✅ **Reliability**:
- Same inputs + settings → same outputs (deterministic)
- Handles edge cases gracefully (short tracks, missing files)
- Clear error messages guide user to fix issues

---

## 15. Notes for Implementation

- If something is ambiguous, ask clarifying questions before implementing
- If trade-offs exist, default to **simplicity and determinism**
- Prioritize **working end-to-end** over perfect individual components
- **Log liberally** — every decision, every FFmpeg command, every warning
- **Test with real MapleStory music** (or similar loopable game OSTs)

---

**End of Specification**
