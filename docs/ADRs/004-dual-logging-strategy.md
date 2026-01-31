# ADR 004: Dual Logging Strategy (Human + Machine Readable)

**Date**: 2025-01-15
**Status**: Accepted
**Decision makers**: Project architect
**Tags**: logging, observability, auditability, debugging

## Context

The pipeline performs complex audio/video processing that can fail in various ways:
- Invalid input files
- FFmpeg errors
- Disk space issues
- Corrupted audio
- Missing dependencies

Users need to:
1. **Debug failures**: "Why did it fail?"
2. **Audit runs**: "What exactly was processed?"
3. **Reproduce results**: "What commands were run?"
4. **Verify outputs**: "Are these outputs correct?"

We need a logging strategy that serves both humans (debugging) and machines (automation/verification).

## Problem

How should we log pipeline execution and outputs?

## Options Considered

### Option 1: Console Output Only

Print everything to stdout/stderr:

```python
print("Processing track1.mp3...")
print("Running FFmpeg command: ffmpeg -i track1.mp3 ...")
print("✓ Done")
```

**Pros**:
- Simple (no file I/O)
- Immediate feedback
- Works in any environment

**Cons**:
- **No persistence**: Output lost when terminal closes
- **Hard to parse**: Unstructured text
- **No auditability**: Can't verify what happened later
- **No checksums**: Can't verify outputs are correct

### Option 2: Single Log File (Text)

Write all output to a log file:

```python
# log.txt
2025-01-15 10:23:45 - Processing track1.mp3...
2025-01-15 10:23:46 - Running FFmpeg command: ffmpeg -i track1.mp3 ...
2025-01-15 10:23:50 - ✓ Done
```

**Pros**:
- Persistent (can review later)
- Chronological record
- Easy to read

**Cons**:
- **Hard to parse**: Unstructured text (grep/regex needed)
- **No machine-readable data**: Can't easily extract checksums, durations
- **Mixed concerns**: Human-readable vs machine-readable conflict
- **Limited auditability**: No structured output metadata

### Option 3: Single Log File (JSON)

Write structured JSON log:

```json
{
  "timestamp": "2025-01-15T10:23:45Z",
  "events": [
    {"type": "info", "message": "Processing track1.mp3"},
    {"type": "command", "command": "ffmpeg -i track1.mp3 ..."},
    {"type": "info", "message": "Done"}
  ]
}
```

**Pros**:
- Machine-parseable
- Structured data
- Easy to query programmatically

**Cons**:
- **Hard for humans to read**: Not friendly for debugging
- **Verbose**: JSON syntax adds noise
- **Order matters**: Streaming JSON is complex

### Option 4: Dual Logging (Chosen)

Write **two outputs**:
1. **run_log.txt**: Human-readable chronological log
2. **manifest.json**: Machine-readable structured metadata

```
output/
├── run_log.txt        # Human: Read to debug
├── manifest.json      # Machine: Parse to verify
├── merged_clean.wav
├── merged_lofi.wav
└── final_video.mp4
```

**run_log.txt** (human-readable):
```
=== Maple Lofi Pipeline ===
Run ID: 550e8400-e29b-41d4-a716-446655440000
Timestamp: 2025-01-15T10:23:45Z

=== Stage 1: Ingest ===
Scanning input directory: /path/to/input
Found 3 audio files:
  - track1.mp3 (2:30)
  - track2.mp3 (3:45)
  - track3.mp3 (4:15)
Order: natural sort (no order.txt found)
✓ Ingest complete (0.5s)

=== Stage 2: Merge ===
Calculating crossfades...
  track1.mp3 → track2.mp3: 15.0s crossfade
  track2.mp3 → track3.mp3: 15.0s crossfade
Running FFmpeg command:
  ffmpeg -i track1.mp3 -i track2.mp3 -i track3.mp3 -filter_complex "..." -y merged_clean.wav
✓ merged_clean.wav (12.3MB)
✓ Merge complete (8.2s)

...
```

