#!/usr/bin/env bash
# Create a video from a static image and audio file
# Usage: ./scripts/make_video.sh <image> <audio> <output>
#
# The image will be scaled/padded to 1920x1080 (16:9) with black bars if needed

set -e

# Check arguments
if [ $# -lt 3 ]; then
    echo "Usage: $0 <image> <audio> <output.mp4>"
    echo ""
    echo "Example:"
    echo "  $0 cover.png merged.wav output.mp4"
    echo ""
    echo "The image will be scaled to fit 1920x1080 (16:9) with letterboxing if needed."
    exit 1
fi

IMAGE="$1"
AUDIO="$2"
OUTPUT="$3"

# Validate inputs exist
if [ ! -f "$IMAGE" ]; then
    echo "ERROR: Image file not found: $IMAGE"
    exit 1
fi

if [ ! -f "$AUDIO" ]; then
    echo "ERROR: Audio file not found: $AUDIO"
    exit 1
fi

echo "Creating video..."
echo "  Image: $IMAGE"
echo "  Audio: $AUDIO"
echo "  Output: $OUTPUT"
echo ""

# Get audio duration for progress indication
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO")
echo "Audio duration: ${DURATION}s"
echo ""

# Create video:
# - Scale image to fit within 1920x1080, preserving aspect ratio
# - Pad with black to exactly 1920x1080
# - Use 1fps for minimal file size (static image)
# - H.264 video, AAC audio for YouTube compatibility
ffmpeg -loop 1 -i "$IMAGE" -i "$AUDIO" \
    -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[v]" \
    -map "[v]" -map 1:a \
    -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
    -c:a aac -b:a 192k \
    -r 1 \
    -shortest \
    -y "$OUTPUT"

echo ""
echo "✅ Video created: $OUTPUT"

# Show output file info
echo ""
echo "Output details:"
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height -of default=noprint_wrappers=1 "$OUTPUT"
