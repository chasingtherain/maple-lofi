"""Tests for the loop subcommand: LoopConfig derived properties and
validate_loop_input.

FFmpeg-dependent execution (loop_stage) is intentionally out of scope here.
"""

import logging

import pytest

from soundweave.loop_config import DEFAULT_GAP_MS, DEFAULT_TRIM_DB, LoopConfig
from soundweave.stages.loop import validate_loop_input
from soundweave.utils.validators import ValidationError


@pytest.fixture
def logger():
    log = logging.getLogger("test_loop")
    log.setLevel(logging.DEBUG)
    return log


# ---------------------------------------------------------------------------
# LoopConfig
# ---------------------------------------------------------------------------


class TestLoopConfig:
    def test_defaults(self, tmp_path):
        input_file = tmp_path / "song.mp3"
        config = LoopConfig(input_file=input_file, count=5)

        assert config.gap_ms == DEFAULT_GAP_MS
        assert config.trim_db == DEFAULT_TRIM_DB
        assert config.output_dir == tmp_path

    def test_string_paths_coerced_to_path(self, tmp_path):
        input_file = tmp_path / "song.mp3"
        config = LoopConfig(input_file=str(input_file), count=1, output_dir=str(tmp_path))

        assert config.input_file == input_file
        assert config.output_dir == tmp_path

    def test_output_dir_defaults_to_input_parent(self, tmp_path):
        nested = tmp_path / "nested" / "song.mp3"
        config = LoopConfig(input_file=nested, count=1)

        assert config.output_dir == nested.parent

    def test_gap_s_converts_ms_to_seconds(self, tmp_path):
        config = LoopConfig(input_file=tmp_path / "song.mp3", count=1, gap_ms=2500)

        assert config.gap_s == 2.5

    def test_output_filename_includes_count(self, tmp_path):
        config = LoopConfig(input_file=tmp_path / "song.mp3", count=3)

        assert config.output_filename == "song_x3.mp3"

    def test_output_path_joins_dir_and_filename(self, tmp_path):
        out_dir = tmp_path / "out"
        config = LoopConfig(input_file=tmp_path / "song.mp3", count=3, output_dir=out_dir)

        assert config.output_path == out_dir / "song_x3.mp3"

    def test_output_stem_overrides_input_file_stem(self, tmp_path):
        # Set by the --url path (cli.py) when input_file is a downloaded
        # cache file named by video id, not something worth naming the
        # output after.
        config = LoopConfig(
            input_file=tmp_path / "dQw4w9WgXcQ.m4a", count=2, output_stem="Never Gonna Give You Up"
        )

        assert config.output_filename == "Never Gonna Give You Up_x2.mp3"


# ---------------------------------------------------------------------------
# validate_loop_input
# ---------------------------------------------------------------------------


class TestValidateLoopInput:
    def _make_input(self, tmp_path, name="song.mp3"):
        input_file = tmp_path / name
        input_file.write_bytes(b"fake audio")
        return input_file

    def test_valid_config_passes(self, tmp_path):
        input_file = self._make_input(tmp_path)
        config = LoopConfig(input_file=input_file, count=5, output_dir=tmp_path / "out")

        validate_loop_input(config)  # should not raise

    def test_missing_input_file_raises(self, tmp_path):
        config = LoopConfig(input_file=tmp_path / "missing.mp3", count=1)

        with pytest.raises(ValidationError, match="not found"):
            validate_loop_input(config)

    def test_input_path_is_directory_raises(self, tmp_path):
        input_dir = tmp_path / "not_a_file"
        input_dir.mkdir()
        config = LoopConfig(input_file=input_dir, count=1)

        with pytest.raises(ValidationError, match="not a file"):
            validate_loop_input(config)

    def test_unsupported_extension_raises(self, tmp_path):
        input_file = self._make_input(tmp_path, name="song.ogg")
        config = LoopConfig(input_file=input_file, count=1)

        with pytest.raises(ValidationError, match="Unsupported audio format"):
            validate_loop_input(config)

    @pytest.mark.parametrize("suffix", [".mp3", ".wav", ".m4a", ".flac", ".MP3"])
    def test_supported_extensions_pass(self, tmp_path, suffix):
        input_file = self._make_input(tmp_path, name=f"song{suffix}")
        config = LoopConfig(input_file=input_file, count=1, output_dir=tmp_path / "out")

        validate_loop_input(config)  # should not raise

    def test_count_below_one_raises(self, tmp_path):
        input_file = self._make_input(tmp_path)
        config = LoopConfig(input_file=input_file, count=0)

        with pytest.raises(ValidationError, match="--count must be >= 1"):
            validate_loop_input(config)

    def test_negative_gap_raises(self, tmp_path):
        input_file = self._make_input(tmp_path)
        config = LoopConfig(input_file=input_file, count=1, gap_ms=-100)

        with pytest.raises(ValidationError, match="--gap-ms must be >= 0"):
            validate_loop_input(config)

    def test_output_would_overwrite_input_raises(self, tmp_path, monkeypatch):
        # output_filename always appends "_x<count>" to the stem, so this
        # can't collide with the input via normal derivation; force it via
        # the output_path property to exercise the guard directly.
        input_file = self._make_input(tmp_path)
        config = LoopConfig(input_file=input_file, count=1, output_dir=tmp_path)
        monkeypatch.setattr(LoopConfig, "output_path", property(lambda self: self.input_file))

        with pytest.raises(ValidationError, match="would overwrite input file"):
            validate_loop_input(config)

    def test_creates_output_dir_if_missing(self, tmp_path):
        input_file = self._make_input(tmp_path)
        out_dir = tmp_path / "does" / "not" / "exist"
        config = LoopConfig(input_file=input_file, count=1, output_dir=out_dir)

        validate_loop_input(config)

        assert out_dir.is_dir()
