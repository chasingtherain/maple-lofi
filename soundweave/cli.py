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
        Parsed namespace with: urls, output, fade_ms, shuffle, strict,
        cache_dir, image, images_dir, animated_background.
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

  # Single static image for the whole video
  soundweave mashup --urls urls.txt --output output --image cover.png

  # One image per track, held for that track's actual duration
  soundweave mashup --urls urls.txt --output output --images covers/

  # Looping animated background instead of a static image (e.g. output
  # from tools/ambient_bg/composite.sh)
  soundweave mashup --urls urls.txt --output output --animated-background loop.mp4

  # Preview the resolved tracklist (titles, durations, order) without
  # downloading any audio or running the rest of the pipeline
  soundweave mashup --urls urls.txt --output output --dry-run

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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help=(
            "Resolve and print the tracklist (order, titles, durations, "
            "estimated total runtime) without downloading audio or running "
            "the rest of the pipeline. No files are written under --output."
        )
    )

    image_group = parser.add_mutually_exclusive_group()
    image_group.add_argument(
        "--image",
        type=Path,
        default=None,
        dest="image",
        help="Single static image for video (omit to skip video rendering)"
    )
    image_group.add_argument(
        "--images",
        type=Path,
        default=None,
        dest="images_dir",
        help=(
            "Directory of per-track images (one per track, natural-sorted by "
            "filename); each is shown for its track's actual duration"
        )
    )
    image_group.add_argument(
        "--animated-background",
        type=Path,
        default=None,
        dest="animated_background",
        help=(
            "Short, pre-rendered, seamlessly looping background video (e.g. "
            "tools/ambient_bg/composite.sh's final.mp4), looped to cover the "
            "full audio duration instead of a static image"
        )
    )

    return parser.parse_args(argv)


def _run_mashup_subcommand(argv: list[str]) -> int:
    """Handle the 'mashup' subcommand.

    Args:
        argv: Arguments after the 'mashup' token (i.e. sys.argv[2:]).

    Returns:
        Exit code.
    """
    import logging

    from soundweave.ffmpeg.commands import build_mp3_command
    from soundweave.ffmpeg.executor import ProcessingError, run_ffmpeg
    from soundweave.ffmpeg.probe import probe_audio_file, probe_loudnorm_duration
    from soundweave.logging.logger import setup_logger
    from soundweave.mashup_config import MashupConfig
    from soundweave.stages.download import download_stage, resolve_dry_run_tracklist
    from soundweave.stages.merge import merge_stage
    from soundweave.stages.video import (
        animated_background_video_stage,
        match_images_to_tracks,
        video_sequence_stage,
        video_stage,
    )
    from soundweave.utils.natural_sort import natural_sort
    from soundweave.utils.validators import validate_asset_path
    from soundweave.utils.youtube import format_timestamp, write_youtube_description
    from soundweave.ytdlp.executor import YtDlpError

    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

    try:
        args = parse_mashup_args(argv)
        config = MashupConfig(
            urls_file=args.urls,
            output_dir=args.output,
            fade_ms=args.fade_ms,
            shuffle=args.shuffle,
            strict=args.strict,
            cache_dir=args.cache_dir,
            static_image=args.image,
            images_dir=args.images_dir,
            animated_background=args.animated_background,
        )

        validate_asset_path(config.static_image, "Static image")
        if config.images_dir is not None and not config.images_dir.is_dir():
            raise ValidationError(f"--images directory not found: {config.images_dir}")
        validate_asset_path(config.animated_background, "Animated background video")

        if args.dry_run:
            # Console-only logger — deliberately does NOT use setup_logger(),
            # which would create mashup_log.txt under --output. A dry run
            # must not write any file under --output.
            dry_run_logger = logging.getLogger("soundweave.dry_run")
            dry_run_logger.setLevel(logging.INFO)
            dry_run_logger.handlers.clear()
            dry_run_logger.propagate = False
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            dry_run_logger.addHandler(console_handler)

            resolved = resolve_dry_run_tracklist(config, dry_run_logger)

            crossfade_s = config.fade_ms / 1000.0
            print()
            print("Dry run: resolved tracklist (no audio downloaded)")
            print("=" * 60)
            current_time = 0.0
            for idx, (title, duration_s) in enumerate(resolved):
                start_ts = format_timestamp(current_time)
                dur_ts = format_timestamp(duration_s)
                print(f"{idx + 1:>3}. [{start_ts}] {title}  ({dur_ts})")
                if idx < len(resolved) - 1:
                    current_time += duration_s - crossfade_s

            total_estimate = max(
                sum(d for _, d in resolved) - crossfade_s * max(len(resolved) - 1, 0),
                0.0,
            )
            print("=" * 60)
            print(f"Tracks: {len(resolved)}")
            print(f"Estimated total runtime: {format_timestamp(total_estimate)}")
            print()
            print("Dry run complete — no audio downloaded, no files written under --output.")

            return 0

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

        # Cheap up-front probe (ffprobe, not a decode) to drive
        # progress/ETA logging on long mashup encodes.
        merged_duration_s = probe_audio_file(merged_clean).duration_s

        logger.info("Encoding to MP3 (320kbps)...")
        run_ffmpeg(
            mp3_cmd,
            logger,
            description="MP3 encoding (320kbps CBR)",
            timeout=None,
            total_duration_s=merged_duration_s,
        )

        mp3_size_mb = merged_mp3.stat().st_size / (1024 ** 2)
        logger.info(f"  {merged_mp3.name} ({mp3_size_mb:.1f}MB)")

        crossfade_s = config.fade_ms / 1000.0
        description_path = config.output_dir / "youtube_description.txt"

        logger.info("Measuring actual track durations (post-loudnorm)...")
        actual_timestamps = [0.0]
        actual_durations = []  # per-track, in order — used for --images sequencing
        current_time = 0.0

        for i, track in enumerate(tracks):
            try:
                actual_duration = probe_loudnorm_duration(track.path)
                actual_durations.append(actual_duration)
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
                actual_durations.append(track.duration_s)
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

        # Stage 4: Video (optional) — static image, per-track image sequence,
        # or looping animated background
        final_video = None
        if config.images_dir is not None:
            images = natural_sort([
                p.name for p in config.images_dir.iterdir()
                if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
            ])
            image_paths = [config.images_dir / name for name in images]
            image_sequence = match_images_to_tracks(image_paths, actual_durations)
            final_video = video_sequence_stage(merged_clean, image_sequence, config.output_dir, logger)
        elif config.static_image is not None:
            final_video = video_stage(merged_clean, config, logger)
        elif config.animated_background is not None:
            final_video = animated_background_video_stage(
                merged_clean, config.animated_background, config.output_dir, logger
            )
        else:
            logger.info("=== Stage 4: Video Rendering ===")
            logger.info("No --image/--images/--animated-background specified, skipping video rendering")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Mashup completed successfully!")
        logger.info(f"Output:      {merged_mp3}")
        logger.info(f"Description: {description_path}")
        if final_video:
            logger.info(f"Video:       {final_video}")
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


