"""Stage 4: Video - Render static video with cover image and audio.

Also provides the per-track image-swap mode (PRD.md §7): instead of one
static image for the whole runtime, a sequence of images is shown, each
held on screen for its own track's duration. See `video_sequence_stage()`,
`match_images_to_tracks()`, and `calculate_sequence_duration()` below.
Not yet wired into the CLI/pipeline -- callers construct the
`(image_path, duration_s)` sequence by hand for now.
"""

import logging
import shutil
from pathlib import Path

from soundweave.config import PipelineConfig
from soundweave.ffmpeg.commands import build_video_command, build_video_sequence_command
from soundweave.ffmpeg.executor import run_ffmpeg
from soundweave.ffmpeg.probe import probe_audio_file
from soundweave.utils.validators import ValidationError


def video_stage(
    audio_path: Path,
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Stage 4: Render static video with static image.

    Args:
        audio_path: Path to final audio (merged.wav)
        config: Pipeline configuration
        logger: Logger instance

    Returns:
        Path to final_video.mp4

    Process:
        1. Probe audio duration
        2. Scale/pad static image to 1920x1080 (preserve aspect, letterbox)
        3. Render static video:
           - 1fps (minimal file size)
           - H.264 (yuv420p, high profile)
           - AAC audio (192kbps)
        4. Copy static image to output/thumbnail.{png,jpg}

    Output format:
        - 1920x1080, 1fps
        - Duration matches audio exactly
        - YouTube-ready quality
    """
    logger.info("=== Stage 4: Video Rendering ===")

    if not config.static_image:
        logger.info("No static image specified, skipping video rendering")
        return None

    logger.info(f"Static image: {config.static_image.name}")

    # Probe audio to get duration
    logger.info("Probing audio duration...")
    audio_metadata = probe_audio_file(audio_path)
    duration_s = audio_metadata.duration_s
    logger.info(f"Audio duration: {duration_s:.2f}s")

    # Build output path
    output_path = config.output_dir / "final_video.mp4"

    # Build FFmpeg command
    command = build_video_command(
        audio_path,
        config.static_image,
        output_path,
        duration_s
    )

    # Execute
    logger.info("Rendering video (this may take a while for long audio)...")
    run_ffmpeg(
        command,
        logger,
        description="Video rendering with static image",
        timeout=None,
        total_duration_s=duration_s,
    )

    video_size_mb = output_path.stat().st_size / (1024 ** 2)
    logger.info(f"  ✓ {output_path.name} ({video_size_mb:.1f}MB)")

    # Copy static image to output as thumbnail
    thumbnail_ext = config.static_image.suffix  # .png or .jpg
    thumbnail_path = config.output_dir / f"thumbnail{thumbnail_ext}"

    logger.info(f"Copying static image to {thumbnail_path.name}...")
    shutil.copy2(config.static_image, thumbnail_path)

    logger.info("Video rendering complete")

    return output_path


def match_images_to_tracks(
    images: list[Path],
    track_durations: list[float],
) -> list[tuple[Path, float]]:
    """Pair ordered images with ordered per-track durations for a video sequence.

    This is the pre-flight validation step for per-track image-swap video
    rendering (PRD.md §7): the caller supplies images (e.g. discovered from
    an `--images` directory, matched by order or filename prefix -- that
    matching logic belongs to the eventual CLI/mashup integration, not
    here) and the actual measured duration of each track (the same
    durations already computed elsewhere for YouTube chapter timestamps).
    This function pairs them 1:1, in track order, and enforces the "don't
    silently reuse/loop images" rule from the PRD.

    Args:
        images: Ordered list of image file paths, one intended per track.
        track_durations: Ordered list of per-track durations in seconds,
            in the same order as the tracks they belong to.

    Returns:
        Ordered list of (image_path, duration_s) pairs, one per track,
        suitable for passing to `video_sequence_stage()`. If more images
        are supplied than tracks, the extras are dropped -- only the first
        len(track_durations) images are used.

    Raises:
        ValidationError: If fewer images are supplied than tracks. Per
            PRD.md §7 this is a hard pre-flight error: "error at pre-flight
            (explicit is better than silently reusing/looping)".
    """
    if len(images) < len(track_durations):
        raise ValidationError(
            f"Not enough images for per-track video sequence: "
            f"{len(images)} image(s) provided for {len(track_durations)} track(s). "
            "Provide at least one image per track (e.g. via --images)."
        )

    return list(zip(images[: len(track_durations)], track_durations))


def calculate_sequence_duration(image_sequence: list[tuple[Path, float]]) -> float:
    """Sum the per-image hold durations to get the total sequence duration.

    Args:
        image_sequence: Ordered list of (image_path, duration_s) pairs

    Returns:
        Total duration in seconds (0.0 for an empty sequence)
    """
    return sum(duration_s for _, duration_s in image_sequence)


def video_sequence_stage(
    audio_path: Path,
    image_sequence: list[tuple[Path, float]],
    output_dir: Path,
    logger: logging.Logger,
) -> Path:
    """Stage 4 (alternate mode): render video with a per-track image swap.

    Companion to `video_stage()` for the mashup "per-track images" mode
    (PRD.md §7). Instead of one static image for the whole runtime, each
    image in `image_sequence` holds on screen for its own duration, in
    order, hard-cutting to the next -- total duration matches the sum of
    the per-image durations. Does not change `video_stage()`'s behavior;
    this is an additive, independent entry point.

    Not yet wired into the CLI: `image_sequence` must be built by the
    caller (see `match_images_to_tracks()` to pair a raw image list with
    per-track durations and get the pre-flight fewer-images-than-tracks
    check for free).

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        image_sequence: Ordered list of (image_path, duration_s) pairs, one
            per track. Must be non-empty.
        output_dir: Directory to write final_video.mp4 (and thumbnail) into
        logger: Logger instance

    Returns:
        Path to final_video.mp4

    Raises:
        ValidationError: If `image_sequence` is empty.

    Output format:
        - 1920x1080, 1fps -- matches `video_stage()`'s output settings
        - Total duration = sum of per-image durations in image_sequence
        - YouTube-ready quality
    """
    logger.info("=== Stage 4: Video Rendering (per-track image sequence) ===")

    if not image_sequence:
        raise ValidationError("Cannot render a video sequence with zero images")

    total_duration_s = calculate_sequence_duration(image_sequence)
    logger.info(
        f"Image sequence: {len(image_sequence)} image(s), "
        f"total duration {total_duration_s:.2f}s"
    )

    # Sanity-check against the actual audio duration. Not a hard failure --
    # durations are typically fed in from measured (but imperfect) per-track
    # probes -- but a large drift is worth flagging.
    audio_metadata = probe_audio_file(audio_path)
    drift_s = abs(audio_metadata.duration_s - total_duration_s)
    if drift_s > 1.0:
        logger.warning(
            f"Image sequence duration ({total_duration_s:.2f}s) differs from "
            f"audio duration ({audio_metadata.duration_s:.2f}s) by {drift_s:.2f}s"
        )

    output_path = output_dir / "final_video.mp4"

    command = build_video_sequence_command(audio_path, image_sequence, output_path)

    logger.info("Rendering video sequence (this may take a while for long audio)...")
    run_ffmpeg(
        command,
        logger,
        description="Video rendering with per-track image sequence",
        timeout=None,
        total_duration_s=total_duration_s,
    )

    video_size_mb = output_path.stat().st_size / (1024 ** 2)
    logger.info(f"  ✓ {output_path.name} ({video_size_mb:.1f}MB)")

    # Copy the first image in the sequence to output as thumbnail
    first_image = image_sequence[0][0]
    thumbnail_path = output_dir / f"thumbnail{first_image.suffix}"
    logger.info(f"Copying first sequence image to {thumbnail_path.name}...")
    shutil.copy2(first_image, thumbnail_path)

    logger.info("Video rendering complete")

    return output_path
