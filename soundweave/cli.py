"""CLI argument parsing and pre-flight validation."""

import argparse
import sys
from pathlib import Path

from soundweave.config import PipelineConfig
from soundweave.utils.validators import (
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
        prog="soundweave",
        description="Random soundtrack selector and YouTube video generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic: Random 20 tracks with video
  python -m soundweave --input input --output output --image cover.png

  # Select specific number of tracks
  python -m soundweave --input input --output output --image cover.png --num-tracks 30

  # Just audio, no video
  python -m soundweave --input input --output output

  # Custom crossfade duration
  python -m soundweave --input input --output output --fade-ms 5000
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
        "--image",
        type=Path,
        help="Static image for video (omit to skip video rendering)"
    )

    # Audio processing
    parser.add_argument(
        "--fade-ms",
        type=int,
        default=3000,
        help="Crossfade duration in milliseconds (default: 3000 = 3 seconds)"
    )
    parser.add_argument(
        "--num-tracks",
        type=int,
        default=20,
        help="Number of random tracks to select (default: 20)"
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
        static_image=args.image,
        fade_ms=args.fade_ms,
        num_tracks=args.num_tracks,
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
    validate_asset_path(config.static_image, "Static image")
    if config.static_image:
        print(f"✓ Static image: {config.static_image}")

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
        from soundweave.pipeline import Pipeline
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