def parse_mashup_ui_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments for the 'mashup-ui' subcommand.

    Args:
        argv: Argument list (defaults to sys.argv[2:] — after the 'mashup-ui' token).

    Returns:
        Parsed namespace with: port, output, no_browser.
    """
    parser = argparse.ArgumentParser(
        prog="soundweave mashup-ui",
        description=(
            "Local web form for the mashup subcommand: paste YouTube URLs and "
            "upload a cover image in a browser, then watch the run progress "
            "live. Binds to 127.0.0.1 only and shells out to the same "
            "'soundweave mashup' subcommand you'd run by hand — nothing "
            "leaves this machine."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  soundweave mashup-ui
  soundweave mashup-ui --port 9000
  soundweave mashup-ui --output output/mashup_ui --no-browser
        """
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="Port to listen on (default: 8787)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output") / "mashup_ui",
        help="Base directory for per-run output folders (default: output/mashup_ui)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        dest="no_browser",
        help="Don't automatically open a browser tab on startup"
    )
    return parser.parse_args(argv)


def _run_mashup_ui_subcommand(argv: list[str]) -> int:
    """Handle the 'mashup-ui' subcommand.

    Args:
        argv: Arguments after the 'mashup-ui' token (i.e. sys.argv[2:]).

    Returns:
        Exit code.
    """
    from soundweave.ui.server import run_server

    try:
        args = parse_mashup_ui_args(argv)
        run_server(port=args.port, output_base=args.output, open_browser=not args.no_browser)
        return 0
    except KeyboardInterrupt:
        print("\nStopped", file=sys.stderr)
        return 0
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0=success, 1=validation error, 2=processing error, 3=output error)
    """
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        return _run_loop_subcommand(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "mashup":
        return _run_mashup_subcommand(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "mashup-ui":
        return _run_mashup_ui_subcommand(sys.argv[2:])

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
