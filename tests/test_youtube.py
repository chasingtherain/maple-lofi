"""Tests for the pure functions in soundweave.utils.youtube.

Covers clean_track_name, format_timestamp, generate_youtube_timestamps,
and format_youtube_description. write_youtube_description (which touches
the filesystem) is out of scope.
"""

from pathlib import Path

from soundweave.stages.ingest import AudioTrack
from soundweave.utils.youtube import (
    clean_track_name,
    format_timestamp,
    format_youtube_description,
    generate_youtube_timestamps,
)


def make_track(filename: str, duration_s: float) -> AudioTrack:
    return AudioTrack(
        path=Path(f"/fake/{filename}"),
        filename=filename,
        duration_s=duration_s,
        sample_rate=48000,
        channels=2,
        codec="pcm_s16le",
    )


# ---------------------------------------------------------------------------
# clean_track_name
# ---------------------------------------------------------------------------


class TestCleanTrackName:
    def test_double_extension(self):
        assert clean_track_name("BlueSky.mp3.mpeg") == "BlueSky"

    def test_underscores_become_spaces(self):
        assert clean_track_name("track_name.mp3") == "track name"

    def test_hyphen_preserved(self):
        assert clean_track_name("My-Song.flac") == "My-Song"

    def test_numbered_prefix_with_dot_and_space(self):
        """Numbered-prefix filenames like Pokemon_RB's "1-05. Track_.mp3"
        strip the extension via a known-audio-suffix check (not a blind
        Path.stem loop), then a regex strips the leading "N-NN. " prefix.
        See the clean_track_name docstring example."""
        assert clean_track_name("1-05. Littleroot Town_.mp3") == "Littleroot Town"

    def test_no_extension(self):
        assert clean_track_name("noext") == "noext"

    def test_only_known_audio_extensions_stripped(self):
        """Only recognized audio extensions are stripped in sequence; a
        non-audio-extension segment like ".d" halts the strip rather than
        being blindly removed."""
        assert clean_track_name("a.b.c.d.mp3") == "a.b.c.d"

    def test_plain_name_with_extension(self):
        assert clean_track_name("SimpleTrack.wav") == "SimpleTrack"


# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------


class TestFormatTimestamp:
    def test_zero(self):
        assert format_timestamp(0) == "0:00"

    def test_under_a_minute(self):
        assert format_timestamp(5) == "0:05"

    def test_minutes_and_seconds(self):
        assert format_timestamp(65) == "1:05"

    def test_hours_minutes_seconds(self):
        assert format_timestamp(3661) == "1:01:01"

    def test_exact_hour(self):
        assert format_timestamp(3600) == "1:00:00"

    def test_exact_minute(self):
        assert format_timestamp(60) == "1:00"

    def test_truncates_fractional_seconds(self):
        assert format_timestamp(65.9) == "1:05"

    def test_multiple_hours(self):
        assert format_timestamp(7325) == "2:02:05"

    def test_seconds_padded_to_two_digits(self):
        assert format_timestamp(61) == "1:01"


# ---------------------------------------------------------------------------
# generate_youtube_timestamps
# ---------------------------------------------------------------------------


class TestGenerateYoutubeTimestamps:
    def test_first_track_starts_at_zero(self):
        tracks = [make_track("a.mp3", 100.0), make_track("b.mp3", 100.0)]

        result = generate_youtube_timestamps(tracks, crossfade_duration_s=3.0)

        assert result[0] == (0.0, "a")

    def test_subsequent_timestamps_account_for_crossfade(self):
        tracks = [make_track("a.mp3", 100.0), make_track("b.mp3", 100.0)]

        result = generate_youtube_timestamps(tracks, crossfade_duration_s=3.0)

        # second track starts at 100 - 3 = 97
        assert result[1] == (97.0, "b")

    def test_three_tracks_cumulative(self):
        tracks = [
            make_track("a.mp3", 60.0),
            make_track("b.mp3", 90.0),
            make_track("c.mp3", 40.0),
        ]

        result = generate_youtube_timestamps(tracks, crossfade_duration_s=5.0)

        assert result[0] == (0.0, "a")
        assert result[1] == (55.0, "b")  # 60 - 5
        assert result[2] == (140.0, "c")  # 55 + (90 - 5)

    def test_single_track(self):
        tracks = [make_track("only.mp3", 50.0)]

        result = generate_youtube_timestamps(tracks, crossfade_duration_s=3.0)

        assert result == [(0.0, "only")]

    def test_empty_tracks(self):
        assert generate_youtube_timestamps([], crossfade_duration_s=3.0) == []

    def test_names_are_cleaned(self):
        tracks = [make_track("track_one.mp3", 10.0), make_track("Track-Two.wav", 10.0)]

        result = generate_youtube_timestamps(tracks, crossfade_duration_s=1.0)

        assert result[0][1] == "track one"
        assert result[1][1] == "Track-Two"


# ---------------------------------------------------------------------------
# format_youtube_description
# ---------------------------------------------------------------------------


class TestFormatYoutubeDescription:
    def test_default_title(self):
        timestamps = [(0.0, "BlueSky"), (161.0, "CavaBien")]

        result = format_youtube_description(timestamps)

        assert result == "Tracklist:\n0:00 BlueSky\n2:41 CavaBien"

    def test_custom_title(self):
        timestamps = [(0.0, "Track")]

        result = format_youtube_description(timestamps, title="My Mix")

        assert result.startswith("My Mix:\n")

    def test_empty_timestamps(self):
        result = format_youtube_description([])
        assert result == "Tracklist:"

    def test_matches_docstring_example(self):
        timestamps = [(0.0, "BlueSky"), (161.0, "CavaBien"), (289.0, "FloralLife")]

        result = format_youtube_description(timestamps)

        expected = "Tracklist:\n0:00 BlueSky\n2:41 CavaBien\n4:49 FloralLife"
        assert result == expected
