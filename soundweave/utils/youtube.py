"""YouTube-related utilities for timestamps and track names."""

import re
from pathlib import Path

from soundweave.stages.ingest import AudioTrack


def clean_track_name(filename: str) -> str:
    """Clean up track filename for YouTube display.

    Args:
        filename: Original filename (e.g., "BlueSky.mp3.mpeg")

    Returns:
        Cleaned track name (e.g., "BlueSky")

    Examples:
        >>> clean_track_name("BlueSky.mp3.mpeg")
        'BlueSky'
        >>> clean_track_name("track_name.mp3")
        'track name'
        >>> clean_track_name("My-Song.flac")
        'My-Song'
    """
    # Remove file extensions (handle double extensions like .mp3.mpeg)
    name = filename
    while True:
        new_name = Path(name).stem
        if new_name == name:
            break
        name = new_name

    # Replace underscores with spaces
    name = name.replace("_", " ")

    return name


def format_timestamp(seconds: float) -> str:
    """Format seconds as YouTube timestamp (M:SS or H:MM:SS).

    Args:
        seconds: Time in seconds

    Returns:
        Formatted timestamp string

    Examples:
        >>> format_timestamp(0)
        '0:00'
        >>> format_timestamp(65)
        '1:05'
        >>> format_timestamp(3661)
        '1:01:01'
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def generate_youtube_timestamps(
    tracks: list[AudioTrack],
    crossfade_duration_s: float
) -> list[tuple[float, str]]:
    """Generate YouTube timestamps for a list of tracks.

    Args:
        tracks: List of audio tracks in playback order
        crossfade_duration_s: Crossfade duration in seconds

    Returns:
        List of (timestamp_seconds, track_name) tuples

    Notes:
        - First track starts at 0:00
        - Each subsequent track timestamp accounts for crossfade overlap
        - Track names are cleaned (extensions removed, underscores → spaces)
    """
    timestamps = []
    current_time = 0.0

    for i, track in enumerate(tracks):
        # Clean the track name
        clean_name = clean_track_name(track.filename)

        # Add timestamp
        timestamps.append((current_time, clean_name))

        # Calculate next timestamp (subtract crossfade overlap)
        if i < len(tracks) - 1:
            current_time += track.duration_s - crossfade_duration_s

    return timestamps


def format_youtube_description(
    timestamps: list[tuple[float, str]],
    title: str = "Tracklist"
) -> str:
    """Format timestamps as YouTube description text.

    Args:
        timestamps: List of (timestamp_seconds, track_name) tuples
        title: Optional title for the timestamp section

    Returns:
        Formatted description text ready for YouTube

    Example output:
        Tracklist:
        0:00 BlueSky
        2:41 CavaBien
        4:49 FloralLife
    """
    lines = [f"{title}:"]

    for timestamp_s, track_name in timestamps:
        formatted_time = format_timestamp(timestamp_s)
        lines.append(f"{formatted_time} {track_name}")

    return "\n".join(lines)


def write_youtube_description(
    output_path: Path,
    tracks: list[AudioTrack],
    crossfade_duration_s: float,
    title: str = "Tracklist",
    actual_timestamps: list[float] | None = None
) -> None:
    """Generate and write YouTube description file with timestamps.

    Args:
        output_path: Path for output description file (e.g., description.txt)
        tracks: List of audio tracks in playback order
        crossfade_duration_s: Crossfade duration in seconds
        title: Optional title for the timestamp section
        actual_timestamps: Optional list of actual timestamps (from silence detection).
                          If provided, these are used instead of calculating from durations.
    """
    if actual_timestamps and len(actual_timestamps) == len(tracks):
        # Use actual detected timestamps
        timestamps = []
        for i, track in enumerate(tracks):
            clean_name = clean_track_name(track.filename)
            timestamps.append((actual_timestamps[i], clean_name))
    else:
        # Fall back to calculated timestamps
        timestamps = generate_youtube_timestamps(tracks, crossfade_duration_s)

    description = format_youtube_description(timestamps, title)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(description)
        f.write("\n")  # Ensure file ends with newline
