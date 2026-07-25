"""Stage 0: Download — fetch audio + metadata from a list of YouTube URLs.

Runs before ingest/merge in the mashup subcommand (see PRD.md §5). Downloaded
tracks feed straight into the existing merge stage via MashupTrack, a
drop-in AudioTrack subclass — merge_stage/build_merge_command are reused
completely unchanged.
"""

import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path

from soundweave.ffmpeg.probe import probe_audio_file
from soundweave.mashup_config import MashupConfig
from soundweave.stages.ingest import AudioTrack
from soundweave.utils.validators import ValidationError
from soundweave.ytdlp.commands import build_download_command, build_metadata_command
from soundweave.ytdlp.executor import YtDlpError, run_ytdlp, validate_ytdlp

# urls.txt only requires http(s)://, not a youtube.com domain, and yt-dlp
# supports hundreds of sites - so a video "id" isn't guaranteed to be a
# YouTube-shaped 11-char token. It's used to build a cache file path
# (cache_dir / f"{video_id}.m4a"), so it must be constrained before that
# happens or a crafted id (e.g. containing "/" or "..") could write outside
# cache_dir.
_SAFE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class MashupTrack(AudioTrack):
    """An AudioTrack sourced from a YouTube URL.

    Extends AudioTrack (unchanged) with optional source metadata so the
    manifest and description generator can use real video titles instead of
    filenames. `filename` is set to the (cleaned) video title so the existing
    utils/youtube.py description generator works completely unmodified.
    """

    source_url: str | None = None
    video_title: str | None = None
    uploader: str | None = None


