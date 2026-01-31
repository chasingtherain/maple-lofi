#!/usr/bin/env bash
# Generate synthetic test audio files for pipeline testing

set -e

echo "Generating test audio files..."

# Create test directories
mkdir -p test_input test_output test_assets

# Generate 3 short music tracks (10 seconds each, different frequencies)
echo "Creating track1.mp3 (440Hz - A note)..."
ffmpeg -f lavfi -i "sine=frequency=440:duration=10" -y test_input/track1.mp3 2>/dev/null

echo "Creating track2.mp3 (523Hz - C note)..."
ffmpeg -f lavfi -i "sine=frequency=523:duration=10" -y test_input/track2.mp3 2>/dev/null

echo "Creating track3.mp3 (659Hz - E note)..."
ffmpeg -f lavfi -i "sine=frequency=659:duration=10" -y test_input/track3.mp3 2>/dev/null

# Generate rain texture (2 seconds of white noise)
echo "Creating rain.wav (white noise texture)..."
ffmpeg -f lavfi -i "anoisesrc=duration=2:color=white:amplitude=0.1" -y test_assets/rain.wav 2>/dev/null

# Generate simple drum beat (1 second loop)
echo "Creating drums.wav (simple beat)..."
ffmpeg -f lavfi -i "sine=frequency=80:duration=0.1,sine=frequency=200:duration=0.1" \
  -filter_complex "[0][1]concat=n=2:v=0:a=1[out]" -map "[out]" -y test_assets/drums.wav 2>/dev/null

# Generate placeholder cover image (1920x1080 blue gradient)
echo "Creating cover.png..."
ffmpeg -f lavfi -i "color=c=blue:s=1920x1080:d=1" -frames:v 1 -y test_assets/cover.png 2>/dev/null

echo ""
echo "✅ Test files created:"
echo "  test_input/track1.mp3 (10s)"
echo "  test_input/track2.mp3 (10s)"
echo "  test_input/track3.mp3 (10s)"
echo "  test_assets/rain.wav (2s loop)"
echo "  test_assets/drums.wav (1s loop)"
echo "  test_assets/cover.png (1920x1080)"
echo ""
echo "Ready to test! Run:"
echo "  python3 -m maple_lofi --input test_input --output test_output --cover test_assets/cover.png --texture test_assets/rain.wav --drums test_assets/drums.wav"
