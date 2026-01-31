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
    cover_image: Path | None = None
    texture: Path | None = None
    drums: Path | None = None

    # Audio processing parameters
    fade_ms: int = 15000                # Crossfade duration in milliseconds
    highpass_hz: int = 35               # High-pass filter frequency
    lowpass_hz: int = 11000             # Low-pass filter frequency
    texture_gain_db: float = -26.0      # Texture volume in dB
    drums_gain_db: float = -22.0        # Drums volume in dB
    drums_start_s: float = 0.0          # Drums start delay in seconds

    # Flags
    skip_lofi: bool = False             # Skip lofi transformation stage

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
        if isinstance(self.cover_image, str):
            self.cover_image = Path(self.cover_image)
        if isinstance(self.texture, str):
            self.texture = Path(self.texture)
        if isinstance(self.drums, str):
            self.drums = Path(self.drums)
