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

    Process (production-grade, taste-driven):
        1. Optional: Loop and mix texture at texture_gain_db
        2. Optional: Loop and mix drums (with delay) at drums_gain_db
        3. Apply EQ: highpass @ highpass_hz, lowpass @ lowpass_hz
        4. Optional: Apply subtle saturation (warmth, not distortion)
        5. Optional: Apply gentle compression (slow, transparent)
        6. Apply limiter @ -1dB (safety only, should rarely trigger)
        7. Encode to MP3 (320kbps CBR)

    Philosophy: Restraint > layers. Default (no saturation/compression) = warm, natural.

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

    # Log tempo control
    if config.tempo_factor != 1.0:
        speed_pct = int((1.0 - config.tempo_factor) * 100)
        logger.info(f"Tempo: {config.tempo_factor:.2f}x speed ({speed_pct}% slower, café vibe)")
    else:
        logger.info("Tempo: 1.0x (original speed)")

    logger.info(f"Highpass: {config.highpass_hz}Hz")
    logger.info(f"Lowpass: {config.lowpass_hz}Hz")

    # Log reverb
    if config.enable_reverb:
        logger.info("Reverb: Enabled (café ambience)")
    else:
        logger.info("Reverb: Disabled")

    # Log optional saturation
    if config.enable_saturation:
        logger.info("Saturation: Enabled (subtle warmth)")
    else:
        logger.info("Saturation: Disabled")

    # Log optional compression
    if config.enable_compression:
        logger.info(
            f"Compression: Enabled ({config.comp_ratio}:1 ratio, "
            f"{config.comp_threshold_db}dB threshold, "
            f"{config.comp_attack_ms}ms attack, {config.comp_release_ms}ms release)"
        )
    else:
        logger.info("Compression: Disabled")

    logger.info("Limiter: -1dB (safety)")

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
