"""Stage 3: Lofi - Apply lofi aesthetic transformation."""

import logging
from pathlib import Path

from maple_lofi.config import PipelineConfig
from maple_lofi.ffmpeg.commands import build_lofi_command
from maple_lofi.ffmpeg.executor import run_ffmpeg


def lofi_stage(
    merged_clean: Path,
    config: PipelineConfig,
    logger: logging.Logger
) -> Path:
    """Stage 3: Apply lofi transformation to merged audio.

    Args:
        merged_clean: Path to merged_clean.wav
        config: Pipeline configuration
        logger: Logger instance

    Returns:
        Path to merged_lofi.wav

    Process:
        1. Optional: Loop and mix texture at texture_gain_db
        2. Optional: Loop and mix drums (with delay) at drums_gain_db
        3. Apply highpass @ highpass_hz
        4. Apply lowpass @ lowpass_hz
        5. Apply compression (3:1, -18dB threshold)
        6. Apply limiter @ -1dB
        7. Encode to MP3 (320kbps CBR)

    Output files:
        - merged_lofi.wav (48kHz, 16-bit PCM)
        - merged_lofi.mp3 (320kbps CBR)
    """
    logger.info("=== Stage 3: Lofi Transformation ===")

    # Build output paths
    output_wav = config.output_dir / "merged_lofi.wav"
    output_mp3 = config.output_dir / "merged_lofi.mp3"

    # Log what we're doing
    if config.texture:
        logger.info(f"Texture: {config.texture.name} @ {config.texture_gain_db}dB")
    else:
        logger.info("Texture: None")

    if config.drums:
        logger.info(
            f"Drums: {config.drums.name} @ {config.drums_gain_db}dB, "
            f"start {config.drums_start_s}s"
        )
    else:
        logger.info("Drums: None")

    logger.info(f"Highpass: {config.highpass_hz}Hz")
    logger.info(f"Lowpass: {config.lowpass_hz}Hz")
    logger.info("Compression: 3:1 ratio, -18dB threshold")
    logger.info("Limiter: -1dB")

    # Build commands
    wav_cmd, mp3_cmd = build_lofi_command(
        merged_clean,
        output_wav,
        output_mp3,
        config
    )

    # Execute WAV processing
    logger.info("Processing lofi audio to WAV...")
    run_ffmpeg(
        wav_cmd,
        logger,
        description="Lofi transformation to WAV",
        timeout=None
    )

    wav_size_mb = output_wav.stat().st_size / (1024 ** 2)
    logger.info(f"  ✓ {output_wav.name} ({wav_size_mb:.1f}MB)")

    # Execute MP3 encoding
    logger.info("Encoding to MP3 (320kbps)...")
    run_ffmpeg(
        mp3_cmd,
        logger,
        description="MP3 encoding (320kbps CBR)",
        timeout=None
    )

    mp3_size_mb = output_mp3.stat().st_size / (1024 ** 2)
    logger.info(f"  ✓ {output_mp3.name} ({mp3_size_mb:.1f}MB)")

    logger.info("Lofi transformation complete")

    return output_wav
