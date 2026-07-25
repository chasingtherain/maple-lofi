"""yt-dlp command builders for the download stage.

Mirrors soundweave/ffmpeg/commands.py: pure functions that *build* command
argument lists for the external `yt-dlp` binary. They never execute anything —
see soundweave/ytdlp/executor.py for the run_* counterpart.
"""


def build_metadata_command(url: str) -> list[str]:
    """Build a yt-dlp command that fetches video metadata as JSON, no download.

    Args:
        url: YouTube video URL.

    Returns:
        yt-dlp command as a list of arguments. Running it prints a single
        JSON object (title, uploader, id, duration, ...) to stdout.
    """
    return [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "--no-warnings",
        "--skip-download",
        url,
    ]


def build_download_command(url: str, output_template: str) -> list[str]:
    """Build a yt-dlp command that downloads the best audio-only stream.

    The stream is extracted to m4a (no video, no re-encoding beyond container
    extraction) so downstream stages (ffprobe, the existing merge stage) can
    treat it exactly like any other local audio file.

    Args:
        url: YouTube video URL.
        output_template: yt-dlp output path template, e.g.
            "/path/to/cache/<video_id>.%(ext)s". Callers should pass a
            template keyed by a stable video ID (not yt-dlp's default title
            template) so re-runs can detect and reuse cached downloads.

    Returns:
        yt-dlp command as a list of arguments.
    """
    return [
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "m4a",
        "--no-playlist",
        "--no-warnings",
        "-o", output_template,
        url,
    ]
