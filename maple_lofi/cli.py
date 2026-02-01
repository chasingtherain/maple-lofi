"""CLI argument parsing and pre-flight validation."""

import argparse
import sys
from pathlib import Path

from maple_lofi.config import PipelineConfig
from maple_lofi.utils.validators import (
    ValidationError,
    estimate_disk_space_needed,
    validate_asset_path,
    validate_disk_space,
    validate_ffmpeg,
    validate_input_directory,
    validate_output_directory,
    validate_python_version,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="maple_lofi",
        description="MapleStory BGM → lofi YouTube longplay pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic (EQ only - warm, natural)
  python -m maple_lofi --input input --output output

  # With subtle warmth (adds saturation)
  python -m maple_lofi --input input --output output --enable-saturation

  # Full lofi (EQ + saturation + gentle compression)
  python -m maple_lofi --input input --output output \\
    --enable-saturation --enable-compression

  # With video and custom assets
  python -m maple_lofi \\
    --input input \\
    --output output \\
    --cover assets/cover.png \\
    --texture assets/rain.wav \\
    --drums assets/drums.wav --drums-start 20 \\
    --enable-saturation

  # Skip lofi (just merge tracks)
  python -m maple_lofi --input input --output output --skip-lofi
        """
    )

    # Required arguments
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Directory containing input audio files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for output files"
    )

    # Optional: Video
    parser.add_argument(
        "--cover",
        type=Path,
        help="Cover image for video (omit to skip video rendering)"
    )

    # Optional: Lofi assets
    parser.add_argument(
        "--texture",
        type=Path,
        help="Ambient texture audio file (e.g., rain.wav)"
    )
    parser.add_argument(
        "--texture-gain",
        type=float,
        default=-26.0,
        help="Texture volume in dB (default: -26)"
    )
    parser.add_argument(
        "--drums",
        type=Path,
        help="Drum loop audio file"
    )
    parser.add_argument(
        "--drums-gain",
        type=float,
        default=-22.0,
        help="Drums volume in dB (default: -22)"
    )
    parser.add_argument(
        "--drums-start",
        type=float,
        default=0.0,
        help="Drums start delay in seconds (default: 0)"
    )

    # Optional: Audio processing
    parser.add_argument(
        "--fade-ms",
        type=int,
        default=15000,
        help="Crossfade duration in milliseconds (default: 15000)"
    )
    parser.add_argument(
        "--highpass",
        type=int,
        default=35,
        help="High-pass filter frequency in Hz (default: 35)"
    )
    parser.add_argument(
        "--lowpass",
        type=int,
        default=9500,
        help="Low-pass filter frequency in Hz (default: 9500 for warmth)"
    )

    # Lofi processing options
    parser.add_argument(
        "--enable-compression",
        action="store_true",
        help="Enable gentle compression (off by default, restraint > layers)"
    )
    parser.add_argument(
        "--enable-saturation",
        action="store_true",
        help="Enable subtle saturation for warmth (off by default)"
    )

    # Advanced compression tuning (for power users)
    parser.add_argument(
        "--comp-ratio",
        type=float,
        default=2.0,
        help="Compression ratio (default: 2.0)"
    )
    parser.add_argument(
        "--comp-threshold",
        type=float,
        default=-23.0,
        help="Compression threshold in dB (default: -23.0)"
    )
    parser.add_argument(
        "--comp-attack",
        type=float,
        default=25.0,
        help="Compression attack in ms (default: 25.0)"
    )
    parser.add_argument(
        "--comp-release",
        type=float,
        default=200.0,
        help="Compression release in ms (default: 200.0)"
    )

    # Flags
    parser.add_argument(
        "--skip-lofi",
        action="store_true",
        help="Skip lofi transformation stage entirely"
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Build PipelineConfig from parsed arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        PipelineConfig instance
    """
    return PipelineConfig(
        input_dir=args.input,
        output_dir=args.output,
        cover_image=args.cover,
        texture=args.texture,
        drums=args.drums,
        fade_ms=args.fade_ms,
        highpass_hz=args.highpass,
        lowpass_hz=args.lowpass,
        texture_gain_db=args.texture_gain,
        drums_gain_db=args.drums_gain,
        drums_start_s=args.drums_start,
        enable_compression=args.enable_compression,
        enable_saturation=args.enable_saturation,
        comp_ratio=args.comp_ratio,
        comp_threshold_db=args.comp_threshold,
        comp_attack_ms=args.comp_attack,
        comp_release_ms=args.comp_release,
        skip_lofi=args.skip_lofi,
    )


def run_preflight_checks(config: PipelineConfig) -> None:
    """Run all pre-flight validation checks.

    Args:
        config: Pipeline configuration

    Raises:
        ValidationError: If any validation fails
    """
    print("Running pre-flight checks...")

    # Check Python version
    validate_python_version()
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")

    # Check FFmpeg
    ffmpeg_version = validate_ffmpeg()
    print(f"✓ FFmpeg {ffmpeg_version}")

    # Check input directory
    validate_input_directory(config.input_dir)
    print(f"✓ Input directory: {config.input_dir}")

    # Check output directory (create if needed)
    validate_output_directory(config.output_dir)
    print(f"✓ Output directory: {config.output_dir}")

    # Check optional assets
    validate_asset_path(config.cover_image, "Cover image")
    if config.cover_image:
        print(f"✓ Cover image: {config.cover_image}")

    validate_asset_path(config.texture, "Texture")
    if config.texture:
        print(f"✓ Texture: {config.texture}")

    validate_asset_path(config.drums, "Drums")
    if config.drums:
        print(f"✓ Drums: {config.drums}")

    # Check disk space
    needed_bytes = estimate_disk_space_needed(config.input_dir)
    validate_disk_space(config.output_dir, needed_bytes)
    needed_gb = needed_bytes / (1024**3)
    print(f"✓ Estimated disk space needed: ~{needed_gb:.2f}GB")

    print("All pre-flight checks passed!\n")


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0=success, 1=validation error, 2=processing error, 3=output error)
    """
    try:
        args = parse_args()
        config = build_config(args)
        run_preflight_checks(config)

        # Run the pipeline
        from maple_lofi.pipeline import Pipeline
        pipeline = Pipeline(config)
        return pipeline.run()

    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2
