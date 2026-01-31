# Architecture Overview

## System Design

The Maple Lofi Pipeline is a **command-line audio/video processing pipeline** that transforms a collection of music tracks into a single, lofi-styled YouTube-ready video. It follows a **linear 4-stage architecture** with emphasis on:

- **Determinism**: Same inputs → same outputs (reproducible builds)
- **Auditability**: Full command logging + SHA256 checksums
- **Simplicity**: Stdlib-only dependencies, FFmpeg for all processing
- **Educational clarity**: Readable code, extensive documentation

## High-Level Data Flow

```
Input Directory          Pipeline Stages                    Output Directory
───────────────          ───────────────                    ────────────────

track1.mp3 ──┐
track2.mp3 ──┤──▶ [Stage 1: Ingest] ──▶ Track list (ordered, validated)
track3.mp3 ──┘           │
(order.txt)              │
                         ▼
                  [Stage 2: Merge] ──▶ merged_clean.wav (48kHz, 16-bit)
                         │               ↑
                         │               └─ Loudness normalized, crossfaded
                         ▼
rain.wav ────┐
drums.wav ───┤──▶ [Stage 3: Lofi] ──▶ merged_lofi.wav + merged_lofi.mp3
             │           │               ↑
             │           │               └─ EQ, compression, texture mixing
             ▼           ▼
cover.png ──▶ [Stage 4: Video] ──▶ final_video.mp4 + thumbnail.png
                         │               ↑
                         │               └─ 1920x1080, 1fps, AAC audio
                         ▼
                  manifest.json + run_log.txt
```

## Core Principles

### 1. Pure Functional Stages

Each stage is a **pure function** with clear inputs and outputs:

```python
def stage(inputs, config, logger) -> outputs:
    """
    - No side effects beyond creating output files
    - No global state
    - Reproducible given same inputs
    """
```

### 2. FFmpeg as Processing Engine

All audio/video operations use **FFmpeg subprocess calls**. No Python audio libraries (pydub, librosa, etc.).

**Why?**
- Battle-tested for production workloads
- Supports all audio formats natively
- Transferable skill (FFmpeg knowledge applies everywhere)
- Filter graphs are declarative and auditable

### 3. Configuration as Data

All pipeline parameters are captured in a single **`PipelineConfig` dataclass**:

```python
@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    fade_ms: int = 15000
    highpass_hz: int = 35
    # ... 10+ parameters
```

This config flows through all stages, ensuring consistency.

### 4. Dual Logging

- **`run_log.txt`**: Human-readable chronological log (console + file)
- **`manifest.json`**: Machine-readable structured output (SHA256, durations, commands)

