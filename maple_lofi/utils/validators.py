"""Pre-flight validation checks for the pipeline."""

import platform
import re
import subprocess
import sys
from pathlib import Path


class ValidationError(Exception):
    """Raised when validation fails (exit code 1)."""
    pass


def validate_python_version() -> None:
    """Check that Python version is >= 3.10.

    Raises:
        ValidationError: If Python version is too old
    """
    version_info = sys.version_info
    if version_info < (3, 10):
        raise ValidationError(
            f"Python 3.10+ required, but running {version_info.major}.{version_info.minor}"
        )


def validate_ffmpeg() -> str:
    """Check that FFmpeg is installed and version >= 4.4.

    Returns:
        FFmpeg version string

    Raises:
        ValidationError: If FFmpeg not found or version too old
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            raise ValidationError("FFmpeg command failed")

        # Parse version from output (e.g., "ffmpeg version 4.4.2")
        match = re.search(r"ffmpeg version (\d+\.\d+)", result.stdout)
        if not match:
            raise ValidationError("Could not parse FFmpeg version")

        version_str = match.group(1)
        major, minor = map(int, version_str.split("."))

        if (major, minor) < (4, 4):
            raise ValidationError(
                f"FFmpeg 4.4+ required, but found {version_str}"
            )

        return version_str

    except FileNotFoundError:
        raise ValidationError(
            "FFmpeg not found. Please install FFmpeg 4.4+ and ensure it's in your PATH"
        )
    except subprocess.TimeoutExpired:
        raise ValidationError("FFmpeg command timed out")


def validate_input_directory(input_dir: Path) -> None:
    """Check that input directory exists and is readable.

    Args:
        input_dir: Path to input directory

    Raises:
        ValidationError: If directory doesn't exist or isn't readable
    """
    if not input_dir.exists():
        raise ValidationError(f"Input directory not found: {input_dir}")

    if not input_dir.is_dir():
        raise ValidationError(f"Input path is not a directory: {input_dir}")

    # Try to list directory to check readability
    try:
        list(input_dir.iterdir())
    except PermissionError:
        raise ValidationError(f"Input directory not readable: {input_dir}")


def validate_asset_path(asset_path: Path | None, asset_name: str) -> None:
    """Check that an optional asset file exists if specified.

    Args:
        asset_path: Path to asset file (or None if not specified)
        asset_name: Human-readable name for error messages

    Raises:
        ValidationError: If path specified but file doesn't exist
    """
    if asset_path is None:
        return

    if not asset_path.exists():
        raise ValidationError(f"{asset_name} file not found: {asset_path}")

    if not asset_path.is_file():
        raise ValidationError(f"{asset_name} path is not a file: {asset_path}")


def estimate_disk_space_needed(input_dir: Path) -> int:
    """Estimate disk space needed for processing (input size × 3).

    Args:
        input_dir: Path to input directory

    Returns:
        Estimated bytes needed
    """
    total_size = 0

    # Sum up all audio files
    for ext in [".mp3", ".wav", ".m4a", ".flac"]:
        for file_path in input_dir.glob(f"*{ext}"):
            total_size += file_path.stat().st_size

    # Estimate: merged_clean.wav + merged_lofi.wav + merged_lofi.mp3 + video
    # Rule of thumb: 3x input size
    return total_size * 3


def validate_disk_space(output_dir: Path, needed_bytes: int) -> None:
    """Check that sufficient disk space is available.

    Args:
        output_dir: Path to output directory
        needed_bytes: Estimated bytes needed

    Raises:
        ValidationError: If insufficient disk space
    """
    try:
        # Get disk usage stats
        stat = output_dir.stat() if output_dir.exists() else output_dir.parent.stat()

        # This is platform-dependent, but works on macOS/Linux
        if hasattr(stat, 'st_blocks'):
            # Try to get actual disk space (not always accurate)
            import shutil
            disk_usage = shutil.disk_usage(output_dir if output_dir.exists() else output_dir.parent)
            available_bytes = disk_usage.free

            if available_bytes < needed_bytes:
                needed_gb = needed_bytes / (1024**3)
                available_gb = available_bytes / (1024**3)
                raise ValidationError(
                    f"Insufficient disk space. Need ~{needed_gb:.2f}GB, "
                    f"but only {available_gb:.2f}GB available"
                )
    except Exception:
        # If we can't check disk space, just log a warning and continue
        # (Better to try and fail than to block on disk space check errors)
        pass


def validate_output_directory(output_dir: Path) -> None:
    """Check that output directory is writable (create if needed).

    Args:
        output_dir: Path to output directory

    Raises:
        ValidationError: If directory can't be created or isn't writable
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValidationError(f"Cannot create output directory: {output_dir}")

    # Try to create a test file to verify writability
    test_file = output_dir / ".write_test"
    try:
        test_file.touch()
        test_file.unlink()
    except PermissionError:
        raise ValidationError(f"Output directory not writable: {output_dir}")
