"""Stage 4: Video - Render static video with cover image and audio."""

import logging
import shutil
from pathlib import Path

from maple_lofi.config import PipelineConfig
from maple_lofi.ffmpeg.commands import build_video_command
from maple_lofi.ffmpeg.executor import run_ffmpeg
from maple_lofi.ffmpeg.probe import probe_audio_file


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
        timeout=None
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
