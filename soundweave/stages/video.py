"""Stage 4: Video - Render static video with cover image and audio.

Also provides the per-track image-swap mode (PRD.md §7): instead of one
static image for the whole runtime, a sequence of images is shown, each
held on screen for its own track's duration. See `video_sequence_stage()`,
`match_images_to_tracks()`, and `calculate_sequence_duration()` below.
Not yet wired into the CLI/pipeline -- callers construct the
`(image_path, duration_s)` sequence by hand for now.

Also provides on-video "now playing" track-title cards (T1): burns each
track's title into the video at its actual start timestamp, fading in/out
over the window built by `build_track_card_drawtext_filters()`
(`soundweave.ffmpeg.commands`). This is an overlay layered onto whichever
of the two video modes above is active (via `video_stage()`'s /
`video_sequence_stage()`'s optional `track_cards`/`font_path` params), not
a third mode -- see `write_track_card_text_files()` and
`resolve_track_card_font()` below, and `cli.py`'s `--track-cards`/`--font`
flags for how this is wired into the `mashup` subcommand.
"""

import logging
import shutil
from pathlib import Path

from soundweave.config import PipelineConfig
from soundweave.ffmpeg.commands import (
    build_track_card_drawtext_filters,
    build_video_command,
    build_video_sequence_command,
)
from soundweave.ffmpeg.executor import run_ffmpeg
from soundweave.ffmpeg.probe import probe_audio_file
from soundweave.utils.validators import ValidationError

# Text files for each track-title card live under this subdirectory of the
# run's output directory (e.g. output/track_cards/card_000.txt), one per
# track -- kept on disk (not a tempdir that's cleaned up) so a user can
# inspect exactly what text was burned in and when, consistent with this
# project's "dual output" transparency convention (CLAUDE.md).
TRACK_CARDS_SUBDIR = "track_cards"

# Common macOS system font file locations to search, in priority order,
# when --font isn't given. Arial.ttf first: a plain (non-collection) .ttf
# is the simplest/most broadly compatible choice for FFmpeg's freetype
# loader. Verified present and renderable via drawtext on this machine
# (macOS, ffmpeg 8.0 built with --enable-libfreetype/--enable-libfontconfig).
DEFAULT_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    Path("/System/Library/Fonts/SFNS.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
]


def resolve_track_card_font(explicit_font: Path | None = None) -> Path:
    """Resolve a .ttf/.ttc/.otf font file for the --track-cards drawtext
    overlay (T1).

    Args:
        explicit_font: Font path from --font, if given. Must exist.

    Returns:
        A font file path confirmed to exist on disk.

    Raises:
        ValidationError: If `explicit_font` is given but doesn't exist, or
            (when not given) none of `DEFAULT_FONT_CANDIDATES` exist
            either -- drawtext needs a real `fontfile=` to render with, so
            this is a hard pre-flight failure rather than a silent
            fallback to no text.
    """
    if explicit_font is not None:
        if not explicit_font.is_file():
            raise ValidationError(f"--font path not found: {explicit_font}")
        return explicit_font

    for candidate in DEFAULT_FONT_CANDIDATES:
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(c) for c in DEFAULT_FONT_CANDIDATES)
    raise ValidationError(
        "No font available for --track-cards text rendering. Searched "
        f"common macOS system font locations: {searched}. "
        "Pass an explicit font file via --font /path/to/font.ttf."
    )


def write_track_card_text_files(
    track_cards: list[tuple[str, float]],
    output_dir: Path,
) -> list[tuple[Path, float]]:
    """Write one small text file per track title for drawtext's
    ``textfile=`` mode (T1), paired with each track's start timestamp.

    Real track titles routinely contain quotes/colons/percent signs (e.g.
    ``Artist: "Track" (Live)``). Embedding that text directly into an
    ffmpeg filtergraph `text=` value turned out to be unreliable in
    practice (see `build_track_card_drawtext_filters()`'s docstring in
    `soundweave.ffmpeg.commands` for the empirical findings) --
    `textfile=` + `expansion=none` renders a file's raw bytes completely
    literally instead, with zero filtergraph escaping needed for the
    title text itself.

    Args:
        track_cards: Ordered list of (title, start_s) pairs -- e.g.
            `[(clean_track_name(t.filename), start_s) for t, start_s in
            zip(tracks, actual_timestamps)]` in `cli.py`'s mashup
            subcommand, the same per-track timing data that already
            drives `youtube_description.txt`.
        output_dir: Run output directory; a `track_cards/` subdirectory
            (`TRACK_CARDS_SUBDIR`) is created under it to hold the files.

    Returns:
        Ordered list of (text_file_path, start_s) pairs, ready for
        `build_track_card_drawtext_filters()`.
    """
    cards_dir = output_dir / TRACK_CARDS_SUBDIR
    cards_dir.mkdir(parents=True, exist_ok=True)

    result = []
    for i, (title, start_s) in enumerate(track_cards):
        text_file = cards_dir / f"card_{i:03d}.txt"
        text_file.write_text(title, encoding="utf-8")
        result.append((text_file, start_s))

    return result


