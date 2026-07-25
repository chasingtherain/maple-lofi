"""Tests for soundweave/mashup_config.py::MashupConfig."""

from pathlib import Path

from soundweave.mashup_config import DEFAULT_CACHE_DIR, DEFAULT_FADE_MS, MashupConfig


class TestMashupConfig:
    def test_defaults(self, tmp_path):
        config = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        assert config.fade_ms == DEFAULT_FADE_MS
        assert config.shuffle is False
        assert config.strict is False
        assert config.cache_dir == DEFAULT_CACHE_DIR

    def test_default_fade_ms_is_4500(self):
        # PRD.md §11: mashup crossfade default, distinct from the main
        # pipeline's 3000ms default.
        assert DEFAULT_FADE_MS == 4500

    def test_string_paths_coerced(self, tmp_path):
        config = MashupConfig(
            urls_file=str(tmp_path / "urls.txt"),
            output_dir=str(tmp_path / "out"),
            cache_dir=str(tmp_path / "cache"),
            animated_background=str(tmp_path / "loop.mp4"),
        )
        assert isinstance(config.urls_file, Path)
        assert isinstance(config.output_dir, Path)
        assert isinstance(config.cache_dir, Path)
        assert isinstance(config.animated_background, Path)

    def test_animated_background_defaults_to_none(self, tmp_path):
        config = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        assert config.animated_background is None

    def test_run_id_and_timestamp_auto_generated(self, tmp_path):
        config = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        assert config.run_id
        assert config.timestamp

    def test_run_id_unique_per_instance(self, tmp_path):
        c1 = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        c2 = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        assert c1.run_id != c2.run_id

    def test_explicit_cache_dir_respected(self, tmp_path):
        custom_cache = tmp_path / "my_cache"
        config = MashupConfig(
            urls_file=tmp_path / "urls.txt",
            output_dir=tmp_path / "out",
            cache_dir=custom_cache,
        )
        assert config.cache_dir == custom_cache

    def test_shuffle_default_is_false_unlike_main_pipeline(self, tmp_path):
        # PRD.md §6: opposite default from PipelineConfig.shuffle (True) —
        # a hand-picked urls.txt has an intentional order.
        config = MashupConfig(urls_file=tmp_path / "urls.txt", output_dir=tmp_path / "out")
        assert config.shuffle is False
