# Debugging Guide

This guide helps you debug common issues in the Maple Lofi Pipeline.

## Quick Diagnosis

1. **Check the exit code**: `echo $?` (0 = success, 1-3 = specific errors)
2. **Read the log**: `cat output/run_log.txt`
3. **Check the manifest**: `cat output/manifest.json | python3 -m json.tool`
4. **Test FFmpeg commands manually**: Copy from log and run in terminal

## Common Issues

### 1. "FFmpeg not found"

**Symptom**:
```
Error: FFmpeg not found. Please install FFmpeg 4.4+
Exit code: 1
```

**Cause**: FFmpeg is not installed or not in PATH.

**Solution**:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Verify installation
ffmpeg -version
```

**Required version**: 4.4 or higher

---

### 2. "No audio files found in input directory"

**Symptom**:
```
Error: No audio files found in /path/to/input
Supported formats: .mp3, .wav, .m4a, .flac, .mpeg
Exit code: 1
```

**Causes**:
1. Wrong input directory
2. Files in subdirectories (pipeline only scans top level)
3. Unsupported file extensions

**Solutions**:

```bash
# Check files in directory
ls -la input/

# Move files to top level
mv input/subdir/*.mp3 input/

# Check file extensions
ls input/*.mp3
```

**Supported extensions**: `.mp3`, `.wav`, `.m4a`, `.flac`, `.mpeg`

---

### 3. "File listed in order.txt not found"

**Symptom**:
```
Error: File 'track5.mp3' listed in order.txt not found in input directory
Exit code: 1
```

**Cause**: order.txt lists a file that doesn't exist.

**Solution**:

```bash
# Check what files exist
ls input/

# Edit order.txt to match actual files
cat > input/order.txt <<EOF
track1.mp3
track2.mp3
track3.mp3
EOF
```

**Remember**: order.txt must list ALL files in directory (no more, no less).

---

### 4. "FFmpeg failed: Invalid filter syntax"

**Symptom**:
```
ERROR: FFmpeg failed (exit code 1)
stderr: [Parsed_acrossfade_0 @ 0x...] Unable to parse option value
Exit code: 2
```

**Cause**: Usually a bug in filter graph construction.

**Debug steps**:

1. **Find the FFmpeg command** in run_log.txt:
   ```bash
   grep "ffmpeg -i" output/run_log.txt
   ```

2. **Copy and run manually**:
   ```bash
   # Paste the exact command from log
   ffmpeg -i track1.mp3 -i track2.mp3 -filter_complex "..." -y test.wav
   ```

3. **Simplify the command** to isolate the issue:
   ```bash
   # Test without filter
   ffmpeg -i track1.mp3 -y test.wav

   # Test with simple filter
   ffmpeg -i track1.mp3 -filter_complex "[0:a]loudnorm[out]" -map "[out]" -y test.wav
   ```

**Common causes**:
- Crossfade duration > track duration (should auto-reduce, but edge case)
- Invalid characters in filter graph
- Unsupported filter on your FFmpeg version

---

### 5. "Clipping detected in output"

**Symptom**:
Audio sounds distorted or has pops/clicks.

**Check for clipping**:

```bash
# Use FFmpeg volumedetect filter
ffmpeg -i output/merged_lofi.wav -af volumedetect -f null - 2>&1 | grep max_volume

# If max_volume is close to 0.0 dB, you have clipping
```

**Solutions**:

1. **Reduce texture gain**:
   ```bash
   python3 -m maple_lofi \
     --input input \
     --output output \
     --texture rain.wav \
     --texture-gain -30  # Default is -26, try -30
   ```

2. **Reduce drums gain**:
   ```bash
   python3 -m maple_lofi \
     --input input \
     --output output \
     --drums drums.wav \
     --drums-gain -26  # Default is -22, try -26
   ```

3. **Check input files**:
   ```bash
   # Check each input track
   for f in input/*.mp3; do
     ffmpeg -i "$f" -af volumedetect -f null - 2>&1 | grep max_volume
   done
   ```

**Root cause**: Usually hot input files or too much gain on texture/drums.

---

### 6. "Video duration doesn't match audio"

**Symptom**:
```bash
# Audio is 10:30, but video is 10:29 or 10:31
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/merged_lofi.wav
# 630.5

ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/final_video.mp4
# 629.8
```

**Cause**: Usually a bug in video rendering stage (duration calculation).

**Debug steps**:

1. **Check manifest.json**:
   ```bash
   cat output/manifest.json | python3 -c "
   import json, sys
   m = json.load(sys.stdin)
   print(f\"Audio: {m['outputs']['merged_lofi_wav']['duration_s']}s\")
   print(f\"Video: {m['outputs']['final_video']['duration_s']}s\")
   "
   ```

2. **Re-render video manually**:
   ```bash
   # Get exact audio duration
   DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/merged_lofi.wav)

   # Render video with exact duration
   ffmpeg -loop 1 -i cover.png -i output/merged_lofi.wav \
     -c:v libx264 -c:a aac -b:a 192k -r 1 -t $DURATION -y output/final_video.mp4
   ```

**Report**: If this happens, it's a bug - please report with manifest.json.

---

### 7. "Crossfades are too long/short"

**Symptom**:
- Crossfades overlap too much (songs blend together)
- Crossfades are abrupt (hard cuts)

**Solution**:

```bash
# Short crossfades (0.5s)
python3 -m maple_lofi \
  --input input \
  --output output \
  --fade-ms 500

# Long crossfades (30s)
python3 -m maple_lofi \
  --input input \
  --output output \
  --fade-ms 30000
```

**Default**: 15000ms (15 seconds)

**Recommendation**: 500-1000ms for minimal overlap, 10000-20000ms for smooth blending.

---

### 8. "Output file size is huge"

**Symptom**:
```bash
ls -lh output/
# merged_clean.wav: 500MB (for 30 minutes of audio)
```

**Explanation**: This is expected for WAV files.

**File sizes** (approximate):
- WAV (48kHz, 16-bit stereo): ~10MB per minute
- MP3 (320kbps): ~2.4MB per minute

**Solutions**:

1. **Use MP3 for final output** (automatically created):
   ```bash
   # merged_lofi.mp3 is much smaller
   ls -lh output/merged_lofi.mp3
   ```

2. **Delete intermediate WAV files** if disk space is tight:
   ```bash
   rm output/merged_clean.wav  # Keep merged_lofi.mp3 and final_video.mp4
   ```

**Do NOT compress WAV files** - they are intermediate lossless files.

---

### 9. "Pipeline is very slow"

**Symptom**:
Processing 60 minutes of audio takes 20+ minutes.

**Expected performance** (modern MacBook):

| Input Duration | Expected Time |
|----------------|---------------|
| 10 min | ~1-2 min |
| 30 min | ~5-8 min |
| 60 min | ~10-15 min |

**Bottlenecks**:

1. **Video rendering** (Stage 4): Slowest part
   - 1fps video still means rendering thousands of frames
   - For 60 min audio: ~3600 frames at 1fps

2. **Lofi processing** (Stage 3): Medium
   - Loudness normalization is computationally expensive

3. **Merge** (Stage 2): Fast
   - Crossfading is relatively quick

**Solutions**:

1. **Skip video** if you only need audio:
   ```bash
   python3 -m maple_lofi --input input --output output
   # No --cover = no video rendering
   ```

2. **Skip lofi** for testing:
   ```bash
   python3 -m maple_lofi --input input --output output --skip-lofi
   # Only merge, no processing
   ```

3. **Use faster machine** or **wait longer** (it's doing a lot of work!)

---

### 10. "Tracks play in wrong order"

**Symptom**:
Tracks merge in unexpected order.

**Default ordering**: Natural sort (case-insensitive)

```
track1.mp3
track2.mp3
track10.mp3  # ← Comes after track2, not between track1 and track2
```

**Solution**: Create order.txt to specify exact order:

```bash
cat > input/order.txt <<EOF
# Comments are allowed
track1.mp3
track10.mp3
track2.mp3
EOF
```

**Important**: order.txt must list ALL files (no more, no less).

---

### 11. "Loudness is inconsistent between tracks"

**Symptom**:
Some tracks are much louder than others in final output.

**Expected**: Pipeline includes loudness normalization (-20 LUFS).

**Debug**:

1. **Check input files**:
   ```bash
   for f in input/*.mp3; do
     echo "=== $f ==="
     ffmpeg -i "$f" -af loudnorm=print_format=json -f null - 2>&1 | grep input_i
   done
   ```

2. **Verify normalization is working**:
   ```bash
   # Check merged output
   ffmpeg -i output/merged_clean.wav -af loudnorm=print_format=json -f null - 2>&1 | grep input_i
   # Should be close to -20 LUFS
   ```

**If normalization isn't working**: Check FFmpeg version (need 4.2+ for loudnorm filter).

---

### 12. "Cover image is stretched/distorted"

**Symptom**:
Cover image doesn't look right in video.

**Cause**: Image aspect ratio doesn't match 16:9 (1920x1080).

**Expected behavior**: Pipeline should letterbox (add black bars), not stretch.

**Verify**:
```bash
# Check cover image dimensions
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 cover.png
```

**Best practice**: Use 16:9 images (1920x1080, 1280x720, etc.) to avoid letterboxing.

**Debug command** (from log):
```bash
# Find video rendering command in log
grep "ffmpeg.*cover.*final_video" output/run_log.txt
```

---

## Advanced Debugging

### Enable Debug Logging

Modify `maple_lofi/logging/logger.py` to enable DEBUG level:

```python
console_handler.setLevel(logging.DEBUG)  # Was INFO
```

Rerun pipeline - run_log.txt will have more detail.

### Inspect FFmpeg Commands

All FFmpeg commands are logged to run_log.txt. Extract and test:

```bash
# Extract all FFmpeg commands
grep "^ffmpeg " output/run_log.txt > commands.sh

# Run commands manually
bash commands.sh
```

### Validate Manifest

```bash
# Check manifest is valid JSON
python3 -c "import json; json.load(open('output/manifest.json'))"

# Pretty-print manifest
python3 -m json.tool output/manifest.json

# Verify checksums
python3 -c "
import json, hashlib
m = json.load(open('output/manifest.json'))
for name, data in m['outputs'].items():
    with open(data['path'], 'rb') as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    expected = data['sha256']
    print(f\"{'✓' if actual == expected else '✗'} {name}\")
"
```

### Profile Performance

Add timing to each stage:

```bash
# Check stage durations in manifest
python3 -c "
import json
m = json.load(open('output/manifest.json'))
for stage in m['stages']:
    print(f\"{stage['name']}: {stage['duration_s']:.1f}s\")
"
```

### Test Individual Stages

You can test stages independently:

```python
# Test ingest only
from maple_lofi.config import PipelineConfig
from maple_lofi.stages.ingest import ingest_stage
from maple_lofi.logging.logger import setup_logger

config = PipelineConfig(input_dir=Path("input"), output_dir=Path("output"))
logger = setup_logger(Path("test.log"))

tracks = ingest_stage(config, logger)
print(tracks)
```

## Getting Help

If you're stuck:

1. **Check TESTING_GUIDE.md** for test procedures
2. **Read ADRs** in `docs/ADRs/` to understand design decisions
3. **Inspect manifest.json** for detailed run information
4. **Open an issue** with:
   - run_log.txt
   - manifest.json
   - Input file details (duration, format)
   - Expected vs actual behavior

## Common Error Exit Codes

- `0`: Success
- `1`: Validation error (bad inputs, missing dependencies)
- `2`: Processing error (FFmpeg failure, corrupted files)
- `3`: Output error (disk full, permissions)

Check exit code:
```bash
python3 -m maple_lofi --input input --output output
echo "Exit code: $?"
```

---

**Remember**: Most issues are either:
1. Missing FFmpeg / wrong version
2. Invalid input files
3. Incorrect parameters (crossfade too long, gain too high)

Check logs first!
