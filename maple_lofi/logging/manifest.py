"""Manifest generation for auditability."""

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from maple_lofi.config import PipelineConfig


@dataclass
class ManifestBuilder:
    """Builds and manages the manifest.json for a pipeline run."""

    config: PipelineConfig
    data: dict = field(default_factory=dict)
    ffmpeg_commands: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize manifest structure."""
        self.data = {
            "run_id": self.config.run_id,
            "timestamp": self.config.timestamp,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "ffmpeg_version": self._get_ffmpeg_version(),
            "platform": platform.system(),
            "inputs": {},
            "parameters": self._build_parameters(),
            "outputs": {},
            "stages": [],
            "ffmpeg_commands": [],
            "warnings": [],
            "errors": []
        }

    def _get_ffmpeg_version(self) -> str:
        """Get FFmpeg version string."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Extract first line (e.g., "ffmpeg version 4.4.2...")
            first_line = result.stdout.split("\n")[0]
            return first_line.replace("ffmpeg version ", "").split(" ")[0]
        except Exception:
            return "unknown"

    def _build_parameters(self) -> dict:
        """Build parameters dict from config."""
        return {
            "fade_ms": self.config.fade_ms,
            "num_tracks": self.config.num_tracks
        }

    def add_input_tracks(self, tracks: list, order_source: str):
        """Add input audio tracks to manifest.

        Args:
            tracks: List of AudioTrack objects
            order_source: "order.txt" or "natural_sort"
        """
        self.data["inputs"]["audio_files"] = [
            {
                "filename": t.filename,
                "duration_s": round(t.duration_s, 2),
                "sample_rate": t.sample_rate,
                "channels": t.channels,
                "codec": t.codec
            }
            for t in tracks
        ]
        self.data["inputs"]["order_source"] = order_source

    def add_input_asset(self, name: str, path: Path | None):
        """Add optional asset to manifest.

        Args:
            name: Asset name (cover_image, texture, drums)
            path: Path to asset (or None if not used)
        """
        if path:
            self.data["inputs"][name] = str(path)
        else:
            self.data["inputs"][name] = None

    def add_output(self, name: str, path: Path):
        """Add output file to manifest with metadata.

        Args:
            name: Output name (merged_clean, merged_lofi_wav, etc.)
            path: Path to output file
        """
        if not path.exists():
            return

        file_size_mb = round(path.stat().st_size / (1024 ** 2), 2)
        sha256 = self._compute_sha256(path)

        # Try to get duration from probe if it's audio/video
        duration_s = None
        try:
            from maple_lofi.ffmpeg.probe import probe_audio_file
            metadata = probe_audio_file(path)
            duration_s = round(metadata.duration_s, 2)
        except Exception:
            pass

        output_data = {
            "path": str(path),
            "file_size_mb": file_size_mb,
            "sha256": sha256
        }

        if duration_s:
            output_data["duration_s"] = duration_s

        self.data["outputs"][name] = output_data

    def add_stage_result(
        self,
        name: str,
        status: str,
        duration_s: float,
        **extras
    ):
        """Add stage completion info.

        Args:
            name: Stage name (ingest, merge, lofi, video)
            status: Status (success, error)
            duration_s: How long the stage took
            **extras: Additional stage-specific info
        """
        stage_data = {
            "name": name,
            "status": status,
            "duration_s": round(duration_s, 2)
        }
        stage_data.update(extras)
        self.data["stages"].append(stage_data)

    def add_ffmpeg_command(self, command: list[str]):
        """Add FFmpeg command to manifest.

        Args:
            command: FFmpeg command as list
        """
        self.ffmpeg_commands.append(" ".join(command))

    def add_warning(self, message: str):
        """Add warning message.

        Args:
            message: Warning message
        """
        self.data["warnings"].append(message)

    def add_error(self, message: str):
        """Add error message.

        Args:
            message: Error message
        """
        self.data["errors"].append(message)

    def write(self, output_path: Path):
        """Write manifest to JSON file.

        Args:
            output_path: Path to manifest.json
        """
        # Add all collected FFmpeg commands
        self.data["ffmpeg_commands"] = self.ffmpeg_commands

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Compute SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hash as hex string
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()
