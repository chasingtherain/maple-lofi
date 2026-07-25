"""Tests for soundweave.stages.merge.calculate_crossfade_durations."""

import logging
from pathlib import Path

import pytest

from soundweave.stages.ingest import AudioTrack
from soundweave.stages.merge import calculate_crossfade_durations


@pytest.fixture
def logger():
    log = logging.getLogger("test_merge")
    log.setLevel(logging.DEBUG)
    return log


def make_track(filename: str, duration_s: float) -> AudioTrack:
    return AudioTrack(
        path=Path(f"/fake/{filename}"),
        filename=filename,
        duration_s=duration_s,
        sample_rate=48000,
        channels=2,
        codec="pcm_s16le",
    )


class TestCalculateCrossfadeDurations:
    def test_zero_tracks_returns_empty(self, logger):
        assert calculate_crossfade_durations([], 3.0, logger) == []

    def test_single_track_returns_empty(self, logger):
        tracks = [make_track("a.mp3", 120.0)]
        assert calculate_crossfade_durations(tracks, 3.0, logger) == []

    def test_returns_one_less_than_track_count(self, logger):
        tracks = [make_track(f"t{i}.mp3", 120.0) for i in range(4)]
        result = calculate_crossfade_durations(tracks, 3.0, logger)
        assert len(result) == 3

    def test_uses_default_when_tracks_long_enough(self, logger):
        tracks = [make_track("a.mp3", 100.0), make_track("b.mp3", 100.0)]
        result = calculate_crossfade_durations(tracks, 3.0, logger)
        assert result == [3.0]

    def test_reduces_to_50_percent_of_shorter_track(self, logger):
        """If a track is shorter than the configured crossfade, the
        crossfade should shrink to 50% of that track's duration."""
        tracks = [make_track("short.mp3", 4.0), make_track("b.mp3", 100.0)]
        default_crossfade = 5.0

        result = calculate_crossfade_durations(tracks, default_crossfade, logger)

        assert result == [2.0]  # 4.0 * 0.5

    def test_minimum_effective_crossfade_is_one_second(self, logger):
        """Even if 50% of the shorter track is below 1s, the crossfade is
        floored at 1.0s."""
        tracks = [make_track("tiny.mp3", 1.0), make_track("b.mp3", 100.0)]
        default_crossfade = 5.0

        result = calculate_crossfade_durations(tracks, default_crossfade, logger)

        assert result == [1.0]

    def test_uses_shorter_of_the_pair(self, logger):
        """The comparison uses the shorter of the two adjacent tracks, not
        just the first one."""
        tracks = [make_track("long.mp3", 100.0), make_track("short.mp3", 4.0)]
        default_crossfade = 5.0

        result = calculate_crossfade_durations(tracks, default_crossfade, logger)

        assert result == [2.0]

    def test_exactly_equal_to_crossfade_uses_default(self, logger):
        """min_duration == default_crossfade_s is NOT < default, so the
        default crossfade should be used unreduced."""
        tracks = [make_track("a.mp3", 5.0), make_track("b.mp3", 100.0)]
        default_crossfade = 5.0

        result = calculate_crossfade_durations(tracks, default_crossfade, logger)

        assert result == [5.0]

    def test_multiple_pairs_mixed(self, logger):
        tracks = [
            make_track("a.mp3", 100.0),
            make_track("short.mp3", 2.0),
            make_track("c.mp3", 100.0),
        ]
        default_crossfade = 4.0

        result = calculate_crossfade_durations(tracks, default_crossfade, logger)

        # Pair 1 (a, short): min=2.0 < 4.0 -> reduced to max(1.0, 1.0) = 1.0
        # Pair 2 (short, c): min=2.0 < 4.0 -> reduced to max(1.0, 1.0) = 1.0
        assert result == [1.0, 1.0]

    def test_warns_when_reduced(self, logger, caplog):
        tracks = [make_track("short.mp3", 4.0), make_track("b.mp3", 100.0)]

        with caplog.at_level(logging.WARNING, logger="test_merge"):
            calculate_crossfade_durations(tracks, 5.0, logger)

        assert any("reduced to" in record.message for record in caplog.records)

    def test_no_warning_when_default_used(self, logger, caplog):
        tracks = [make_track("a.mp3", 100.0), make_track("b.mp3", 100.0)]

        with caplog.at_level(logging.WARNING, logger="test_merge"):
            calculate_crossfade_durations(tracks, 3.0, logger)

        assert len(caplog.records) == 0

    def test_warning_names_the_shorter_track(self, logger, caplog):
        tracks = [make_track("long.mp3", 100.0), make_track("shorty.mp3", 4.0)]

        with caplog.at_level(logging.WARNING, logger="test_merge"):
            calculate_crossfade_durations(tracks, 5.0, logger)

        assert any("shorty.mp3" in record.message for record in caplog.records)
