# Soundweave

Random soundtrack selector and YouTube video generator with automatic timestamp generation.

## Features

- Random track selection from a pool of audio files
- Smooth crossfading between tracks
- YouTube-ready video generation with static image
- Automatic timestamp generation for YouTube descriptions
- Clean track name formatting
- High-quality audio output (320kbps MP3 + 48kHz WAV)

## Installation

```bash
# Clone the repository
git clone https://github.com/chasingtherain/soundweave.git
cd soundweave

# Install dependencies (requires Python 3.10+ and FFmpeg)
pip install -e .
```

## Usage

```bash
# Basic: Random 20 tracks with video
python -m soundweave --input input --output output --image cover.png

# Select specific number of tracks
python -m soundweave --input input --output output --image cover.png --num-tracks 30

# Just audio, no video
python -m soundweave --input input --output output

# Custom crossfade duration
python -m soundweave --input input --output output --fade-ms 5000
```

## Outputs

- `merged.wav` - 48kHz stereo WAV
- `merged.mp3` - 320kbps MP3
- `youtube_description.txt` - Timestamps in YouTube format
- `final_video.mp4` - (if `--image` provided)
- `manifest.json` - Pipeline metadata

## Requirements

- Python 3.10+
- FFmpeg 4.0+
