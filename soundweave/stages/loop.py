"""Stage: Loop — Repeat a single audio file N times with fade/silence gaps."""

import logging
import time
from pathlib import Path

from soundweave.ffmpeg.commands import build_loop_command
from soundweave.ffmpeg.executor import ProcessingError, run_ffmpeg
from soundweave.ffmpeg.probe import probe_audio_file
from soundweave.loop_config import AUDIO_EXTENSIONS, LoopConfig
from soundweave.utils.validators import ValidationError


def validate_loop_input(config: LoopConfig) -> None:
    """Validate all inputs for the loop subcommand.

    Raises:
        ValidationError: On any validation failure.
    """
    if not config.input_file.exists():
        raise ValidationError(f"Input file not found: {config.input_file}")
    if not config.input_file.is_file():
        raise ValidationError(f"Input path is not a file: {config.input_file}")

    suffix = config.input_file.suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValidationError(
            f"Unsupported audio format '{suffix}'. "
            f"Supported: {', '.join(sorted(AUDIO_EXTENSIONS))}"
        )

    if config.count < 1:
        raise ValidationError(f"--count must be >= 1, got {config.count}")

    if config.gap_ms < 0:
        raise ValidationError(f"--gap-ms must be >= 0, got {config.gap_ms}")

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValidationError(
            f"Cannot create output directory: {config.output_dir}"
        )

    if config.output_path.resolve() == config.input_file.resolve():
        raise ValidationError(
            f"Output path {config.output_path} would overwrite input file."
        )


def loop_stage(config: LoopConfig, logger: logging.Logger) -> Path:
    """Execute the loop subcommand.

    Args:
        config: LoopConfig with all parameters.
        logger: Logger instance.

    Returns:
        Path to the output MP3 file.

    Raises:
        ValidationError: If inputs are invalid.
        ProcessingError: If FFmpeg fails.
    """
    logger.info("=== Loop Stage ===")
    logger.info(f"Input:    {config.input_file}")
    logger.info(f"Count:    {config.count}x")
    logger.info(f"Gap:      {config.gap_ms}ms ({config.gap_s:.2f}s)")
    logger.info(f"Fade:     {config.fade_s}s in + {config.fade_s}s out per rep")
    logger.info(f"Trim:     trailing audio below {config.trim_db}dB removed per rep")
    logger.info(f"Output:   {config.output_path}")

    validate_loop_input(config)
    logger.info("Input validation passed")

    logger.info(f"Probing {config.input_file.name}...")
    metadata = probe_audio_file(config.input_file)
    logger.info(
        f"  Duration: {metadata.duration_s:.3f}s, "
        f"{metadata.sample_rate}Hz, "
        f"{metadata.channels}ch, "
        f"{metadata.codec}"
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)

    command = build_loop_command(
        input_file=config.input_file,
        output_path=config.output_path,
        count=config.count,
        gap_s=config.gap_s,
        fade_s=config.fade_s,
        trim_db=config.trim_db,
    )

    logger.info("Running FFmpeg loop command...")
    start = time.time()
    run_ffmpeg(
        command,
        logger,
        description=f"Loop {config.input_file.name} x{config.count}",
        timeout=None,
    )
    elapsed = time.time() - start
    logger.info(f"FFmpeg completed in {elapsed:.1f}s")

    if not config.output_path.exists():
        raise ProcessingError(
            f"Loop stage: output file not created: {config.output_path}"
        )

    size_mb = config.output_path.stat().st_size / (1024 ** 2)
    logger.info(f"Output: {config.output_path.name} ({size_mb:.1f}MB)")
    logger.info("Loop stage complete.")

    return config.output_path
