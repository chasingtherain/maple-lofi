"""Stage 2: Merge - Crossfade merging of audio tracks."""

import logging
from pathlib import Path

from maple_lofi.config import PipelineConfig
from maple_lofi.ffmpeg.commands import build_merge_command
from maple_lofi.ffmpeg.executor import run_ffmpeg
from maple_lofi.stages.ingest import AudioTrack


def calculate_crossfade_durations(
    tracks: list[AudioTrack],
    default_crossfade_s: float,
    logger: logging.Logger
) -> list[float]:
    """Calculate crossfade duration for each pair of tracks.

    Args:
        tracks: List of audio tracks
        default_crossfade_s: Default crossfade duration in seconds
        logger: Logger for warnings

    Returns:
        List of crossfade durations (one less than number of tracks)

    Logic (from SPECIFICATION.md):
        - Default: use default_crossfade_s
        - If track duration < crossfade: reduce to 50% of track duration
        - Minimum effective crossfade: 1 second
    """
    if len(tracks) <= 1:
        return []

    crossfades = []

    for i in range(len(tracks) - 1):
        track1 = tracks[i]
        track2 = tracks[i + 1]

        # Find the shorter of the two tracks
        min_duration = min(track1.duration_s, track2.duration_s)

        # Calculate crossfade duration
        if min_duration < default_crossfade_s:
            # Reduce to 50% of shorter track duration
            crossfade_s = max(1.0, min_duration * 0.5)
            logger.warning(
                f"Track '{track1.filename if track1.duration_s < track2.duration_s else track2.filename}' "
                f"duration ({min_duration:.1f}s) < crossfade ({default_crossfade_s:.1f}s), "
                f"reduced to {crossfade_s:.1f}s"
            )
        else:
            crossfade_s = default_crossfade_s

        crossfades.append(crossfade_s)

    return crossfades


def merge_stage(
    tracks: list[AudioTrack],
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Stage 2: Merge tracks with crossfades into a single file.

    Args:
        tracks: Ordered list of audio tracks
        config: Pipeline configuration
        logger: Logger instance

    Returns:
        Path to merged_clean.wav

    Process:
        1. Calculate crossfade durations (handle short tracks)
        2. Build FFmpeg filter_complex for sequential crossfades
        3. Execute FFmpeg command
        4. Verify output exists

    Output format:
        - 48kHz, 16-bit PCM, stereo
        - No gaps or hard cuts between tracks
    """
    logger.info("=== Stage 2: Merge ===")
    logger.info(f"Merging {len(tracks)} track(s) with crossfades...")

    # Calculate crossfade durations
    default_crossfade_s = config.fade_ms / 1000.0
    crossfades = calculate_crossfade_durations(tracks, default_crossfade_s, logger)

    if crossfades:
        logger.info(
            f"Crossfade durations: "
            f"min={min(crossfades):.1f}s, max={max(crossfades):.1f}s, avg={sum(crossfades)/len(crossfades):.1f}s"
        )

    # Build output path
    output_path = config.output_dir / "merged_clean.wav"

    # Build FFmpeg command
    command = build_merge_command(tracks, output_path, crossfades)

    # Execute
    run_ffmpeg(
        command,
        logger,
        description=f"Merging {len(tracks)} tracks with crossfades",
        timeout=None  # No timeout for long merges
    )

    # Verify output
    if not output_path.exists():
        from maple_lofi.ffmpeg.executor import ProcessingError
        raise ProcessingError("merge: Output file not created")

    file_size_mb = output_path.stat().st_size / (1024 ** 2)
    logger.info(f"Merge complete: {output_path.name} ({file_size_mb:.1f}MB)")

    return output_path