def parse_urls_file(urls_file: Path) -> list[str]:
    """Parse urls.txt to get an ordered list of YouTube URLs.

    Format mirrors ingest.py's parse_order_file()/order.txt convention:
        - One URL per line
        - Lines starting with '#' are ignored (comments)
        - Blank lines are ignored
        - Duplicates allowed

    Args:
        urls_file: Path to urls.txt.

    Returns:
        Ordered list of URL strings (may include duplicates).

    Raises:
        ValidationError: If the file has no URLs, or a non-comment/non-blank
            line doesn't look like a URL.
    """
    urls = []

    with open(urls_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if not line.startswith(("http://", "https://")):
                raise ValidationError(
                    f"urls.txt line {line_num}: expected a URL "
                    f"(http:// or https://), got: {line}"
                )

            urls.append(line)

    if not urls:
        raise ValidationError(f"No URLs found in {urls_file}")

    return urls


def validate_mashup_input(config: MashupConfig) -> None:
    """Validate inputs for the mashup subcommand's download stage.

    Args:
        config: Mashup configuration.

    Raises:
        ValidationError: On any validation failure.
    """
    if not config.urls_file.exists():
        raise ValidationError(f"urls.txt not found: {config.urls_file}")
    if not config.urls_file.is_file():
        raise ValidationError(f"urls.txt path is not a file: {config.urls_file}")

    if config.fade_ms < 0:
        raise ValidationError(f"--fade-ms must be >= 0, got {config.fade_ms}")

    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValidationError(f"Cannot create output directory: {config.output_dir}")


def fetch_metadata(url: str, logger: logging.Logger, timeout: int = 30) -> dict:
    """Fetch video metadata (title, uploader, duration, id) via yt-dlp.

    Args:
        url: YouTube video URL.
        logger: Logger instance.
        timeout: Timeout in seconds for the metadata-only call.

    Returns:
        Parsed yt-dlp JSON metadata dict.

    Raises:
        YtDlpError: If yt-dlp fails or its output can't be parsed as JSON.
    """
    command = build_metadata_command(url)
    result = run_ytdlp(
        command, logger, description=f"Fetch metadata for {url}", timeout=timeout
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise YtDlpError(f"Failed to parse yt-dlp metadata for {url}: {e}")


def download_audio(
    url: str,
    video_id: str,
    cache_dir: Path,
    logger: logging.Logger,
    timeout: int | None = None,
) -> Path:
    """Download the best audio-only stream for a URL, cached by video ID.

    Re-running a mashup (tweaking crossfade or images) reuses the cached file
    instead of re-downloading, per PRD.md §5.

    Args:
        url: YouTube video URL.
        video_id: yt-dlp video ID (from fetch_metadata), used as the cache key.
        cache_dir: Directory holding cached downloads (<id>.m4a).
        logger: Logger instance.
        timeout: Optional timeout in seconds (None = no timeout).

    Returns:
        Path to the downloaded (or already-cached) audio file.

    Raises:
        YtDlpError: If the download fails or doesn't produce the expected file.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    expected_path = cache_dir / f"{video_id}.m4a"

    if expected_path.exists():
        logger.info(f"  Using cached download: {expected_path.name}")
        return expected_path

    output_template = str(cache_dir / f"{video_id}.%(ext)s")
    command = build_download_command(url, output_template)
    run_ytdlp(command, logger, description=f"Download audio for {url}", timeout=timeout)

    if not expected_path.exists():
        raise YtDlpError(f"yt-dlp did not produce expected output file: {expected_path}")

    return expected_path


def resolve_dry_run_tracklist(
    config: MashupConfig, logger: logging.Logger
) -> list[tuple[str, float]]:
    """Resolve the final tracklist (title, duration) without downloading audio.

    For --dry-run: lets a user sanity-check track order/titles/estimated
    runtime for a urls.txt before committing to a full download + crossfade
    + encode run. Mirrors download_stage()'s URL parsing, shuffle-if-
    configured, and per-URL failure handling exactly (skip-with-warning
    unless config.strict) — but only calls fetch_metadata() (yt-dlp
    --dump-json --skip-download), never download_audio()/probe_audio_file().
    No audio is downloaded and nothing is written to config.cache_dir.

    Args:
        config: Mashup configuration.
        logger: Logger instance.

    Returns:
        Ordered list of (title, duration_s) tuples, one per successfully
        resolved URL, in final play order (post-shuffle if config.shuffle).

    Raises:
        ValidationError: If inputs are invalid, if config.strict is set and a
            URL fails, or if zero URLs resolve successfully.
    """
    logger.info("=== Dry Run: Resolve Tracklist ===")
    logger.info(f"URLs file: {config.urls_file}")

    validate_mashup_input(config)
    logger.info("Input validation passed")

    ytdlp_version = validate_ytdlp()
    logger.info(f"yt-dlp version: {ytdlp_version}")

    urls = parse_urls_file(config.urls_file)
    logger.info(f"Parsed {len(urls)} URL(s) from {config.urls_file.name}")

    ordered_urls = list(urls)
    if config.shuffle:
        logger.info("Shuffling URL order")
        random.shuffle(ordered_urls)
    else:
        logger.info("Using urls.txt order as-listed (no shuffle)")

    resolved: list[tuple[str, float]] = []

    for i, url in enumerate(ordered_urls, start=1):
        logger.info(f"[{i}/{len(ordered_urls)}] {url}")
        try:
            metadata = fetch_metadata(url, logger)
            title = metadata.get("title") or metadata.get("id") or url
            duration = metadata.get("duration")
            if duration is None:
                logger.warning(f"  yt-dlp metadata missing duration for {url}, using 0.0")
                duration = 0.0
            duration_s = float(duration)

            logger.info(f"  Title:    {title}")
            logger.info(f"  Duration: {duration_s:.1f}s")

            resolved.append((title, duration_s))

        except (YtDlpError, ValidationError) as e:
            if config.strict:
                raise ValidationError(f"Aborting (--strict): failed on {url}: {e}")
            logger.warning(f"  Skipping {url}: {e}")
            continue

    if not resolved:
        raise ValidationError("No tracks resolved successfully from urls.txt")

    logger.info(
        f"Dry-run resolution complete: {len(resolved)}/{len(ordered_urls)} track(s)"
    )

    return resolved


def download_stage(config: MashupConfig, logger: logging.Logger) -> list[MashupTrack]:
    """Stage 0: Discover URLs and download audio + metadata for each.

    Args:
        config: Mashup configuration.
        logger: Logger instance.

    Returns:
        Ordered list of MashupTrack objects, one per successfully downloaded
        URL (order = as-listed in urls.txt, unless config.shuffle is set).

    Raises:
        ValidationError: If inputs are invalid, if config.strict is set and a
            URL fails, or if zero URLs succeed.

    Failure handling:
        A single bad/unavailable URL logs a warning and is skipped — it does
        not abort the run (mirrors ingest.py's "skip corrupted file"
        behavior) — unless config.strict is True, in which case the run
        aborts on the first failure.
    """
    logger.info("=== Stage 0: Download ===")
    logger.info(f"URLs file: {config.urls_file}")

    validate_mashup_input(config)
    logger.info("Input validation passed")

    ytdlp_version = validate_ytdlp()
    logger.info(f"yt-dlp version: {ytdlp_version}")

    urls = parse_urls_file(config.urls_file)
    logger.info(f"Parsed {len(urls)} URL(s) from {config.urls_file.name}")

    ordered_urls = list(urls)
    if config.shuffle:
        logger.info("Shuffling URL order")
        random.shuffle(ordered_urls)
    else:
        logger.info("Using urls.txt order as-listed (no shuffle)")

    tracks: list[MashupTrack] = []

    for i, url in enumerate(ordered_urls, start=1):
        logger.info(f"[{i}/{len(ordered_urls)}] {url}")
        try:
            metadata = fetch_metadata(url, logger)
            video_id = metadata.get("id")
            if not video_id:
                raise YtDlpError(f"yt-dlp metadata missing video id for {url}")
            if not _SAFE_VIDEO_ID.match(video_id):
                raise YtDlpError(
                    f"yt-dlp returned an unsafe video id for {url}: {video_id!r}"
                )

            title = metadata.get("title") or video_id
            uploader = metadata.get("uploader")

            logger.info(f"  Title:    {title}")
            logger.info(f"  Uploader: {uploader}")

            audio_path = download_audio(url, video_id, config.cache_dir, logger)
            probed = probe_audio_file(audio_path)

            track = MashupTrack(
                path=audio_path,
                filename=title,
                duration_s=probed.duration_s,
                sample_rate=probed.sample_rate,
                channels=probed.channels,
                codec=probed.codec,
                source_url=url,
                video_title=title,
                uploader=uploader,
            )
            tracks.append(track)
            logger.info(
                f"  [{len(tracks)}] {track.duration_s:.1f}s, "
                f"{track.sample_rate}Hz, {track.channels}ch, {track.codec}"
            )

        except (YtDlpError, ValidationError) as e:
            if config.strict:
                raise ValidationError(f"Aborting (--strict): failed on {url}: {e}")
            logger.warning(f"  Skipping {url}: {e}")
            continue

    if not tracks:
        raise ValidationError("No tracks downloaded successfully from urls.txt")

    total_duration = sum(t.duration_s for t in tracks)
    logger.info(
        f"Download complete: {len(tracks)}/{len(ordered_urls)} track(s), "
        f"total {total_duration:.1f}s"
    )

    return tracks
