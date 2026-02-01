"""Configuration dataclass for the Maple Lofi pipeline."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class PipelineConfig:
    """Configuration for the entire pipeline run.

    This dataclass holds all parameters needed for processing,
    ensuring type safety and clear documentation of options.
    """

    # Required paths
    input_dir: Path
    output_dir: Path

    # Optional paths
    static_image: Path | None = None    # Static image for video (placeholder if None)

    # Audio processing parameters
    fade_ms: int = 3000                 # Crossfade duration in milliseconds (3 seconds)
    num_tracks: int = 20                # Number of random tracks to select from input

    # Generated at runtime (do not set manually)
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        """Convert string paths to Path objects if needed."""
        if isinstance(self.input_dir, str):
            self.input_dir = Path(self.input_dir)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.static_image, str):
            self.static_image = Path(self.static_image)
