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
  # All tracks in order (no shuffle)
  python -m soundweave --input input --output output --no-shuffle

  # Random 20 tracks with video
  python -m soundweave --input input --output output --image cover.png --num-tracks 20

  # All tracks, shuffled, with video
  python -m soundweave --input input --output output --image cover.png

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
        default=None,
        help="Number of tracks to select (default: all tracks)"
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_true",
        help="Disable shuffling - keep original/natural order"
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
        shuffle=not args.no_shuffle,
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


def parse_loop_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments for the 'loop' subcommand.

    Args:
        argv: Argument list (defaults to sys.argv[2:] — after the 'loop' token).

    Returns:
        Parsed namespace with: input_file, count, gap_ms, output.
    """
    parser = argparse.ArgumentParser(
        prog="soundweave loop",
        description="Loop a single audio file N times with fade/silence between reps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Loop mysong.mp3 five times with default 3.5s gap
  soundweave loop mysong.mp3 --count 5

  # Custom gap of 4 seconds
  soundweave loop mysong.mp3 --count 3 --gap-ms 4000

  # Write output to a specific directory
  soundweave loop mysong.mp3 --count 10 --output /tmp/looped

Output filename: <stem>_x<N>.mp3  (e.g. mysong_x5.mp3)
        """
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="Audio file to loop (.mp3, .wav, .m4a, .flac)"
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of times to play the file (must be >= 1)"
    )
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=3500,
        dest="gap_ms",
        help="Silence between repetitions in milliseconds (default: 3500)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: same directory as input file)"
    )
    parser.add_argument(
        "--trim-db",
        type=float,
        default=-40.0,
        dest="trim_db",
        help=(
            "dB threshold for trimming the quiet tail of each repetition "
            "before inserting the gap (default: -40). "
            "Raises the threshold to trim more of a gradual wind-down, "
            "e.g. --trim-db -25."
        )
    )

    return parser.parse_args(argv)


def _run_loop_subcommand(argv: list[str]) -> int:
    """Handle the 'loop' subcommand.

    Args:
        argv: Arguments after the 'loop' token (i.e. sys.argv[2:]).

    Returns:
        Exit code.
    """
    from soundweave.ffmpeg.executor import ProcessingError
    from soundweave.logging.logger import setup_logger
    from soundweave.loop_config import LoopConfig
    from soundweave.stages.loop import loop_stage

    try:
        args = parse_loop_args(argv)
        config = LoopConfig(
            input_file=args.input_file,
            count=args.count,
            gap_ms=args.gap_ms,
            output_dir=args.output,
            trim_db=args.trim_db,
        )

        logger = setup_logger(config.output_dir / "loop_log.txt")

        logger.info("=" * 60)
        logger.info("Soundweave - Loop Subcommand")
        logger.info("=" * 60)
        logger.info(f"Run ID:    {config.run_id}")
        logger.info(f"Timestamp: {config.timestamp}")
        logger.info("")

        output_path = loop_stage(config, logger)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Loop completed successfully!")
        logger.info(f"Output: {output_path}")
        logger.info("=" * 60)

        return 0

    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ProcessingError as e:
        print(f"PROCESSING ERROR: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


def parse_mashup_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments for the 'mashup' subcommand.

    Args:
        argv: Argument list (defaults to sys.argv[2:] — after the 'mashup' token).

    Returns:
        Parsed namespace with: urls, output, fade_ms, shuffle, strict, cache_dir.
    """
    from soundweave.mashup_config import DEFAULT_FADE_MS

    parser = argparse.ArgumentParser(
        prog="soundweave mashup",
        description=(
            "Download audio from a list of YouTube URLs and crossfade them "
            "into one longplay (reuses the existing merge/MP3 pipeline)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download & merge, tracks played in the order listed in urls.txt
  soundweave mashup --urls urls.txt --output output

  # Randomize order instead of using the listed order
  soundweave mashup --urls urls.txt --output output --shuffle

  # Custom crossfade duration
  soundweave mashup --urls urls.txt --output output --fade-ms 5000

  # Abort on the first unavailable/failed URL instead of skipping it
  soundweave mashup --urls urls.txt --output output --strict

urls.txt format: one YouTube URL per line, '#' comments, blank lines ignored
(same convention as order.txt).
        """
    )

    parser.add_argument(
        "--urls",
        type=Path,
        required=True,
        help="Path to urls.txt (one YouTube URL per line)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for output files"
    )
    parser.add_argument(
        "--fade-ms",
        type=int,
        default=DEFAULT_FADE_MS,
        dest="fade_ms",
        help=f"Crossfade duration in milliseconds (default: {DEFAULT_FADE_MS} = 4.5 seconds)"
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomize track order (default: play in the order listed in urls.txt)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Abort the run on the first failed/unavailable URL instead of "
            "skipping it with a warning"
        )
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        dest="cache_dir",
        help="Directory for cached yt-dlp downloads, keyed by video ID (default: .cache/youtube)"
    )

    return parser.parse_args(argv)


