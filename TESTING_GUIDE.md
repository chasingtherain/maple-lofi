# Testing Guide for Maple Lofi Pipeline

## Quick Start: Synthetic Test (5 minutes)

This is the fastest way to verify the pipeline works end-to-end.

### Step 1: Generate Test Files

```bash
# Run the test file generator
./scripts/generate_test_audio.sh
```

This creates:
- 3 short music tracks (10s each, different tones)
- Rain texture (2s loop)
- Drum loop (1s loop)
- Placeholder cover image

### Step 2: Run Minimal Test (Audio Only)

```bash
python3 -m maple_lofi --input test_input --output test_output
```

**Expected:**
- ✅ Merges 3 tracks with crossfades
- ✅ Applies lofi processing (no texture/drums, just EQ + compression)
- ✅ Outputs: `merged_clean.wav`, `merged_lofi.wav`, `merged_lofi.mp3`
- ✅ Creates `manifest.json` and `run_log.txt`

**Duration:** ~30 seconds

### Step 3: Run Full Test (With Video)

```bash
python3 -m maple_lofi \
  --input test_input \
  --output test_output \
  --cover test_assets/cover.png \
  --texture test_assets/rain.wav \
  --drums test_assets/drums.wav
```

**Expected:**
- ✅ All of the above PLUS
- ✅ Video: `final_video.mp4` (30s, 1920x1080, 1fps)
- ✅ Thumbnail: `thumbnail.png`

**Duration:** ~1-2 minutes

### Step 4: Verify Outputs

```bash
# Check output files exist
ls -lh test_output/

# Play the audio (macOS)
afplay test_output/merged_lofi.mp3

# Play the video (macOS)
open test_output/final_video.mp4

# Inspect manifest
cat test_output/manifest.json | python3 -m json.tool

# Read log
cat test_output/run_log.txt
```

### Step 5: Clean Up

```bash
rm -rf test_input test_output test_assets
```

---

## Real Music Test (MapleStory BGM)

Once synthetic tests pass, test with real music.

### Where to Get MapleStory Music

**Legal sources:**
1. **Extract from game files** (if you own the game)
   - Look for `.wz` files in MapleStory installation
   - Use WZ file extractors (search "MapleStory WZ extractor")

2. **YouTube downloads** (personal use only, not for distribution)
   - Find MapleStory OST uploads
   - Use `yt-dlp` to download audio:
     ```bash
     yt-dlp -x --audio-format mp3 "https://youtube.com/watch?v=..."
     ```

3. **Free alternatives for testing:**
   - Use any royalty-free lofi/game music
   - Sources: Free Music Archive, Incompetech, Bensound

### Setup Real Test

```bash
# Create directories
mkdir -p real_input real_output real_assets

# Add your MapleStory MP3/WAV files to real_input/
# Name them clearly (e.g., ellinia.mp3, henesys.mp3, etc.)

# Optional: Create order.txt for custom ordering
cat > real_input/order.txt <<EOF
ellinia.mp3
henesys.mp3
ludibrium.mp3
EOF

# Get lofi assets (see below)
```

### Get Lofi Assets