def _build_track_cards_filter(
    track_cards: list[tuple[str, float]] | None,
    font_path: Path | None,
    output_dir: Path,
    logger: logging.Logger,
) -> str | None:
    """Shared T1 wiring for `video_stage()`/`video_sequence_stage()`:
    resolve a font, write per-track text files, and build the drawtext
    filter fragment. Returns None (no-op) if `track_cards` is None/empty,
    so callers can pass the result straight through to the existing
    command builders' optional `track_cards_filter` param unchanged.
    """
    if not track_cards:
        return None

    resolved_font = resolve_track_card_font(font_path)
    logger.info(f"Track cards: {len(track_cards)} title(s), font={resolved_font}")

    card_files = write_track_card_text_files(track_cards, output_dir)
    return build_track_card_drawtext_filters(card_files, resolved_font)


def video_stage(
    audio_path: Path,
    config: PipelineConfig,
    logger: logging.Logger,
    track_cards: list[tuple[str, float]] | None = None,
    font_path: Path | None = None,
) -> Path:
    """Stage 4: Render static video with static image.

    Args:
        audio_path: Path to final audio (merged.wav)
        config: Pipeline configuration
        logger: Logger instance
        track_cards: Optional ordered list of (title, start_s) pairs for
            T1's "now playing" track-title cards, burned into the video at
            each track's start with a fade in/out. None (default) skips
            the overlay entirely -- behavior is unchanged from before this
            parameter existed.
        font_path: Optional explicit font file for the overlay (see
            `resolve_track_card_font()`). Ignored if `track_cards` is None.

    Returns:
        Path to final_video.mp4

    Process:
        1. Probe audio duration
        2. Scale/pad static image to 1920x1080 (preserve aspect, letterbox)
        3. Render static video:
           - 1fps (minimal file size)
           - H.264 (yuv420p, high profile)
           - AAC audio (192kbps)
           - Optional track-title card overlay (see `track_cards` above)
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

    track_cards_filter = _build_track_cards_filter(
        track_cards, font_path, config.output_dir, logger
    )

    # Build FFmpeg command
    command = build_video_command(
        audio_path,
        config.static_image,
        output_path,
        duration_s,
        track_cards_filter=track_cards_filter,
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
    track_cards: list[tuple[str, float]] | None = None,
    font_path: Path | None = None,
) -> Path:
    """Stage 4 (alternate mode): render video with a per-track image swap.

    Companion to `video_stage()` for the mashup "per-track images" mode
    (PRD.md §7). Instead of one static image for the whole runtime, each
    image in `image_sequence` holds on screen for its own duration, in
    order, hard-cutting to the next -- total duration matches the sum of
    the per-image durations. Does not change `video_stage()`'s behavior;
    this is an additive, independent entry point.

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        image_sequence: Ordered list of (image_path, duration_s) pairs, one
            per track. Must be non-empty.
        output_dir: Directory to write final_video.mp4 (and thumbnail) into
        logger: Logger instance
        track_cards: Optional ordered list of (title, start_s) pairs for
            T1's "now playing" track-title cards, burned into the video at
            each track's start with a fade in/out. None (default) skips
            the overlay entirely -- behavior is unchanged from before this
            parameter existed.
        font_path: Optional explicit font file for the overlay (see
            `resolve_track_card_font()`). Ignored if `track_cards` is None.

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

    track_cards_filter = _build_track_cards_filter(
        track_cards, font_path, output_dir, logger
    )

    command = build_video_sequence_command(
        audio_path, image_sequence, output_path, track_cards_filter=track_cards_filter
    )

    logger.info("Rendering video sequence (this may take a while for long audio)...")
    run_ffmpeg(
        command,
        logger,
        description="Video rendering with per-track image sequence",
        timeout=None
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
