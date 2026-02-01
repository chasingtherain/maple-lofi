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
    lowpass_hz: int = 9500              # Low-pass filter frequency (changed from 11000 for warmth)
    texture_gain_db: float = -26.0      # Texture volume in dB
    drums_gain_db: float = -22.0        # Drums volume in dB
    drums_start_s: float = 0.0          # Drums start delay in seconds

    # Lofi processing options (optional, off by default)
    enable_compression: bool = False    # Enable gentle compression (restraint > layers)
    enable_saturation: bool = False     # Enable subtle saturation for warmth
    enable_reverb: bool = True          # Enable subtle reverb for café ambience (on by default)

    # Tempo control (café vibe)
    tempo_factor: float = 0.75          # Playback speed (0.75 = 25% slower, café chill vibe)

    # Compression parameters (when enabled)
    comp_ratio: float = 2.0             # Compression ratio (gentler than old 3:1)
    comp_threshold_db: float = -23.0    # Threshold in dB (lower than old -18dB)
    comp_attack_ms: float = 25.0        # Attack time in ms (slower than old 5ms)
    comp_release_ms: float = 200.0      # Release time in ms (longer than old 50ms)

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
