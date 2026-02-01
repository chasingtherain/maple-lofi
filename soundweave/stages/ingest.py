"""Stage 1: Ingest - File discovery and ordering."""

import logging
from dataclasses import dataclass
from pathlib import Path

from soundweave.config import PipelineConfig
from soundweave.ffmpeg.probe import probe_audio_file
from soundweave.utils.natural_sort import natural_sort
from soundweave.utils.validators import ValidationError


# Supported audio file extensions
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".mpeg"}


@dataclass
class AudioTrack:
    """Represents a single audio track with metadata."""

    path: Path
    filename: str
    duration_s: float
    sample_rate: int
    channels: int
    codec: str


def discover_audio_files(input_dir: Path) -> list[Path]:
    """Scan input directory for audio files (top-level only).

    Args:
        input_dir: Directory to scan

    Returns:
        List of audio file paths

    Raises:
        ValidationError: If no audio files found
    """
    audio_files = []

    for ext in AUDIO_EXTENSIONS:
        for file_path in input_dir.glob(f"*{ext}"):
            if file_path.is_file():
                audio_files.append(file_path)

    if not audio_files:
        raise ValidationError(
            f"No audio files found in {input_dir}. "
            f"Supported formats: {', '.join(sorted(AUDIO_EXTENSIONS))}"
        )

    return audio_files


