"""Configuration dataclass for the mashup subcommand."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# PRD.md §11: crossfade default for mashup mode, verified by ear against a
# 4-track local sample — reads as a clean song-to-song transition rather than
# a DJ-style overlap. Overridable via --fade-ms.
DEFAULT_FADE_MS: int = 4500
DEFAULT_CACHE_DIR: Path = Path(".cache") / "youtube"


@dataclass
class MashupConfig:
    """Configuration for a mashup subcommand run.

    Attributes:
        urls_file:   Path to the urls.txt file (one YouTube URL per line,
                     '#' comments, blank lines ignored — same format as
                     ingest.py's order.txt).
        output_dir:  Directory to write outputs (merged.mp3,
                     youtube_description.txt, mashup_log.txt) into.
        fade_ms:     Crossfade duration in milliseconds (default 4500 —
                     PRD.md §11). Passed straight through to the existing
                     merge stage unchanged.
        shuffle:     Whether to randomize track order (default False — a
                     hand-picked urls.txt has an intentional order; this is
                     the opposite default from the main pipeline's
                     PipelineConfig.shuffle).
        strict:      If True, abort the run on the first failed/unavailable
                     URL instead of skipping it with a warning (default
                     False — skip-with-warning, confirmed with the user).
        cache_dir:   Directory for yt-dlp downloads, cached by video ID
                     (<id>.m4a) so re-running a mashup (tweaking crossfade,
                     images, etc.) doesn't re-download. Defaults to
                     ./.cache/youtube.
        static_image: Single cover image for the whole video's duration
                     (mutually exclusive with images_dir). Same attribute
                     name as PipelineConfig.static_image so video_stage()
                     can be called with a MashupConfig unmodified.
        images_dir:  Directory of per-track images for the video's
                     per-track image-swap mode (mutually exclusive with
                     static_image). See match_images_to_tracks() /
                     video_sequence_stage() in soundweave/stages/video.py.
        run_id:      UUID for this run, auto-generated.
        timestamp:   ISO-8601 UTC timestamp, auto-generated.
    """

    urls_file: Path
    output_dir: Path
    fade_ms: int = DEFAULT_FADE_MS
    shuffle: bool = False
    strict: bool = False
    cache_dir: Path | None = None
    static_image: Path | None = None
    images_dir: Path | None = None
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if isinstance(self.urls_file, str):
            self.urls_file = Path(self.urls_file)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.cache_dir, str):
            self.cache_dir = Path(self.cache_dir)
        if isinstance(self.static_image, str):
            self.static_image = Path(self.static_image)
        if isinstance(self.images_dir, str):
            self.images_dir = Path(self.images_dir)
        if self.cache_dir is None:
            self.cache_dir = DEFAULT_CACHE_DIR
