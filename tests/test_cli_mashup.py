"""Tests for the 'mashup' subcommand's CLI argument parsing (cli.py).

Only argument parsing is exercised here — no subprocess/network calls happen
since parse_mashup_args() doesn't touch yt-dlp or FFmpeg.
"""

from pathlib import Path

import pytest

from soundweave.cli import parse_mashup_args
from soundweave.mashup_config import DEFAULT_FADE_MS


class TestParseMashupArgs:
    def test_required_args(self):
        args = parse_mashup_args(["--urls", "urls.txt", "--output", "output"])
        assert args.urls == Path("urls.txt")
        assert args.output == Path("output")

    def test_defaults(self):
        args = parse_mashup_args(["--urls", "urls.txt", "--output", "output"])
        assert args.fade_ms == DEFAULT_FADE_MS
        assert args.shuffle is False
        assert args.strict is False
        assert args.cache_dir is None
        assert args.image is None
        assert args.images_dir is None
        assert args.animated_background is None

    def test_fade_ms_override(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--fade-ms", "5000"]
        )
        assert args.fade_ms == 5000

    def test_shuffle_flag(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--shuffle"]
        )
        assert args.shuffle is True

    def test_strict_flag(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--strict"]
        )
        assert args.strict is True

    def test_cache_dir_override(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--cache-dir", "/tmp/mycache"]
        )
        assert args.cache_dir == Path("/tmp/mycache")

    def test_image_flag(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--image", "cover.png"]
        )
        assert args.image == Path("cover.png")
        assert args.images_dir is None

    def test_images_flag(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--images", "covers/"]
        )
        assert args.images_dir == Path("covers/")
        assert args.image is None

    def test_image_and_images_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_mashup_args(
                [
                    "--urls", "urls.txt", "--output", "output",
                    "--image", "cover.png", "--images", "covers/",
                ]
            )

    def test_animated_background_flag(self):
        args = parse_mashup_args(
            ["--urls", "urls.txt", "--output", "output", "--animated-background", "loop.mp4"]
        )
        assert args.animated_background == Path("loop.mp4")
        assert args.image is None
        assert args.images_dir is None

    def test_animated_background_and_image_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_mashup_args(
                [
                    "--urls", "urls.txt", "--output", "output",
                    "--image", "cover.png", "--animated-background", "loop.mp4",
                ]
            )

    def test_animated_background_and_images_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_mashup_args(
                [
                    "--urls", "urls.txt", "--output", "output",
                    "--images", "covers/", "--animated-background", "loop.mp4",
                ]
            )