def parse_order_file(order_file: Path) -> list[str]:
    """Parse order.txt file to get ordered list of filenames.

    Args:
        order_file: Path to order.txt

    Returns:
        List of filenames (may include duplicates)

    Format:
        - One filename per line (with extension)
        - Lines starting with # are ignored (comments)
        - Blank lines are ignored
        - Duplicates allowed (will be processed twice)

    Examples:
        track1.mp3
        track2.mp3
        track3.mp3
    """
    ordered_tracks = []

    with open(order_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            # Strip whitespace
            line = line.strip()

            # Skip blank lines and comments
            if not line or line.startswith("#"):
                continue

            # Split on whitespace to get filename only
            filename = line.split()[0]

            # Just the filename, no paths
            if "/" in filename or "\\" in filename:
                raise ValidationError(
                    f"order.txt line {line_num}: Paths not allowed, "
                    f"only filenames (got: {filename})"
                )

            ordered_tracks.append(filename)

    return ordered_tracks


def validate_ordering(
    ordered_filenames: list[str],
    available_files: set[str],
    logger: logging.Logger
) -> None:
    """Validate that order.txt lists all available files (and only those).

    Args:
        ordered_filenames: Filenames from order.txt (may have duplicates)
        available_files: Set of actual filenames in input directory
        logger: Logger for warnings

    Raises:
        ValidationError: If order.txt is inconsistent with available files

    Rules (from SPECIFICATION.md):
        - If order.txt exists, it MUST list all audio files
        - Missing files in order.txt → Error
        - Extra files in order.txt (not in input dir) → Error
        - Duplicates allowed (same file processed multiple times)
    """
    # Get unique filenames from order.txt (to check coverage)
    unique_ordered = set(ordered_filenames)

    # Check for files in order.txt but not in input directory
    extra_in_order = unique_ordered - available_files
    if extra_in_order:
        raise ValidationError(
            f"order.txt lists files not found in input directory: "
            f"{', '.join(sorted(extra_in_order))}"
        )

    # Check for files in input directory but not in order.txt
    missing_from_order = available_files - unique_ordered
    if missing_from_order:
        raise ValidationError(
            f"order.txt is missing files from input directory: "
            f"{', '.join(sorted(missing_from_order))}"
        )

    # Log duplicates (allowed, but worth noting)
    if len(ordered_filenames) != len(unique_ordered):
        duplicates = [f for f in ordered_filenames if ordered_filenames.count(f) > 1]
        unique_dupes = set(duplicates)
        logger.info(
            f"order.txt contains duplicates (will be processed multiple times): "
            f"{', '.join(sorted(unique_dupes))}"
        )


def determine_track_order(
    input_dir: Path,
    audio_files: list[Path],
    logger: logging.Logger
) -> list[str]:
    """Determine playback order for audio files.

    Args:
        input_dir: Input directory
        audio_files: List of discovered audio files
        logger: Logger for info/warnings

    Returns:
        Ordered list of filenames

    Logic:
        1. If order.txt exists: use it (and validate)
        2. Otherwise: natural sort by filename
    """
    order_file = input_dir / "order.txt"
    available_filenames = {f.name for f in audio_files}

    if order_file.exists():
        logger.info(f"Using order.txt for track ordering")
        ordered_filenames = parse_order_file(order_file)
        validate_ordering(ordered_filenames, available_filenames, logger)
        return ordered_filenames
    else:
        logger.info("No order.txt found, using natural sort by filename")
        return natural_sort(list(available_filenames))


def probe_track(file_path: Path, logger: logging.Logger) -> AudioTrack | None:
    """Probe a single audio file and create AudioTrack.

    Args:
        file_path: Path to audio file
        logger: Logger for warnings

    Returns:
        AudioTrack if successful, None if file is corrupted
    """
    try:
        metadata = probe_audio_file(file_path)
        return AudioTrack(
            path=file_path,
            filename=file_path.name,
            duration_s=metadata.duration_s,
            sample_rate=metadata.sample_rate,
            channels=metadata.channels,
            codec=metadata.codec
        )
    except ValidationError as e:
        logger.warning(f"Skipping corrupted file {file_path.name}: {e}")
        return None


def ingest_stage(config: PipelineConfig, logger: logging.Logger) -> list[AudioTrack]:
    """Stage 1: Discover and order audio files.

    Args:
        config: Pipeline configuration
        logger: Logger instance

    Returns:
        Ordered list of AudioTrack objects (randomly selected if num_tracks specified)

    Raises:
        ValidationError: If zero valid files found after filtering

    Process:
        1. Scan input directory for audio files (top-level only)
        2. Determine ordering (order.txt or natural sort)
        3. Randomly select num_tracks if specified
        4. Probe each file for metadata
        5. Filter out corrupted files (with warnings)
        6. Return ordered list
    """
    import random

    logger.info("=== Stage 1: Ingest ===")
    logger.info(f"Scanning {config.input_dir} for audio files...")

    # Discover audio files
    audio_files = discover_audio_files(config.input_dir)
    logger.info(f"Found {len(audio_files)} audio file(s)")

    # Determine order
    ordered_filenames = determine_track_order(config.input_dir, audio_files, logger)
    logger.info(f"Track order determined: {len(ordered_filenames)} track(s) available")

    # Randomly select num_tracks if specified and fewer than available
    if config.num_tracks and config.num_tracks < len(ordered_filenames):
        logger.info(f"Randomly selecting {config.num_tracks} track(s) from {len(ordered_filenames)} available")
        ordered_filenames = random.sample(ordered_filenames, config.num_tracks)
        logger.info(f"Selected {len(ordered_filenames)} track(s) for processing")

    # Build filename → path mapping
    file_map = {f.name: f for f in audio_files}

    # Probe each track in order
    tracks = []
    for filename in ordered_filenames:
        file_path = file_map[filename]
        logger.debug(f"Probing {filename}...")

        track = probe_track(file_path, logger)
        if track:
            tracks.append(track)
            logger.info(
                f"  [{len(tracks)}] {track.filename}: "
                f"{track.duration_s:.1f}s, {track.sample_rate}Hz, "
                f"{track.channels}ch, {track.codec}"
            )

    # Verify we have at least one valid track
    if not tracks:
        raise ValidationError("No valid audio tracks found after filtering")

    total_duration = sum(t.duration_s for t in tracks)
    logger.info(f"Ingest complete: {len(tracks)} track(s), total {total_duration:.1f}s")

    return tracks