Both are written to the output directory for every run.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                           │
│  (maple_lofi/cli.py, __main__.py)                          │
│                                                             │
│  • Parse arguments (argparse)                              │
│  • Run pre-flight validators                               │
│  • Build PipelineConfig                                    │
│  • Invoke Pipeline.run()                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline Orchestrator                    │
│  (maple_lofi/pipeline.py)                                  │
│                                                             │
│  class Pipeline:                                           │
│      def run() -> int:                                     │
│          1. Execute Stage 1: Ingest                        │
│          2. Execute Stage 2: Merge                         │
│          3. Execute Stage 3: Lofi (optional)              │
│          4. Execute Stage 4: Video (optional)             │
│          5. Write manifest.json                            │
│          6. Return exit code (0-3)                         │
│                                                             │
│  Exception Handling:                                        │
│  • ValidationError → exit 1                                │
│  • ProcessingError → exit 2                                │
│  • OutputError → exit 3                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Stage Modules                          │
│  (maple_lofi/stages/*.py)                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Stage 1: Ingest (ingest.py)                        │  │
│  │ • Discover audio files                              │  │
│  │ • Parse order.txt or natural sort                   │  │
│  │ • Probe metadata (duration, sample rate, channels) │  │
│  │ → Returns: List[AudioTrack]                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Stage 2: Merge (merge.py)                          │  │
│  │ • Calculate crossfade durations                     │  │
│  │ • Normalize loudness (-20 LUFS per track)          │  │
│  │ • Build FFmpeg filter graph (acrossfade)           │  │
│  │ → Returns: Path to merged_clean.wav                │  │
│  └─────────────────────────────────────────────────────┘  │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Stage 3: Lofi (lofi.py)                            │  │
│  │ • Mix texture (rain) at -26dB                       │  │
│  │ • Mix drums at -22dB (delayed start)                │  │
│  │ • Apply EQ (highpass 35Hz, lowpass 11kHz)          │  │
│  │ • Compress (3:1 ratio, -18dB threshold)            │  │
│  │ • Limit (-1dB ceiling)                              │  │
│  │ • Encode MP3 (320kbps CBR)                          │  │
│  │ → Returns: Path to merged_lofi.wav                 │  │
│  └─────────────────────────────────────────────────────┘  │
│                            ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Stage 4: Video (video.py)                          │  │
│  │ • Probe audio duration                              │  │
│  │ • Scale/pad cover to 1920x1080 (letterbox)         │  │
│  │ • Render video (1fps, H.264, AAC)                  │  │
│  │ • Copy cover as thumbnail                           │  │
│  │ → Returns: Path to final_video.mp4                 │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    FFmpeg Abstraction                       │
│  (maple_lofi/ffmpeg/*.py)                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ executor.py                                         │  │
│  │ • run_ffmpeg(command, logger, timeout)             │  │
│  │ • subprocess.run() wrapper                          │  │
│  │ • Log command + duration                            │  │
│  │ • Raise ProcessingError on failure                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ commands.py                                         │  │
│  │ • build_merge_command(tracks, durations)           │  │
│  │ • build_lofi_command(input, config)                │  │
│  │ • build_video_command(audio, cover, duration)      │  │
│  │ → Returns: List[str] (FFmpeg command)              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ probe.py                                            │  │
│  │ • probe_audio_file(path) → AudioMetadata           │  │
│  │ • Runs ffprobe, parses JSON                         │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Utilities & Logging                      │
│  (maple_lofi/utils/*.py, maple_lofi/logging/*.py)         │
│                                                             │
│  • validators.py: Pre-flight checks                        │
│  • natural_sort.py: Filename sorting                       │
│  • file_utils.py: SHA256, file size                        │
│  • logger.py: Dual logging setup                           │
│  • manifest.py: ManifestBuilder class                      │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Stage Independence

Each stage can **fail independently** without corrupting state:

- If Stage 2 fails → only partial output created, manifest records error
- If Stage 3 fails → `merged_clean.wav` still usable
- If Stage 4 fails → audio outputs still valid

### Optional Stages

Stages 3 and 4 are **optional** based on flags:

- `--skip-lofi`: Skip Stage 3 (merge only)
- No `--cover`: Skip Stage 4 (audio only)

This allows incremental testing and flexible workflows.

### Loudness Normalization

**Critical feature for consistent output quality.**

Applied in Stage 2 (merge) using FFmpeg's `loudnorm` filter:
- Target: -20 LUFS (standard streaming level)
- True Peak: -1.5 dBTP (headroom for encoding)
- Loudness Range: 11 LU (consistent dynamics)

Each track is normalized **before** crossfading, ensuring:
- No sudden volume jumps between tracks
- No clipping from hot input files
- Consistent perceived loudness throughout mix

### Error Handling Strategy

**Exit codes convey error type:**

- `0`: Success
- `1`: Validation error (bad inputs, missing FFmpeg, etc.)
- `2`: Processing error (FFmpeg failure, corrupted files)
- `3`: Output error (disk full, permissions)

**Manifest written even on error** for debugging.

### Manifest as Audit Log

The `manifest.json` contains:

1. **Run metadata**: ID, timestamp, FFmpeg version, platform
2. **Input tracking**: All input files with metadata
3. **Output tracking**: All output files with SHA256 + size
4. **Stage results**: Duration + status for each stage
5. **FFmpeg commands**: Every command executed (reproducibility)
6. **Warnings/errors**: All issues encountered

This makes the pipeline **fully auditable**.

## Performance Characteristics

### Processing Time

Dominated by FFmpeg operations:

- **Stage 1 (Ingest)**: O(n) file probes (~1s per file)
- **Stage 2 (Merge)**: O(n) audio processing (~0.5× real-time)
- **Stage 3 (Lofi)**: O(1) relative to merge (similar duration)
- **Stage 4 (Video)**: O(duration) at 1fps (~6 min for 60 min audio)

**Bottleneck**: Video rendering (Stage 4) for long audio.

### Memory Usage

**Minimal** - FFmpeg streams data, Python just orchestrates:

- Peak memory: ~100-200MB (Python process)
- FFmpeg uses ~200-500MB per operation
- No audio data loaded into Python memory

### Disk Usage

**Estimate**: 3× input size

- `merged_clean.wav`: ~10MB/min (48kHz, 16-bit)
- `merged_lofi.wav`: ~10MB/min (same format)
- `merged_lofi.mp3`: ~2.4MB/min (320kbps)
- `final_video.mp4`: ~0.5-1MB/min (1fps, H.264)

## Extension Points

The architecture supports these extensions without major refactoring:

### 1. Additional Stages

Add new stages between existing ones:

```python
# After merge, before lofi:
mastered = mastering_stage(merged_clean, config, logger)
```

### 2. Custom FFmpeg Filters

Modify `commands.py` to add filters:

```python
# Add reverb to lofi stage:
filter_parts.append("[lp]aecho=0.8:0.88:60:0.4[reverb]")
```

### 3. Alternative Output Formats

Add new output formats in Stage 3/4:

```python
# Export FLAC alongside MP3:
build_flac_command(merged_lofi_wav, output_flac_path)
```

### 4. Parallel Processing

For very long playlists, parallelize ingest probing:

```python
with ThreadPoolExecutor() as executor:
    metadata = executor.map(probe_audio_file, audio_files)
```

## Security Considerations

### Subprocess Injection

**Current**: Command arrays (not shell strings) prevent injection:

```python
# Safe:
subprocess.run(["ffmpeg", "-i", user_input])

# Unsafe (not used):
subprocess.run(f"ffmpeg -i {user_input}", shell=True)
```

### Path Traversal

**Mitigated**: All paths resolved via `pathlib.Path.resolve()`:

```python
input_dir = Path(args.input).resolve()  # Canonicalizes path
```

### Disk Exhaustion

**Partially mitigated**: Pre-flight check estimates disk usage (3× input size).

**Not mitigated**: Long-running video rendering can't be interrupted gracefully (TODO: add signal handlers).

## Testing Strategy

See [TEST_PLAN.md](TEST_PLAN.md) for comprehensive testing guide.

**Quick summary**:
- Unit tests: Pure functions (crossfade calc, natural sort, order.txt parsing)
- Integration tests: End-to-end with fixtures (synthetic audio)
- Manual tests: Real music, quality checks (listening, visual inspection)

## Observability

### Logs

- **Console**: Progress indicators, stage transitions
- **run_log.txt**: Full chronological log with timestamps
- **manifest.json**: Structured data for machine parsing

### Debugging

All FFmpeg commands logged **before execution**:

```
[2025-01-15 10:23:45] Running FFmpeg command:
ffmpeg -i track1.mp3 -i track2.mp3 -filter_complex "[0:a]loudnorm=I=-20:TP=-1.5:LRA=11[norm0];[1:a]loudnorm=I=-20:TP=-1.5:LRA=11[norm1];[norm0][norm1]acrossfade=d=15:c1=tri:c2=tri[out]" -map "[out]" -ar 48000 -ac 2 -sample_fmt s16 -y merged_clean.wav
```

Copy-paste to reproduce issues.

## Dependencies

### External (Required)

- **Python 3.10+**: Dataclasses, pathlib, typing improvements
- **FFmpeg 4.4+**: Audio/video processing engine

### Python Stdlib Only

- `argparse`: CLI argument parsing
- `subprocess`: FFmpeg execution
- `logging`: Dual logging
- `dataclasses`: Type-safe config
- `pathlib`: Path handling
- `json`: Manifest serialization
- `hashlib`: SHA256 checksums

**No external Python packages** for production use (pytest/black/ruff for dev only).

## File Structure

```
maple_lofi/
├── __init__.py              # Package marker
├── __main__.py              # Entry point (python -m maple_lofi)
├── cli.py                   # Argument parsing, pre-flight
├── pipeline.py              # Orchestrator
├── config.py                # PipelineConfig dataclass
│
├── stages/
│   ├── ingest.py            # Stage 1
│   ├── merge.py             # Stage 2
│   ├── lofi.py              # Stage 3
│   └── video.py             # Stage 4
│
├── ffmpeg/
│   ├── executor.py          # subprocess wrapper
│   ├── commands.py          # Command builders
│   └── probe.py             # ffprobe metadata
│
├── logging/
│   ├── logger.py            # Dual logging setup
│   └── manifest.py          # ManifestBuilder
│
└── utils/
    ├── validators.py        # Pre-flight checks
    ├── file_utils.py        # SHA256, file size
    └── natural_sort.py      # Filename sorting
```

**Total lines of code**: ~1500 (excluding docs/tests)

## Comparison to Alternatives

| Feature | Maple Lofi | pydub | ffmpeg-python | Audacity scripting |
|---------|-----------|-------|---------------|-------------------|
| Dependency count | 0 | 1 | 1 | 0 |
| Reproducibility | Full | Partial | Full | Manual |
| Auditability | manifest.json | None | None | Log file |
| Learning curve | Medium | Low | High | Low |
| Flexibility | High | Medium | High | Medium |
| Type safety | Full (dataclasses) | None | Partial | N/A |

**Trade-off**: Slightly more code than pydub approach, but gains reproducibility, auditability, and educational value.

## Future Improvements

**Not implemented yet, but architecturally feasible:**

1. **Resume failed runs**: Check manifest for completed stages, skip them
2. **Parallel track probing**: Speed up Stage 1 for many files
3. **Progress bars**: Add rich/tqdm for better UX (current: text logs)
4. **Plugin system**: Load custom stages from external modules
5. **Web UI**: Flask app wrapping CLI (for non-technical users)
6. **Cloud rendering**: S3 input/output, EC2 processing

## Conclusion

The Maple Lofi Pipeline prioritizes **simplicity, reproducibility, and educational clarity** over maximum performance or features. It demonstrates:

- Clean architecture with pure functions
- Proper separation of concerns (CLI → Orchestrator → Stages → FFmpeg)
- Comprehensive error handling and logging
- Minimal dependencies (stdlib + FFmpeg)
- Type safety with dataclasses
- Extensive documentation for learning

**Suitable for**: Educational projects, personal use, small-scale production.

**Not suitable for**: Real-time processing, web-scale parallel rendering, GUI applications (CLI only).

---

**See also**:
- [PIPELINE_CONTRACT.md](PIPELINE_CONTRACT.md) - Stage interface contracts
- [DEBUGGING.md](DEBUGGING.md) - Common issues and solutions
- [LEARNING_PATH.md](LEARNING_PATH.md) - How to learn from this codebase
