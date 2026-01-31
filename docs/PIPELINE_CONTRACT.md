# Pipeline Stage Contracts

This document defines the interface contract for each pipeline stage. These contracts ensure stages can be tested independently and composed together.

## Overview

Each stage is a **pure function** with this general contract:

```python
def stage_name(
    inputs: <stage-specific-type>,
    config: PipelineConfig,
    logger: logging.Logger
) -> <stage-specific-output>:
    """
    Stage description.

    Args:
        inputs: What this stage needs (from previous stage or config)
        config: Immutable pipeline configuration
        logger: Logger instance for progress/errors

    Returns:
        What this stage produces (for next stage)

    Raises:
        ValidationError: Invalid inputs detected
        ProcessingError: FFmpeg or processing failed
    """
```

## Stage 1: Ingest

### Purpose
Discover audio files in input directory and order them.

### Function Signature

```python
def ingest_stage(
    config: PipelineConfig,
    logger: logging.Logger
) -> List[AudioTrack]:
    """Discover and order audio tracks."""
```

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `PipelineConfig` | Contains `input_dir` to scan |
| `logger` | `logging.Logger` | For logging progress |

### Outputs

**Returns**: `List[AudioTrack]`

```python
@dataclass
class AudioTrack:
    path: Path              # Full path to audio file
    filename: str           # Just the filename (for display)
    duration_s: float       # Duration in seconds
    sample_rate: int        # Sample rate (e.g., 44100)
    channels: int           # Number of channels (1=mono, 2=stereo)
    codec: str              # Codec name (e.g., "mp3", "wav")
```

### Behavior

1. **Scan input directory** for supported audio files:
   - Extensions: `.mp3`, `.wav`, `.m4a`, `.flac`, `.mpeg`
   - Top-level only (no subdirectories)

2. **Determine order**:
   - If `order.txt` exists: Use specified order
     - Must list ALL files (error if mismatch)
     - Duplicates allowed (file can appear multiple times)
     - Comments (`#`) and blank lines ignored
   - If no `order.txt`: Natural sort by filename (case-insensitive)

3. **Probe each file** using `ffprobe`:
   - Extract duration, sample rate, channels, codec
   - Log warning if file is corrupted/unreadable

4. **Return ordered list** of AudioTrack objects

### Errors

| Error Type | Condition | Exit Code |
|------------|-----------|-----------|
| `ValidationError` | No audio files found | 1 |
| `ValidationError` | order.txt lists missing file | 1 |
| `ValidationError` | order.txt doesn't list all files | 1 |
| `ProcessingError` | ffprobe fails on file | 2 |

### Example

```python
config = PipelineConfig(input_dir=Path("input"), output_dir=Path("output"))
logger = setup_logger(Path("test.log"))

tracks = ingest_stage(config, logger)

# tracks = [
#     AudioTrack(path=Path("input/track1.mp3"), filename="track1.mp3", duration_s=150.5, ...),
#     AudioTrack(path=Path("input/track2.mp3"), filename="track2.mp3", duration_s=180.3, ...),
# ]
```

---

## Stage 2: Merge

### Purpose
Merge multiple audio tracks into a single file with crossfades.

### Function Signature

```python
def merge_stage(
    tracks: List[AudioTrack],
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Merge tracks with crossfades."""
```

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| `tracks` | `List[AudioTrack]` | Ordered list from Stage 1 |
| `config` | `PipelineConfig` | Contains `fade_ms`, `output_dir` |
| `logger` | `logging.Logger` | For logging progress |

### Outputs

**Returns**: `Path` to `merged_clean.wav`

**Output format**:
- Sample rate: 48kHz
- Bit depth: 16-bit PCM
- Channels: Stereo (2)
- Format: WAV

### Behavior

1. **Calculate crossfade durations** for each track pair:
   - Default: `config.fade_ms` milliseconds
   - **Short track handling**: If crossfade > 50% of track duration, reduce to 50%
   - Minimum crossfade: 1 second (1000ms)

2. **Normalize loudness** for each track:
   - Target: -20 LUFS
   - True Peak: -1.5 dBTP
   - Loudness Range: 11 LU
   - Applied BEFORE crossfading

3. **Build FFmpeg filter graph**:
   - Loudness normalization for each input: `loudnorm=I=-20:TP=-1.5:LRA=11`
   - Chain crossfades: `acrossfade=d=<duration>:c1=tri:c2=tri`
   - Triangular curves for smooth transitions

4. **Execute FFmpeg** to create merged_clean.wav

5. **Return path** to output file

### Special Cases

| Case | Behavior |
|------|----------|
| 1 track | No crossfade, just normalize and convert to 48kHz/16-bit |
| 0 tracks | Raise `ValidationError` (should never happen after Stage 1) |
| Very short track | Reduce crossfade to 50% of duration, minimum 1s |

### Errors

| Error Type | Condition | Exit Code |
|------------|-----------|-----------|
| `ValidationError` | Empty track list | 1 |
| `ProcessingError` | FFmpeg merge fails | 2 |
| `OutputError` | Can't write output file | 3 |

