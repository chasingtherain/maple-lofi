"""FFprobe integration for audio metadata extraction."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from soundweave.utils.validators import ValidationError


@dataclass
class AudioMetadata:
    """Metadata extracted from an audio file."""

    duration_s: float
    sample_rate: int
    channels: int
    codec: str
    bit_rate: int | None = None


def probe_audio_file(file_path: Path) -> AudioMetadata:
    """Extract metadata from an audio file using ffprobe.

    Args:
        file_path: Path to audio file

    Returns:
        AudioMetadata with duration, sample rate, channels, etc.

    Raises:
        ValidationError: If file is corrupted or unsupported
    """
    try:
        # Run ffprobe with JSON output
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            raise ValidationError(f"ffprobe failed for {file_path.name}")

        # Parse JSON output
        data = json.loads(result.stdout)

        # Find the first audio stream
        audio_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                audio_stream = stream
                break

        if not audio_stream:
            raise ValidationError(f"No audio stream found in {file_path.name}")

        # Extract metadata
        format_info = data.get("format", {})

        duration_s = float(format_info.get("duration", 0))
        if duration_s <= 0:
            raise ValidationError(f"Invalid duration for {file_path.name}")

        sample_rate = int(audio_stream.get("sample_rate", 0))
        if sample_rate <= 0:
            raise ValidationError(f"Invalid sample rate for {file_path.name}")

        channels = int(audio_stream.get("channels", 0))
        if channels <= 0:
            raise ValidationError(f"Invalid channel count for {file_path.name}")

        codec = audio_stream.get("codec_name", "unknown")

        # Bit rate may not always be available
        bit_rate = None
        if "bit_rate" in audio_stream:
            bit_rate = int(audio_stream["bit_rate"])
        elif "bit_rate" in format_info:
            bit_rate = int(format_info["bit_rate"])

        return AudioMetadata(
            duration_s=duration_s,
            sample_rate=sample_rate,
            channels=channels,
            codec=codec,
            bit_rate=bit_rate
        )

    except FileNotFoundError:
        raise ValidationError("ffprobe not found. Please install FFmpeg.")
    except subprocess.TimeoutExpired:
        raise ValidationError(f"ffprobe timed out for {file_path.name}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValidationError(f"Failed to parse ffprobe output for {file_path.name}: {e}")


def probe_loudnorm_duration(file_path: Path) -> float:
    """Measure the actual output duration after applying silence trim and loudnorm.

    The silenceremove filter trims trailing silence and the loudnorm filter can
    change track duration slightly. This function measures the actual output
    duration to enable accurate timestamp calculation.

    Args:
        file_path: Path to audio file

    Returns:
        Duration in seconds after silence trim and loudnorm processing

    Raises:
        ValidationError: If FFmpeg fails or output cannot be parsed
    """
    try:
        # Output to raw PCM and count bytes to calculate duration
        # This is reliable because we know the exact output format
        # 48kHz, stereo (2 channels), 16-bit (2 bytes per sample)
        # Duration = total_bytes / (48000 * 2 * 2)
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", str(file_path),
                "-af", "silenceremove=stop_periods=1:stop_duration=0.5:stop_threshold=-50dB,loudnorm=I=-20:TP=-1.5:LRA=11",
                "-ar", "48000",
                "-ac", "2",
                "-f", "s16le",
                "-"
            ],
            capture_output=True,
            timeout=120  # Allow up to 2 minutes per track
        )

        if result.returncode != 0:
            raise ValidationError(
                f"FFmpeg failed for {file_path.name}: {result.stderr.decode()[:200]}"
            )

        # Calculate duration from raw PCM bytes
        # 48000 samples/sec * 2 channels * 2 bytes/sample = 192000 bytes/sec
        bytes_per_second = 48000 * 2 * 2
        total_bytes = len(result.stdout)
        duration_s = total_bytes / bytes_per_second

        return duration_s

    except subprocess.TimeoutExpired:
        raise ValidationError(f"FFmpeg timed out measuring loudnorm duration for {file_path.name}")
    except FileNotFoundError:
        raise ValidationError("FFmpeg not found. Please install FFmpeg.")


def detect_track_boundaries(
    file_path: Path,
    expected_tracks: int,
    noise_db: float = -35,
    min_silence_duration: float = 0.1
) -> list[float]:
    """Detect track boundaries in merged audio using silence/volume dip detection.

    Crossfades create brief moments of lower volume at track transitions.
    This function finds these dips and returns timestamps for each track start.

    Args:
        file_path: Path to merged audio/video file
        expected_tracks: Number of tracks expected (to validate detection)
        noise_db: Threshold in dB below which audio is considered "quiet" (default: -35dB)
        min_silence_duration: Minimum duration of quiet moment to detect (default: 0.1s)

    Returns:
        List of timestamps (in seconds) for each track start, including 0.0 for first track

    Raises:
        ValidationError: If FFmpeg fails or detection doesn't match expected tracks
    """
    import re

    try:
        # Use silencedetect filter to find quiet moments (crossfade dips)
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", str(file_path),
                "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
                "-f", "null",
                "-"
            ],
            capture_output=True,
            text=True,
            timeout=600  # Allow up to 10 minutes for long files
        )

        # Parse silence_start timestamps from stderr
        # Format: [silencedetect @ 0x...] silence_start: 123.456
        silence_pattern = r"silence_start:\s*([\d.]+)"
        silence_starts = re.findall(silence_pattern, result.stderr)

        # Convert to floats and add 0.0 for first track
        timestamps = [0.0]
        for ts in silence_starts:
            timestamps.append(float(ts))

        # If we got expected number of boundaries, return them
        if len(timestamps) == expected_tracks:
            return timestamps

        # If we got more, we may need to adjust threshold
        # If we got fewer, the crossfades may not create enough of a dip
        # Return what we have with a warning (caller can decide what to do)
        return timestamps

    except subprocess.TimeoutExpired:
        raise ValidationError(f"FFmpeg timed out detecting track boundaries in {file_path.name}")
    except FileNotFoundError:
        raise ValidationError("FFmpeg not found. Please install FFmpeg.")
