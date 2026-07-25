"""Tests for soundweave/stages/download.py.

All yt-dlp subprocess interaction is mocked (via soundweave.stages.download's
imported run_ytdlp/validate_ytdlp/probe_audio_file references) — no network
access happens in this file.
"""

import json
import logging
import subprocess
from unittest.mock import patch

import pytest

from soundweave.ffmpeg.probe import AudioMetadata
from soundweave.mashup_config import MashupConfig
from soundweave.stages.download import (
    MashupTrack,
    download_audio,
    download_stage,
    fetch_metadata,
    parse_urls_file,
    validate_mashup_input,
)
from soundweave.utils.validators import ValidationError
from soundweave.ytdlp.executor import YtDlpError


@pytest.fixture
def logger():
    log = logging.getLogger("test-download")
    log.addHandler(logging.NullHandler())
    return log


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _metadata_json(video_id="abc123", title="My Song", uploader="Some Channel", duration=180):
    return json.dumps(
        {"id": video_id, "title": title, "uploader": uploader, "duration": duration}
    )


# ---------------------------------------------------------------------------
# parse_urls_file — mirrors ingest.py's parse_order_file conventions
# ---------------------------------------------------------------------------

class TestParseUrlsFile:
    def test_basic_urls(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://youtube.com/watch?v=aaa\n"
            "https://youtube.com/watch?v=bbb\n"
        )
        result = parse_urls_file(urls_file)
        assert result == [
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=bbb",
        ]

    def test_comments_ignored(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "# my playlist\n"
            "https://youtube.com/watch?v=aaa\n"
            "# another comment\n"
            "https://youtube.com/watch?v=bbb\n"
        )
        result = parse_urls_file(urls_file)
        assert len(result) == 2

    def test_blank_lines_ignored(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://youtube.com/watch?v=aaa\n"
            "\n"
            "   \n"
            "https://youtube.com/watch?v=bbb\n"
        )
        result = parse_urls_file(urls_file)
        assert len(result) == 2

    def test_duplicates_allowed(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://youtube.com/watch?v=aaa\n"
            "https://youtube.com/watch?v=aaa\n"
        )
        result = parse_urls_file(urls_file)
        assert result == [
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=aaa",
        ]

    def test_order_preserved(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://youtube.com/watch?v=zzz\n"
            "https://youtube.com/watch?v=aaa\n"
            "https://youtube.com/watch?v=mmm\n"
        )
        result = parse_urls_file(urls_file)
        assert result == [
            "https://youtube.com/watch?v=zzz",
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=mmm",
        ]

    def test_non_url_line_raises(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("not-a-url-at-all\n")
        with pytest.raises(ValidationError):
            parse_urls_file(urls_file)

    def test_empty_file_raises(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("# only comments\n\n")
        with pytest.raises(ValidationError):
            parse_urls_file(urls_file)


# ---------------------------------------------------------------------------
# validate_mashup_input
# ---------------------------------------------------------------------------

class TestValidateMashupInput:
    def test_missing_urls_file_raises(self, tmp_path):
        config = MashupConfig(
            urls_file=tmp_path / "nonexistent.txt", output_dir=tmp_path / "out"
        )
        with pytest.raises(ValidationError):
            validate_mashup_input(config)

    def test_negative_fade_ms_raises(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://youtube.com/watch?v=aaa\n")
        config = MashupConfig(urls_file=urls_file, output_dir=tmp_path / "out", fade_ms=-1)
        with pytest.raises(ValidationError):
            validate_mashup_input(config)

    def test_creates_output_dir(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://youtube.com/watch?v=aaa\n")
        out_dir = tmp_path / "brand_new_output"
        config = MashupConfig(urls_file=urls_file, output_dir=out_dir)
        validate_mashup_input(config)
        assert out_dir.exists()

    def test_valid_input_passes(self, tmp_path):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://youtube.com/watch?v=aaa\n")
        config = MashupConfig(urls_file=urls_file, output_dir=tmp_path / "out")
        validate_mashup_input(config)  # should not raise


# ---------------------------------------------------------------------------
# fetch_metadata
# ---------------------------------------------------------------------------

class TestFetchMetadata:
    def test_parses_json_metadata(self, logger):
        with patch(
            "soundweave.stages.download.run_ytdlp",
            return_value=_completed(stdout=_metadata_json()),
        ):
            metadata = fetch_metadata("https://youtube.com/watch?v=abc123", logger)

        assert metadata["id"] == "abc123"
        assert metadata["title"] == "My Song"
        assert metadata["uploader"] == "Some Channel"

    def test_invalid_json_raises_ytdlp_error(self, logger):
        with patch(
            "soundweave.stages.download.run_ytdlp",
            return_value=_completed(stdout="not json"),
        ), pytest.raises(YtDlpError):
            fetch_metadata("https://youtube.com/watch?v=abc123", logger)

    def test_ytdlp_failure_propagates(self, logger):
        with patch(
            "soundweave.stages.download.run_ytdlp", side_effect=YtDlpError("failed")
        ), pytest.raises(YtDlpError):
            fetch_metadata("https://youtube.com/watch?v=abc123", logger)


# ---------------------------------------------------------------------------
# download_audio — caching behavior
# ---------------------------------------------------------------------------

class TestDownloadAudio:
    def test_downloads_when_not_cached(self, tmp_path, logger):
        cache_dir = tmp_path / "cache"

        def fake_run_ytdlp(command, logger, description, timeout=None):
            # Simulate yt-dlp writing the extracted m4a to disk.
            (cache_dir / "abc123.m4a").write_bytes(b"fake audio")
            return _completed()

        with patch("soundweave.stages.download.run_ytdlp", side_effect=fake_run_ytdlp) as mock_run:
            result = download_audio(
                "https://youtube.com/watch?v=abc123", "abc123", cache_dir, logger
            )

        mock_run.assert_called_once()
        assert result == cache_dir / "abc123.m4a"
        assert result.exists()

    def test_uses_cache_when_present(self, tmp_path, logger):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached_file = cache_dir / "abc123.m4a"
        cached_file.write_bytes(b"already downloaded")

        with patch("soundweave.stages.download.run_ytdlp") as mock_run:
            result = download_audio(
                "https://youtube.com/watch?v=abc123", "abc123", cache_dir, logger
            )

        mock_run.assert_not_called()
        assert result == cached_file

    def test_missing_output_file_raises(self, tmp_path, logger):
        cache_dir = tmp_path / "cache"
        with (
            patch("soundweave.stages.download.run_ytdlp", return_value=_completed()),
            pytest.raises(YtDlpError),
        ):
            download_audio(
                "https://youtube.com/watch?v=abc123", "abc123", cache_dir, logger
            )


# ---------------------------------------------------------------------------
# download_stage — end-to-end with everything mocked
# ---------------------------------------------------------------------------

class TestDownloadStage:
    def _base_config(self, tmp_path, urls, **kwargs):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("\n".join(urls) + "\n")
        return MashupConfig(urls_file=urls_file, output_dir=tmp_path / "out", **kwargs)

    def test_downloads_all_tracks_in_listed_order(self, tmp_path, logger):
        urls = [
            "https://youtube.com/watch?v=aaa",
            "https://youtube.com/watch?v=bbb",
        ]
        config = self._base_config(tmp_path, urls)

        def fake_fetch_metadata(url, logger, timeout=30):
            vid = url.rsplit("=", 1)[-1]
            return {"id": vid, "title": f"Title {vid}", "uploader": "Channel"}

        def fake_download_audio(url, video_id, cache_dir, logger, timeout=None):
            path = tmp_path / f"{video_id}.m4a"
            path.write_bytes(b"audio")
            return path

        fake_probe = AudioMetadata(duration_s=120.0, sample_rate=44100, channels=2, codec="aac")

        with patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"), \
             patch("soundweave.stages.download.fetch_metadata", side_effect=fake_fetch_metadata), \
             patch("soundweave.stages.download.download_audio", side_effect=fake_download_audio), \
             patch("soundweave.stages.download.probe_audio_file", return_value=fake_probe):
            tracks = download_stage(config, logger)

        assert len(tracks) == 2
        assert all(isinstance(t, MashupTrack) for t in tracks)
        # As-listed order preserved (no shuffle by default)
        assert tracks[0].video_title == "Title aaa"
        assert tracks[1].video_title == "Title bbb"
        assert tracks[0].source_url == "https://youtube.com/watch?v=aaa"
        assert tracks[0].filename == "Title aaa"

    def test_single_failed_url_is_skipped_with_warning(self, tmp_path, logger, caplog):
        urls = [
            "https://youtube.com/watch?v=good",
            "https://youtube.com/watch?v=bad",
        ]
        config = self._base_config(tmp_path, urls)

        def fake_fetch_metadata(url, logger, timeout=30):
            if "bad" in url:
                raise YtDlpError("video unavailable")
            return {"id": "good", "title": "Good Song", "uploader": "Channel"}

        def fake_download_audio(url, video_id, cache_dir, logger, timeout=None):
            path = tmp_path / f"{video_id}.m4a"
            path.write_bytes(b"audio")
            return path

        fake_probe = AudioMetadata(duration_s=120.0, sample_rate=44100, channels=2, codec="aac")

        with patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"), \
             patch("soundweave.stages.download.fetch_metadata", side_effect=fake_fetch_metadata), \
             patch("soundweave.stages.download.download_audio", side_effect=fake_download_audio), \
             patch("soundweave.stages.download.probe_audio_file", return_value=fake_probe):
            tracks = download_stage(config, logger)

        # Only the good URL succeeded — the run was not aborted.
        assert len(tracks) == 1
        assert tracks[0].video_title == "Good Song"

    def test_unsafe_video_id_is_skipped_not_used_as_path(self, tmp_path, logger):
        """urls.txt only requires http(s)://, not a youtube.com domain, so a
        video "id" from some other yt-dlp-supported extractor isn't
        guaranteed to be path-safe. An id containing path separators must be
        rejected rather than used to build a cache file path."""
        urls = [
            "https://example.com/watch?v=good",
            "https://example.com/watch?v=evil",
        ]
        config = self._base_config(tmp_path, urls)

        def fake_fetch_metadata(url, logger, timeout=30):
            if "evil" in url:
                return {"id": "../../etc/passwd", "title": "Evil", "uploader": "x"}
            return {"id": "good", "title": "Good Song", "uploader": "Channel"}

        def fake_download_audio(url, video_id, cache_dir, logger, timeout=None):
            path = tmp_path / f"{video_id}.m4a"
            path.write_bytes(b"audio")
            return path

        fake_probe = AudioMetadata(duration_s=120.0, sample_rate=44100, channels=2, codec="aac")

        with (
            patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"),
            patch("soundweave.stages.download.fetch_metadata", side_effect=fake_fetch_metadata),
            patch("soundweave.stages.download.download_audio", side_effect=fake_download_audio),
            patch("soundweave.stages.download.probe_audio_file", return_value=fake_probe),
        ):
            tracks = download_stage(config, logger)

        # The unsafe id was skipped like any other failed URL — download_audio
        # (and therefore the path built from video_id) was never reached for it.
        assert len(tracks) == 1
        assert tracks[0].video_title == "Good Song"

    def test_strict_mode_aborts_on_first_failure(self, tmp_path, logger):
        urls = [
            "https://youtube.com/watch?v=good",
            "https://youtube.com/watch?v=bad",
        ]
        config = self._base_config(tmp_path, urls, strict=True)

        def fake_fetch_metadata(url, logger, timeout=30):
            if "bad" in url:
                raise YtDlpError("video unavailable")
            return {"id": "good", "title": "Good Song", "uploader": "Channel"}

        def fake_download_audio(url, video_id, cache_dir, logger, timeout=None):
            path = tmp_path / f"{video_id}.m4a"
            path.write_bytes(b"audio")
            return path

        fake_probe = AudioMetadata(duration_s=120.0, sample_rate=44100, channels=2, codec="aac")

        with (
            patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"),
            patch("soundweave.stages.download.fetch_metadata", side_effect=fake_fetch_metadata),
            patch("soundweave.stages.download.download_audio", side_effect=fake_download_audio),
            patch("soundweave.stages.download.probe_audio_file", return_value=fake_probe),
            pytest.raises(ValidationError),
        ):
            download_stage(config, logger)

    def test_all_urls_failing_raises(self, tmp_path, logger):
        urls = ["https://youtube.com/watch?v=bad1", "https://youtube.com/watch?v=bad2"]
        config = self._base_config(tmp_path, urls)

        with (
            patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"),
            patch(
                "soundweave.stages.download.fetch_metadata",
                side_effect=YtDlpError("unavailable"),
            ),
            pytest.raises(ValidationError),
        ):
            download_stage(config, logger)

    def test_shuffle_still_returns_all_tracks(self, tmp_path, logger):
        urls = [f"https://youtube.com/watch?v={i}" for i in range(5)]
        config = self._base_config(tmp_path, urls, shuffle=True)

        def fake_fetch_metadata(url, logger, timeout=30):
            vid = url.rsplit("=", 1)[-1]
            return {"id": vid, "title": f"Title {vid}", "uploader": "Channel"}

        def fake_download_audio(url, video_id, cache_dir, logger, timeout=None):
            path = tmp_path / f"{video_id}.m4a"
            path.write_bytes(b"audio")
            return path

        fake_probe = AudioMetadata(duration_s=60.0, sample_rate=44100, channels=2, codec="aac")

        with patch("soundweave.stages.download.validate_ytdlp", return_value="2024.01.01"), \
             patch("soundweave.stages.download.fetch_metadata", side_effect=fake_fetch_metadata), \
             patch("soundweave.stages.download.download_audio", side_effect=fake_download_audio), \
             patch("soundweave.stages.download.probe_audio_file", return_value=fake_probe):
            tracks = download_stage(config, logger)

        assert len(tracks) == 5
        assert {t.video_title for t in tracks} == {f"Title {i}" for i in range(5)}

    def test_missing_ytdlp_raises_validation_error(self, tmp_path, logger):
        urls = ["https://youtube.com/watch?v=aaa"]
        config = self._base_config(tmp_path, urls)

        with patch(
            "soundweave.stages.download.validate_ytdlp",
            side_effect=ValidationError("yt-dlp not found"),
        ), pytest.raises(ValidationError):
            download_stage(config, logger)