### Example

```python
tracks = [
    AudioTrack(path=Path("track1.mp3"), duration_s=30, ...),
    AudioTrack(path=Path("track2.mp3"), duration_s=45, ...)
]
config = PipelineConfig(
    input_dir=Path("input"),
    output_dir=Path("output"),
    fade_ms=15000  # 15 second crossfades
)

merged_path = merge_stage(tracks, config, logger)
# merged_path = Path("output/merged_clean.wav")

# Total duration = 30 + 45 - 15 = 60 seconds (one 15s crossfade)
```

---

## Stage 3: Lofi

### Purpose
Apply lofi effects to merged audio (texture, drums, EQ, compression).

### Function Signature

```python
def lofi_stage(
    input_wav: Path,
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Apply lofi transformation."""
```

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| `input_wav` | `Path` | Path to merged_clean.wav from Stage 2 |
| `config` | `PipelineConfig` | Contains texture, drums, EQ, gains |
| `logger` | `logging.Logger` | For logging progress |

### Outputs

**Returns**: `Path` to `merged_lofi.wav`

**Also creates**: `merged_lofi.mp3` (320kbps CBR)

**Output format** (WAV):
- Sample rate: 48kHz (same as input)
- Bit depth: 16-bit PCM
- Channels: Stereo (2)
- Format: WAV

**Output format** (MP3):
- Bitrate: 320kbps CBR
- Sample rate: 48kHz
- Channels: Stereo (2)
- Format: MP3

### Behavior

1. **Mix texture** (if `config.texture` provided):
   - Loop texture audio: `aloop=loop=-1`
   - Gain: `config.texture_gain_db` (default: -26dB)
   - Mix with music: `amix=inputs=2`

2. **Mix drums** (if `config.drums` provided):
   - Loop drums audio: `aloop=loop=-1`
   - Delay start: `adelay` by `config.drums_start_s` seconds
   - Gain: `config.drums_gain_db` (default: -22dB)
   - Mix with music: `amix=inputs=2`

3. **Apply EQ**:
   - Highpass filter: `config.highpass_hz` (default: 35Hz) - removes sub-bass
   - Lowpass filter: `config.lowpass_hz` (default: 11kHz) - removes high frequencies

4. **Apply dynamics**:
   - Compressor: Ratio 3:1, threshold -18dB, attack 5ms, release 50ms
   - Limiter: Ceiling -1dB, attack 5ms, release 50ms

5. **Output WAV** file (lossless)

6. **Encode MP3** at 320kbps CBR

7. **Return path** to WAV file

### Special Cases

| Case | Behavior |
|------|----------|
| No texture/drums | Skip mixing, just apply EQ + dynamics |
| Texture shorter than music | Loop texture automatically with `aloop` |
| Drums shorter than music | Loop drums automatically with `aloop` |

### Errors

| Error Type | Condition | Exit Code |
|------------|-----------|-----------|
| `ValidationError` | Texture file doesn't exist | 1 |
| `ValidationError` | Drums file doesn't exist | 1 |
| `ProcessingError` | FFmpeg lofi processing fails | 2 |
| `ProcessingError` | MP3 encoding fails | 2 |
| `OutputError` | Can't write output files | 3 |

### Example

```python
input_wav = Path("output/merged_clean.wav")
config = PipelineConfig(
    input_dir=Path("input"),
    output_dir=Path("output"),
    texture=Path("assets/rain.wav"),
    drums=Path("assets/drums.wav"),
    texture_gain_db=-26.0,
    drums_gain_db=-22.0,
    drums_start_s=20.0,
    highpass_hz=35,
    lowpass_hz=11000
)

lofi_path = lofi_stage(input_wav, config, logger)
# lofi_path = Path("output/merged_lofi.wav")
# Also creates: output/merged_lofi.mp3
```

---

## Stage 4: Video

### Purpose
Render static video with cover image and audio.

### Function Signature

```python
def video_stage(
    audio_path: Path,
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Render static video with cover image."""
```

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| `audio_path` | `Path` | Path to final audio (merged_lofi.wav or merged_clean.wav) |
| `config` | `PipelineConfig` | Contains `cover_image`, `output_dir` |
| `logger` | `logging.Logger` | For logging progress |

### Outputs

**Returns**: `Path` to `final_video.mp4`

**Also creates**: `thumbnail.{png,jpg}` (copy of cover image)

**Output format** (Video):
- Resolution: 1920x1080
- Frame rate: 1fps (minimal for static image)
- Video codec: H.264 (yuv420p, high profile)
- Audio codec: AAC (192kbps)
- Duration: Exactly matches audio duration

### Behavior

1. **Probe audio duration** using ffprobe

2. **Scale/pad cover image** to 1920x1080:
   - Preserve aspect ratio
   - Add letterboxing (black bars) if not 16:9
   - Center image

3. **Render video**:
   - Loop cover image: `loop=1`
   - Combine with audio
   - Set duration to match audio exactly
   - Encode with H.264 + AAC

