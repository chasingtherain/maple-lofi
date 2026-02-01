"""Natural sorting for filenames (e.g., track2 before track10)."""

import re
from typing import Any


def natural_sort_key(text: str) -> list[Any]:
    """Generate a sort key for natural (human-friendly) sorting.

    This makes "track2.mp3" sort before "track10.mp3" instead of after it.

    Args:
        text: String to generate sort key for

    Returns:
        List of strings and integers for sorting

    Example:
        >>> files = ["track10.mp3", "track2.mp3", "track1.mp3"]
        >>> sorted(files, key=natural_sort_key)
        ['track1.mp3', 'track2.mp3', 'track10.mp3']
    """
    def convert(fragment: str) -> int | str:
        """Convert fragment to int if numeric, otherwise lowercase string."""
        return int(fragment) if fragment.isdigit() else fragment.lower()

    return [convert(c) for c in re.split(r'(\d+)', text)]


def natural_sort(items: list[str]) -> list[str]:
    """Sort a list of strings using natural (human-friendly) ordering.

    Args:
        items: List of strings to sort

    Returns:
        Sorted list

    Example:
        >>> natural_sort(["track10.mp3", "track2.mp3", "track1.mp3"])
        ['track1.mp3', 'track2.mp3', 'track10.mp3']
    """
    return sorted(items, key=natural_sort_key)