**Rain texture:**
- [Freesound.org](https://freesound.org) - search "rain ambience"
- Download as WAV, ~30-60 seconds is enough (loops automatically)

**Drum loop:**
- [Freesound.org](https://freesound.org) - search "lofi drum loop"
- Or use royalty-free beat packs
- 2-4 bar loops work best

**Cover image:**
- Any 16:9 image works (will be scaled to 1920x1080)
- MapleStory fan art, screenshots, etc.
- Or create your own

### Run Real Pipeline

```bash
python3 -m maple_lofi \
  --input real_input \
  --output real_output \
  --cover real_assets/cover.png \
  --texture real_assets/rain.wav \
  --drums real_assets/drums.wav \
  --drums-start 20
```

---

## Incremental Testing Strategy

Test stages incrementally to isolate issues:

### Test 1: Ingest Only

```bash
# Run pipeline, it will fail after ingest but you'll see track discovery
python3 -m maple_lofi --input test_input --output test_output --skip-lofi 2>&1 | head -20
```

Check: Do all tracks get discovered? Is order correct?

### Test 2: Merge Only (Skip Lofi)

```bash
python3 -m maple_lofi --input test_input --output test_output --skip-lofi
```

Check: Does `merged_clean.wav` sound smooth? No pops/clicks at transitions?

### Test 3: Lofi (No Assets)

```bash
python3 -m maple_lofi --input test_input --output test_output
```

Check: Does lofi processing work? Is there clipping? (Open in Audacity to check waveform)

### Test 4: Lofi (With Texture Only)

```bash
python3 -m maple_lofi \
  --input test_input \
  --output test_output \
  --texture test_assets/rain.wav
```

Check: Can you hear rain in background? Is music still audible?

### Test 5: Full Pipeline

```bash
python3 -m maple_lofi \
  --input test_input \
  --output test_output \
  --cover test_assets/cover.png \
  --texture test_assets/rain.wav \
  --drums test_assets/drums.wav
```

Check: Everything works together?

---

## Quality Checks

### Audio Quality

**Listen for:**
- ✅ Smooth crossfades (no hard cuts or pops)
- ✅ Music still audible under texture/drums
- ✅ No clipping or distortion
- ✅ Consistent volume throughout

**Tools:**
- **Audacity** (free): Open WAV files, check waveform for clipping
- **ffprobe**: Check for clipping warnings
  ```bash
  ffmpeg -i test_output/merged_lofi.wav -af volumedetect -f null - 2>&1 | grep max_volume
  ```

### Video Quality

**Check:**
- ✅ Duration matches audio exactly
  ```bash
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 test_output/merged_lofi.wav
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 test_output/final_video.mp4
  ```
- ✅ Image not stretched (proper letterboxing if not 16:9)
- ✅ Plays smoothly in video player
- ✅ YouTube uploader accepts it (try uploading to test)

### Manifest Validation

```bash
# Check manifest is valid JSON
python3 -c "import json; json.load(open('test_output/manifest.json'))"

# Check all expected fields exist
cat test_output/manifest.json | python3 -m json.tool | grep -E "(run_id|timestamp|inputs|outputs|stages)"

# Verify SHA256 checksums
python3 -c "
import json, hashlib
manifest = json.load(open('test_output/manifest.json'))
for name, data in manifest['outputs'].items():
    with open(data['path'], 'rb') as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    expected = data['sha256']
    status = '✅' if actual == expected else '❌'
    print(f'{status} {name}: {actual == expected}')
"
```

---

## Edge Case Testing

### Short Tracks (< Crossfade Duration)

Create a very short track:
```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -y test_input/short.mp3
```

Expected: Crossfade should reduce to 50% of track duration (2.5s)

### Order.txt Edge Cases

**Test duplicate entries:**
```bash
cat > test_input/order.txt <<EOF
track1.mp3
track2.mp3
track1.mp3
EOF
```

Expected: track1.mp3 plays twice

**Test missing file in order.txt:**
```bash
cat > test_input/order.txt <<EOF
track1.mp3
nonexistent.mp3
EOF
```

Expected: Error message, exit code 1

**Test comments and blank lines:**
```bash
cat > test_input/order.txt <<EOF
# This is a comment
track1.mp3

track2.mp3
# Another comment
track3.mp3
EOF
```

Expected: Processes 3 tracks, ignores comments/blanks

### Long Audio Test

For real use, test with 60+ minutes of audio:
- Check: Does it complete without crashing?
- Check: Does video duration match exactly?
- Check: No degradation in quality over time?

---

## Troubleshooting

### "ffmpeg not found"
```bash
# Install FFmpeg
# macOS:
brew install ffmpeg

# Ubuntu:
sudo apt install ffmpeg
```

### "No audio files found"
- Check file extensions (must be .mp3, .wav, .m4a, or .flac)
- Check files are in input directory (not subdirectories)
- Run: `ls -la test_input/`

### "Crossfade failed" or audio sounds wrong
- Check logs: `cat test_output/run_log.txt`
- Check FFmpeg commands in manifest.json
- Try with `--skip-lofi` to isolate merge vs lofi issues

### Video rendering takes forever
- Expected for long audio (1fps still means rendering many frames)
- For 60 min audio: ~5-10 min rendering time is normal
- Check progress in log file: `tail -f test_output/run_log.txt`

### Clipping detected
- Reduce texture/drums gain:
  ```bash
  --texture-gain -30 --drums-gain -26
  ```
- Check input files aren't already clipping

---

## Performance Benchmarks

Expected processing times (on modern MacBook):

| Input Duration | Merge | Lofi | Video | Total |
|----------------|-------|------|-------|-------|
| 10s (3 tracks) | 2s    | 3s   | 5s    | ~10s  |
| 5min           | 5s    | 10s  | 30s   | ~45s  |
| 30min          | 15s   | 45s  | 3min  | ~5min |
| 60min          | 30s   | 90s  | 6min  | ~10min|

Longer input = proportionally longer processing.

---

## Success Criteria

A successful test means:

✅ All stages complete without errors
✅ `merged_clean.wav` has smooth crossfades
✅ `merged_lofi.wav` sounds balanced (music audible, no clipping)
✅ `merged_lofi.mp3` is 320kbps CBR
✅ `final_video.mp4` duration matches audio
✅ `manifest.json` is valid JSON with correct checksums
✅ `run_log.txt` shows no errors

If all checks pass → Pipeline works! 🎉

---

## Next Steps After Testing

1. Test with your actual MapleStory music
2. Tweak parameters (crossfade duration, EQ, gains) to taste
3. Upload to YouTube and enjoy!
4. (Optional) Contribute documentation improvements back to the project