4. **Copy cover image** to output as `thumbnail.{ext}`
   - Extension matches cover image (.png or .jpg)

5. **Return path** to video file

### Special Cases

| Case | Behavior |
|------|----------|
| No cover image | Return None (stage skipped) |
| Cover not 16:9 | Letterbox with black bars |
| Very long audio (60+ min) | May take 5-10 minutes to render |

### Errors

| Error Type | Condition | Exit Code |
|------------|-----------|-----------|
| `ValidationError` | Cover image doesn't exist | 1 |
| `ProcessingError` | FFmpeg video rendering fails | 2 |
| `OutputError` | Can't write video file | 3 |
| `OutputError` | Can't copy thumbnail | 3 |

### Example

```python
audio_path = Path("output/merged_lofi.wav")
config = PipelineConfig(
    input_dir=Path("input"),
    output_dir=Path("output"),
    cover_image=Path("assets/cover.png")
)

video_path = video_stage(audio_path, config, logger)
# video_path = Path("output/final_video.mp4")
# Also creates: output/thumbnail.png
```

---

## Pipeline Orchestration

The `Pipeline` class coordinates all stages:

```python
class Pipeline:
    def run(self) -> int:
        """Run all stages sequentially.

        Returns:
            Exit code (0=success, 1-3=error)
        """
        try:
            # Stage 1: Ingest
            tracks = ingest_stage(self.config, self.logger)

            # Stage 2: Merge
            merged = merge_stage(tracks, self.config, self.logger)

            # Stage 3: Lofi (optional)
            if not self.config.skip_lofi:
                lofi = lofi_stage(merged, self.config, self.logger)
                final_audio = lofi
            else:
                final_audio = merged

            # Stage 4: Video (optional)
            if self.config.cover_image:
                video = video_stage(final_audio, self.config, self.logger)

            # Write manifest
            self.manifest.write(self.config.output_dir / "manifest.json")

            return 0  # Success

        except ValidationError:
            return 1
        except ProcessingError:
            return 2
        except OutputError:
            return 3
```

## Data Flow

```
PipelineConfig ──────┐
                     ├──▶ ingest_stage() ──▶ List[AudioTrack]
                     │                             │
                     │                             ▼
                     ├──▶ merge_stage() ◀───────────┘
                     │         │
                     │         ▼
                     │    merged_clean.wav
                     │         │
                     ├──▶ lofi_stage() ◀──────────────┘
                     │         │
                     │         ▼
                     │    merged_lofi.wav + merged_lofi.mp3
                     │         │
                     └──▶ video_stage() ◀─────────────┘
                               │
                               ▼
                          final_video.mp4 + thumbnail.{png,jpg}
```

## Testing Contracts

Each stage should be testable independently:

```python
# Test Stage 1
def test_ingest_stage():
    config = PipelineConfig(input_dir=test_dir, output_dir=tmp_path)
    logger = setup_logger(tmp_path / "test.log")

    tracks = ingest_stage(config, logger)

    assert len(tracks) == 3
    assert tracks[0].filename == "track1.mp3"
    assert tracks[0].duration_s > 0


# Test Stage 2
def test_merge_stage():
    tracks = [create_test_track("t1.mp3"), create_test_track("t2.mp3")]
    config = PipelineConfig(input_dir=test_dir, output_dir=tmp_path, fade_ms=5000)
    logger = setup_logger(tmp_path / "test.log")

    merged = merge_stage(tracks, config, logger)

    assert merged.exists()
    assert merged.name == "merged_clean.wav"
    # Verify duration = sum(durations) - crossfade
```

## Contract Violations

If a stage violates its contract (e.g., returns wrong type, raises unexpected exception), this is a **bug** and should be fixed.

Examples:
- ❌ Stage returns `None` instead of `Path`
- ❌ Stage raises `KeyError` instead of `ValidationError`
- ❌ Stage mutates `config` (should be immutable)
- ❌ Stage calls next stage directly (should return and let orchestrator call)

## Summary

| Stage | Input | Output | Optional | Errors |
|-------|-------|--------|----------|--------|
| 1. Ingest | `PipelineConfig` | `List[AudioTrack]` | No | Validation, Processing |
| 2. Merge | `List[AudioTrack]` | `Path` (WAV) | No | Validation, Processing, Output |
| 3. Lofi | `Path` (WAV) | `Path` (WAV + MP3) | Yes (--skip-lofi) | Validation, Processing, Output |
| 4. Video | `Path` (audio) | `Path` (MP4 + thumbnail) | Yes (no --cover) | Validation, Processing, Output |

All stages:
- Accept `config: PipelineConfig` and `logger: Logger`
- Are pure functions (no side effects besides file I/O)
- Log progress to logger
- Raise typed exceptions (`ValidationError`, `ProcessingError`, `OutputError`)
- Can be tested independently

---

**See also**:
- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system design
- [ADR 001: Pipeline Architecture](ADRs/001-pipeline-architecture.md) - Why this design