**manifest.json** (machine-readable):
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-01-15T10:23:45Z",
  "python_version": "3.10.0",
  "ffmpeg_version": "4.4.2",
  "platform": "Darwin",
  "inputs": {
    "audio_files": [
      {
        "filename": "track1.mp3",
        "duration_s": 150.5,
        "sample_rate": 44100,
        "channels": 2,
        "codec": "mp3"
      }
    ],
    "order_source": "natural_sort"
  },
  "outputs": {
    "merged_clean": {
      "path": "output/merged_clean.wav",
      "file_size_mb": 12.3,
      "duration_s": 600.5,
      "sha256": "a1b2c3d4..."
    }
  },
  "stages": [
    {
      "name": "ingest",
      "status": "success",
      "duration_s": 0.5,
      "tracks_found": 3
    },
    {
      "name": "merge",
      "status": "success",
      "duration_s": 8.2,
      "crossfades_applied": 2
    }
  ],
  "ffmpeg_commands": [
    "ffmpeg -i track1.mp3 -i track2.mp3 -filter_complex \"...\" -y merged_clean.wav"
  ],
  "warnings": [],
  "errors": []
}
```

**Pros**:
- **Best of both worlds**: Human-readable logs + machine-readable metadata
- **Debuggable**: Read log file to understand what happened
- **Auditable**: Parse manifest to verify checksums, commands
- **Reproducible**: Manifest contains all inputs, parameters, commands
- **Queryable**: Can write scripts to analyze manifests

**Cons**:
- **Two files to maintain**: More complexity
- **Potential inconsistency**: Must keep both in sync

## Decision

**We will use dual logging: run_log.txt (human) + manifest.json (machine).**

### Implementation

#### run_log.txt (Logger)

```python
# maple_lofi/logging/logger.py

import logging
from pathlib import Path

def setup_logger(log_file: Path) -> logging.Logger:
    """Setup dual logging (console + file).

    Args:
        log_file: Path to run_log.txt

    Returns:
        Logger instance
    """
    logger = logging.getLogger("maple_lofi")
    logger.setLevel(logging.INFO)

    # Console handler (for interactive use)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    # File handler (for persistence)
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
```

**Usage**:
```python
logger.info("=== Stage 1: Ingest ===")
logger.info(f"Found {len(tracks)} audio files")
logger.debug(f"Track details: {tracks}")  # Only in file, not console
```

#### manifest.json (ManifestBuilder)

```python
# maple_lofi/logging/manifest.py

