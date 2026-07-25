"""Tests for soundweave/ytdlp/commands.py — pure command builders."""

from soundweave.ytdlp.commands import build_download_command, build_metadata_command


class TestBuildMetadataCommand:
    def test_includes_url(self):
        cmd = build_metadata_command("https://youtube.com/watch?v=abc123")
        assert "https://youtube.com/watch?v=abc123" in cmd

    def test_no_download_flags(self):
        cmd = build_metadata_command("https://youtube.com/watch?v=abc123")
        assert "--dump-json" in cmd
        assert "--skip-download" in cmd
        assert "--no-playlist" in cmd

    def test_returns_list_of_strings(self):
        cmd = build_metadata_command("https://youtube.com/watch?v=abc123")
        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)

    def test_starts_with_binary_name(self):
        cmd = build_metadata_command("https://youtube.com/watch?v=abc123")
        assert cmd[0] == "yt-dlp"


class TestBuildDownloadCommand:
    def test_includes_url_and_template(self):
        cmd = build_download_command(
            "https://youtube.com/watch?v=abc123", "/cache/abc123.%(ext)s"
        )
        assert "https://youtube.com/watch?v=abc123" in cmd
        assert "/cache/abc123.%(ext)s" in cmd

    def test_audio_only_extraction(self):
        cmd = build_download_command(
            "https://youtube.com/watch?v=abc123", "/cache/abc123.%(ext)s"
        )
        assert "-x" in cmd
        assert "--audio-format" in cmd
        assert "m4a" in cmd
        assert "--no-playlist" in cmd

    def test_output_template_follows_o_flag(self):
        cmd = build_download_command(
            "https://youtube.com/watch?v=abc123", "/cache/abc123.%(ext)s"
        )
        o_index = cmd.index("-o")
        assert cmd[o_index + 1] == "/cache/abc123.%(ext)s"

    def test_returns_list_of_strings(self):
        cmd = build_download_command("https://youtube.com/watch?v=abc123", "tmpl")
        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)
