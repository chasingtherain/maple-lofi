"""Configuration dataclass for the loop subcommand."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

FADE_DURATION_S: float = 0.5
DEFAULT_GAP_MS: int = 3500
DEFAULT_TRIM_DB: float = -40.0
AUDIO_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".m4a", ".flac"})


@dataclass
class LoopConfig:
    """Configuration for a loop subcommand run.

    Attributes:
        input_file:  Path to the single audio input file.
        count:       Number of times to play the file (>= 1).
        gap_ms:      Silence between repetitions in milliseconds.
        output_dir:  Directory to write the output MP3 into.
                     Defaults to the same directory as input_file.
        fade_s:      Fade-in/out duration in seconds (fixed at 0.5s).
        trim_db:     dB threshold for trailing silence trim (default -40dB).
                     Audio below this level at the track's end is removed before
                     the gap is inserted, accounting for natural wind-down.
        run_id:      UUID for this run, auto-generated.
        timestamp:   ISO-8601 UTC timestamp, auto-generated.
        output_stem: Override for output_filename's stem. Unset when looping
                     a local file (the file's own stem is used, as before).
                     Set by the --url path (cli.py) to a sanitized video
                     title, since the downloaded file's stem is a cache-key
                     video id, not something worth naming the output after.
    """

    input_file: Path
    count: int
    gap_ms: int = DEFAULT_GAP_MS
    output_dir: Path | None = None
    fade_s: float = FADE_DURATION_S
    trim_db: float = DEFAULT_TRIM_DB
    output_stem: str | None = None
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if isinstance(self.input_file, str):
            self.input_file = Path(self.input_file)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if self.output_dir is None:
            self.output_dir = self.input_file.parent

    @property
    def gap_s(self) -> float:
        return self.gap_ms / 1000.0

    @property
    def output_filename(self) -> str:
        stem = self.output_stem or self.input_file.stem
        return f"{stem}_x{self.count}.mp3"

    @property
    def output_path(self) -> Path:
        return self.output_dir / self.output_filename