@dataclass
class ManifestBuilder:
    """Builds manifest.json for auditability."""

    config: PipelineConfig
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        """Initialize manifest structure."""
        self.data = {
            "run_id": self.config.run_id,
            "timestamp": self.config.timestamp,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "ffmpeg_version": self._get_ffmpeg_version(),
            "platform": platform.system(),
            "inputs": {},
            "outputs": {},
            "stages": [],
            "ffmpeg_commands": [],
            "warnings": [],
            "errors": []
        }

    def add_output(self, name: str, path: Path):
        """Add output file with SHA256 checksum."""
        self.data["outputs"][name] = {
            "path": str(path),
            "file_size_mb": round(path.stat().st_size / (1024 ** 2), 2),
            "sha256": self._compute_sha256(path)
        }

    def write(self, output_path: Path):
        """Write manifest to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.data, f, indent=2)
```

**Usage**:
```python
manifest.add_output("merged_clean", merged_clean_path)
manifest.add_stage_result("merge", "success", duration_s=8.2)
manifest.write(output_dir / "manifest.json")
```

## Rationale

### 1. Human Debugging

**Problem**: When pipeline fails, users need to understand what happened.

**Solution**: run_log.txt provides chronological narrative:

```
=== Stage 2: Merge ===
Running FFmpeg command:
  ffmpeg -i track1.mp3 -i track2.mp3 ...

[ffmpeg output]

ERROR: FFmpeg failed (exit code 1)
stderr: [Parsed_loudnorm_0 @ 0x...] Error processing audio
```

User can:
- Read top-to-bottom to understand flow
- See exact error message
- Copy-paste FFmpeg command to test manually

### 2. Machine Verification

**Problem**: How do you verify outputs are correct? Were they tampered with?

**Solution**: manifest.json contains SHA256 checksums:

```json
"outputs": {
  "merged_clean": {
    "sha256": "a1b2c3d4e5f6..."
  }
}
```

Verification script:
```python
import json, hashlib

manifest = json.load(open('output/manifest.json'))
for name, data in manifest['outputs'].items():
    with open(data['path'], 'rb') as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    expected = data['sha256']
    print(f"{'✓' if actual == expected else '✗'} {name}")
```

### 3. Reproducibility

**Problem**: "How was this output created?"

**Solution**: manifest.json records:
- All input files (with metadata)
- All FFmpeg commands executed
- All parameters used
- Environment (Python version, FFmpeg version, platform)

User can reproduce **exact same output** by running same commands with same inputs.

### 4. Auditability

**Problem**: "What files were processed? How long did it take?"

**Solution**: manifest.json provides structured data:

```json
{
  "stages": [
    {"name": "ingest", "duration_s": 0.5, "tracks_found": 3},
    {"name": "merge", "duration_s": 8.2, "crossfades_applied": 2},
    {"name": "lofi", "duration_s": 12.5},
    {"name": "video", "duration_s": 45.8}
  ]
}
```

Can write scripts to analyze performance across runs:
```python
# Find slow runs
runs = [json.load(open(f)) for f in glob('*/manifest.json')]
slow_runs = [r for r in runs if sum(s['duration_s'] for s in r['stages']) > 60]
```

### 5. Error Tracking

**Problem**: "Did the pipeline complete successfully? Were there warnings?"

**Solution**: manifest.json tracks errors/warnings:

```json
{
  "warnings": [
    "Track3.mp3 has clipping, consider reducing gain"
  ],
  "errors": []
}
```

Even on error, partial manifest is written:
```json
{
  "stages": [
    {"name": "ingest", "status": "success"},
    {"name": "merge", "status": "error"}
  ],
  "errors": [
    "FFmpeg failed: Invalid filter syntax"
  ]
}
```

## Consequences

### Positive

- **Best of both worlds**: Human-readable + machine-readable
- **Debuggable**: Read log file to understand flow
- **Auditable**: Verify outputs with checksums
- **Reproducible**: All commands recorded
- **Queryable**: Can analyze manifests programmatically
- **Error tracking**: Know exactly what succeeded/failed

### Negative

- **Two files**: Need to maintain consistency
- **More code**: ManifestBuilder + Logger setup
- **Disk usage**: ~10KB extra per run (negligible)

### Mitigation for Consistency

Both log and manifest are built during same Pipeline.run() execution:

```python
def run(self):
    # Update both
    self.logger.info("=== Stage 1: Ingest ===")
    tracks = ingest_stage(...)
    self.manifest.add_input_tracks(tracks)

    # Both get errors
    except ProcessingError as e:
        self.logger.error(f"Processing error: {e}")
        self.manifest.add_error(str(e))
```

## Implementation Guidelines

### For Junior Engineers

#### When to Log to run_log.txt

```python
# Stage transitions
logger.info("=== Stage 2: Merge ===")

# Important events
logger.info(f"Found {len(tracks)} audio files")

# Warnings
logger.warning("Track has clipping, results may be distorted")

# Errors (before raising exception)
logger.error(f"FFmpeg failed: {stderr}")

# Debug info (only in file, not console)
logger.debug(f"Full track metadata: {track}")
```

#### When to Add to manifest.json

```python
# Input files
manifest.add_input_tracks(tracks)
manifest.add_input_asset("cover_image", cover_path)

# Output files
manifest.add_output("merged_clean", merged_clean_path)

# Stage results
manifest.add_stage_result("merge", "success", duration_s=8.2, crossfades=2)

# FFmpeg commands (done automatically in run_ffmpeg)
manifest.add_ffmpeg_command(command)

# Warnings
manifest.add_warning("Track has clipping")

# Errors
manifest.add_error(str(exception))
```

#### Best Practices

1. **Log before risky operations**:
   ```python
   logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
   result = subprocess.run(cmd)  # If this fails, we logged the command
   ```

2. **Add outputs after creation**:
   ```python
   run_ffmpeg(cmd, ...)
   manifest.add_output("merged_clean", output_path)  # File exists now
   ```

3. **Write manifest even on error**:
   ```python
   except ProcessingError as e:
       manifest.add_error(str(e))
       manifest.write(output_dir / "manifest.json")  # Partial manifest
   ```

## Examples from Other Projects

### Webpack Build Tool

**Human log** (console):
```
webpack 5.0.0
Compiling...
✓ 15 modules compiled
⚠ 2 warnings
Build completed in 3.2s
```

**Machine manifest** (stats.json):
```json
{
  "time": 3200,
  "assets": [
    {"name": "bundle.js", "size": 245678}
  ],
  "warnings": ["Module parse warning..."]
}
```

### CI/CD Systems (GitHub Actions)

**Human log** (workflow run):
```
Run npm install
✓ Installed 234 packages
Run npm test
✓ 45 tests passed
```

**Machine manifest** (workflow API):
```json
{
  "conclusion": "success",
  "steps": [
    {"name": "npm install", "status": "completed"},
    {"name": "npm test", "status": "completed"}
  ]
}
```

## Related Decisions

- [ADR 001: Pipeline Architecture](001-pipeline-architecture.md) - Pipeline builds both log and manifest
- [ADR 003: FFmpeg Abstraction](003-ffmpeg-abstraction.md) - run_ffmpeg logs commands

## References

- Python logging docs: https://docs.python.org/3/library/logging.html
- Structured logging: https://www.structlog.org/en/stable/
- Build manifests: https://reproducible-builds.org/

## Review History

- **2025-01-15**: Initial decision (approved)

---

**Key Takeaway for Junior Engineers**: When building tools that process data, **log for both humans and machines**:
- **Human logs** (text): For debugging "what happened?"
- **Machine manifests** (JSON): For verification "is this correct?" and auditability "what was processed?"

This dual approach gives you the best of both worlds: easy debugging + automated verification.