def _run_mashup_subcommand(argv: list[str]) -> int:
    """Handle the 'mashup' subcommand.

    Args:
        argv: Arguments after the 'mashup' token (i.e. sys.argv[2:]).

    Returns:
        Exit code.
    """
    from soundweave.ffmpeg.commands import build_mp3_command
    from soundweave.ffmpeg.executor import ProcessingError, run_ffmpeg
    from soundweave.ffmpeg.probe import probe_loudnorm_duration
    from soundweave.logging.logger import setup_logger
    from soundweave.mashup_config import MashupConfig
    from soundweave.stages.download import download_stage
    from soundweave.stages.merge import merge_stage
    from soundweave.utils.youtube import write_youtube_description
    from soundweave.ytdlp.executor import YtDlpError

    try:
        args = parse_mashup_args(argv)
        config = MashupConfig(
            urls_file=args.urls,
            output_dir=args.output,
            fade_ms=args.fade_ms,
            shuffle=args.shuffle,
            strict=args.strict,
            cache_dir=args.cache_dir,
        )

        logger = setup_logger(config.output_dir / "mashup_log.txt")

        logger.info("=" * 60)
        logger.info("Soundweave - Mashup Subcommand")
        logger.info("=" * 60)
        logger.info(f"Run ID:    {config.run_id}")
        logger.info(f"Timestamp: {config.timestamp}")
        logger.info("")

        # Stage 0: Download (new)
        tracks = download_stage(config, logger)
        logger.info("")

        # Stage 2: Merge with crossfades (reused, unmodified)
        merged_clean = merge_stage(tracks, config, logger)
        logger.info("")

        # Stage 3: MP3 encoding & YouTube timestamps (reused pattern from
        # pipeline.py's inline Stage 3 — same commands, same accurate
        # post-loudnorm timestamp measurement)
        logger.info("=== Stage 3: MP3 Encoding & YouTube Timestamps ===")

        merged_mp3 = config.output_dir / "merged.mp3"
        mp3_cmd = build_mp3_command(merged_clean, merged_mp3)

        logger.info("Encoding to MP3 (320kbps)...")
        run_ffmpeg(mp3_cmd, logger, description="MP3 encoding (320kbps CBR)", timeout=None)

        mp3_size_mb = merged_mp3.stat().st_size / (1024 ** 2)
        logger.info(f"  {merged_mp3.name} ({mp3_size_mb:.1f}MB)")

        crossfade_s = config.fade_ms / 1000.0
        description_path = config.output_dir / "youtube_description.txt"

        logger.info("Measuring actual track durations (post-loudnorm)...")
        actual_timestamps = [0.0]
        current_time = 0.0

        for i, track in enumerate(tracks):
            try:
                actual_duration = probe_loudnorm_duration(track.path)
                diff = actual_duration - track.duration_s
                logger.info(
                    f"  [{i + 1}] {track.filename}: "
                    f"{track.duration_s:.2f}s -> {actual_duration:.2f}s "
                    f"({'+' if diff >= 0 else ''}{diff:.2f}s)"
                )
                if i < len(tracks) - 1:
                    current_time += actual_duration - crossfade_s
                    actual_timestamps.append(current_time)
            except Exception as e:
                logger.warning(f"  Failed to measure {track.filename}: {e}")
                if i < len(tracks) - 1:
                    current_time += track.duration_s - crossfade_s
                    actual_timestamps.append(current_time)

        logger.info("Generating YouTube timestamps...")
        write_youtube_description(
            description_path,
            tracks,
            crossfade_s,
            title="Tracklist",
            actual_timestamps=(
                actual_timestamps if len(actual_timestamps) == len(tracks) else None
            ),
        )
        logger.info(f"  {description_path.name}")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Mashup completed successfully!")
        logger.info(f"Output:      {merged_mp3}")
        logger.info(f"Description: {description_path}")
        logger.info("=" * 60)

        return 0

    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (ProcessingError, YtDlpError) as e:
        print(f"PROCESSING ERROR: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0=success, 1=validation error, 2=processing error, 3=output error)
    """
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        return _run_loop_subcommand(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "mashup":
        return _run_mashup_subcommand(sys.argv[2:])

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
