"""FFprobe integration for audio metadata extraction."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from maple_lofi.utils.validators import ValidationError


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
