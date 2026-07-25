"""Tests for the pure ordering functions in soundweave.stages.ingest.

Covers parse_order_file, validate_ordering, and determine_track_order.
FFmpeg-dependent probing (probe_track, ingest_stage) is intentionally
out of scope here.
"""

import logging

import pytest

from soundweave.stages.ingest import (
    determine_track_order,
    parse_order_file,
    validate_ordering,
)
from soundweave.utils.validators import ValidationError


@pytest.fixture
def logger():
    log = logging.getLogger("test_ingest")
    log.setLevel(logging.DEBUG)
    return log


# ---------------------------------------------------------------------------
# parse_order_file
# ---------------------------------------------------------------------------


class TestParseOrderFile:
    def test_basic_list(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("track1.mp3\ntrack2.mp3\ntrack3.mp3\n")

        result = parse_order_file(order_file)

        assert result == ["track1.mp3", "track2.mp3", "track3.mp3"]

    def test_ignores_comments(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text(
            "# This is a comment\n"
            "track1.mp3\n"
            "# another comment\n"
            "track2.mp3\n"
        )

        result = parse_order_file(order_file)

        assert result == ["track1.mp3", "track2.mp3"]

    def test_ignores_blank_lines(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("track1.mp3\n\n\ntrack2.mp3\n\n")

        result = parse_order_file(order_file)

        assert result == ["track1.mp3", "track2.mp3"]

    def test_strips_whitespace(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("  track1.mp3  \n\ttrack2.mp3\t\n")

        result = parse_order_file(order_file)

        assert result == ["track1.mp3", "track2.mp3"]

    def test_allows_duplicates(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("track1.mp3\ntrack2.mp3\ntrack1.mp3\n")

        result = parse_order_file(order_file)

        assert result == ["track1.mp3", "track2.mp3", "track1.mp3"]

    def test_filenames_with_spaces(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("1-05. Littleroot Town_.mp3\ntrack two.mp3\n")

        result = parse_order_file(order_file)

        assert result == ["1-05. Littleroot Town_.mp3", "track two.mp3"]

    def test_rejects_forward_slash_paths(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("subdir/track1.mp3\n")

        with pytest.raises(ValidationError, match="Paths not allowed"):
            parse_order_file(order_file)

    def test_rejects_backslash_paths(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("subdir\\track1.mp3\n")

        with pytest.raises(ValidationError, match="Paths not allowed"):
            parse_order_file(order_file)

    def test_error_message_includes_line_number(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("track1.mp3\nsubdir/track2.mp3\n")

        with pytest.raises(ValidationError, match="line 2"):
            parse_order_file(order_file)

    def test_empty_file(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("")

        result = parse_order_file(order_file)

        assert result == []

    def test_only_comments_and_blanks(self, tmp_path):
        order_file = tmp_path / "order.txt"
        order_file.write_text("# comment only\n\n   \n# another\n")

        result = parse_order_file(order_file)

        assert result == []


# ---------------------------------------------------------------------------
# validate_ordering
# ---------------------------------------------------------------------------


class TestValidateOrdering:
    def test_valid_exact_match(self, logger):
        # No exception should be raised.
        validate_ordering(
            ["track1.mp3", "track2.mp3"],
            {"track1.mp3", "track2.mp3"},
            logger,
        )

    def test_extra_file_in_order_txt_raises(self, logger):
        """A file listed in order.txt but missing from disk is an error."""
        with pytest.raises(ValidationError, match="not found in input directory"):
            validate_ordering(
                ["track1.mp3", "ghost.mp3"],
                {"track1.mp3"},
                logger,
            )

    def test_missing_from_order_txt_is_only_a_warning(self, logger, caplog):
        """A file that exists on disk but isn't listed in order.txt is OK
        (just logged as info), not an error."""
        with caplog.at_level(logging.INFO, logger="test_ingest"):
            validate_ordering(
                ["track1.mp3"],
                {"track1.mp3", "track2.mp3"},
                logger,
            )

        assert any(
            "not listed in order.txt" in record.message for record in caplog.records
        )

    def test_asymmetry_extra_errors_missing_warns(self, logger, caplog):
        """Combined case: an unknown file still raises even though there's
        also a missing-from-order file present."""
        with pytest.raises(ValidationError, match="not found in input directory"):
            validate_ordering(
                ["track1.mp3", "ghost.mp3"],
                {"track1.mp3", "track2.mp3"},
                logger,
            )

    def test_duplicates_logged_but_allowed(self, logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_ingest"):
            validate_ordering(
                ["track1.mp3", "track1.mp3", "track2.mp3"],
                {"track1.mp3", "track2.mp3"},
                logger,
            )

        assert any("duplicates" in record.message for record in caplog.records)

    def test_no_duplicates_no_duplicate_log(self, logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_ingest"):
            validate_ordering(
                ["track1.mp3", "track2.mp3"],
                {"track1.mp3", "track2.mp3"},
                logger,
            )

        assert not any("duplicates" in record.message for record in caplog.records)

    def test_empty_order_with_available_files(self, logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_ingest"):
            validate_ordering([], {"track1.mp3"}, logger)

        assert any(
            "not listed in order.txt" in record.message for record in caplog.records
        )

    def test_error_message_lists_all_extra_files_sorted(self, logger):
        with pytest.raises(ValidationError) as exc_info:
            validate_ordering(
                ["z.mp3", "a.mp3"],
                set(),
                logger,
            )
        message = str(exc_info.value)
        assert "a.mp3" in message
        assert "z.mp3" in message
        # sorted() means "a.mp3" should appear before "z.mp3"
        assert message.index("a.mp3") < message.index("z.mp3")


# ---------------------------------------------------------------------------
# determine_track_order
# ---------------------------------------------------------------------------


class TestDetermineTrackOrder:
    def test_uses_order_file_when_present(self, tmp_path, logger):
        (tmp_path / "order.txt").write_text("b.mp3\na.mp3\n")
        audio_files = [tmp_path / "a.mp3", tmp_path / "b.mp3"]

        result = determine_track_order(tmp_path, audio_files, logger)

        assert result == ["b.mp3", "a.mp3"]

    def test_falls_back_to_natural_sort_without_order_file(self, tmp_path, logger):
        audio_files = [
            tmp_path / "track10.mp3",
            tmp_path / "track2.mp3",
            tmp_path / "track1.mp3",
        ]

        result = determine_track_order(tmp_path, audio_files, logger)

        assert result == ["track1.mp3", "track2.mp3", "track10.mp3"]

    def test_order_file_with_invalid_entry_raises(self, tmp_path, logger):
        (tmp_path / "order.txt").write_text("a.mp3\nghost.mp3\n")
        audio_files = [tmp_path / "a.mp3"]

        with pytest.raises(ValidationError):
            determine_track_order(tmp_path, audio_files, logger)

    def test_order_file_subset_of_available_files(self, tmp_path, logger):
        """order.txt may list only a subset of available files."""
        (tmp_path / "order.txt").write_text("a.mp3\n")
        audio_files = [tmp_path / "a.mp3", tmp_path / "b.mp3"]

        result = determine_track_order(tmp_path, audio_files, logger)

        assert result == ["a.mp3"]
