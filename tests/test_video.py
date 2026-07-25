"""Tests for the per-track image-swap video sequence logic (PRD.md §7).

These tests exercise the pure timing/pairing logic in
`soundweave.stages.video` and the pure command-builder in
`soundweave.ffmpeg.commands`. Nothing here shells out to real FFmpeg:
`video_sequence_stage()` is exercised with `run_ffmpeg` and
`probe_audio_file` mocked out, and `build_video_sequence_command()` is a
pure function that only returns an argument list.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from soundweave.ffmpeg.commands import build_video_sequence_command
from soundweave.stages.video import (
    calculate_sequence_duration,
    match_images_to_tracks,
    video_sequence_stage,
)
from soundweave.utils.validators import ValidationError


@pytest.fixture
def logger():
    log = logging.getLogger("test_video")
    log.addHandler(logging.NullHandler())
    return log


# --- match_images_to_tracks ---------------------------------------------


def test_match_images_to_tracks_pairs_1to1_in_order():
    images = [Path("a.png"), Path("b.png"), Path("c.png")]
    durations = [10.0, 20.0, 30.0]

    result = match_images_to_tracks(images, durations)

    assert result == [
        (Path("a.png"), 10.0),
        (Path("b.png"), 20.0),
        (Path("c.png"), 30.0),
    ]


def test_match_images_to_tracks_exact_count():
    images = [Path("a.png"), Path("b.png")]
    durations = [5.0, 7.5]

    result = match_images_to_tracks(images, durations)

    assert len(result) == 2
    assert result[0] == (Path("a.png"), 5.0)
    assert result[1] == (Path("b.png"), 7.5)


def test_match_images_to_tracks_drops_extra_images():
    images = [Path("a.png"), Path("b.png"), Path("c.png"), Path("d.png")]
    durations = [1.0, 2.0]

    result = match_images_to_tracks(images, durations)

    assert result == [(Path("a.png"), 1.0), (Path("b.png"), 2.0)]


def test_match_images_to_tracks_fewer_images_than_tracks_raises():
    images = [Path("a.png")]
    durations = [1.0, 2.0, 3.0]

    with pytest.raises(ValidationError):
        match_images_to_tracks(images, durations)


def test_match_images_to_tracks_error_message_is_explicit():
    """Error should explain the count mismatch, not just fail silently."""
    images = [Path("a.png")]
    durations = [1.0, 2.0]

    with pytest.raises(ValidationError, match=r"1 image.*2 track"):
        match_images_to_tracks(images, durations)


def test_match_images_to_tracks_zero_images_zero_tracks():
    assert match_images_to_tracks([], []) == []


def test_match_images_to_tracks_zero_images_some_tracks_raises():
    with pytest.raises(ValidationError):
        match_images_to_tracks([], [1.0])


# --- calculate_sequence_duration ----------------------------------------


def test_calculate_sequence_duration_sums_durations():
    sequence = [
        (Path("a.png"), 10.0),
        (Path("b.png"), 20.5),
        (Path("c.png"), 5.25),
    ]

    assert calculate_sequence_duration(sequence) == pytest.approx(35.75)


def test_calculate_sequence_duration_empty_is_zero():
    assert calculate_sequence_duration([]) == 0.0


def test_calculate_sequence_duration_single_image():
    assert calculate_sequence_duration([(Path("a.png"), 42.0)]) == pytest.approx(42.0)


# --- build_video_sequence_command (pure command builder) ----------------


def test_build_video_sequence_command_one_input_per_image_plus_audio():
    sequence = [(Path("a.png"), 10.0), (Path("b.png"), 20.0), (Path("c.png"), 30.0)]
    audio_path = Path("audio.wav")
    output_path = Path("out.mp4")

    cmd = build_video_sequence_command(audio_path, sequence, output_path)

    # 3 images + 1 audio track = 4 "-i" inputs
    assert cmd.count("-i") == 4
    # Each image path and the audio path appear as an input
    assert str(Path("a.png")) in cmd
    assert str(Path("b.png")) in cmd
    assert str(Path("c.png")) in cmd
    assert str(audio_path) in cmd


def test_build_video_sequence_command_per_image_hold_durations():
    sequence = [(Path("a.png"), 10.0), (Path("b.png"), 20.0)]
    cmd = build_video_sequence_command(Path("audio.wav"), sequence, Path("out.mp4"))

    # Each image is preceded by "-loop 1 -t <duration> -i"
    idx_a = cmd.index(str(Path("a.png")))
    idx_b = cmd.index(str(Path("b.png")))
    assert cmd[idx_a - 5 : idx_a] == ["-loop", "1", "-t", "10.0", "-i"]
    assert cmd[idx_b - 5 : idx_b] == ["-loop", "1", "-t", "20.0", "-i"]


def test_build_video_sequence_command_concat_filter_covers_all_images():
    sequence = [(Path(f"img{i}.png"), float(i + 1)) for i in range(5)]
    cmd = build_video_sequence_command(Path("audio.wav"), sequence, Path("out.mp4"))

    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=5:v=1:a=0" in filter_complex
    for i in range(5):
        assert f"[v{i}]" in filter_complex


def test_build_video_sequence_command_maps_concat_video_and_audio():
    sequence = [(Path("a.png"), 10.0), (Path("b.png"), 20.0)]
    cmd = build_video_sequence_command(Path("audio.wav"), sequence, Path("out.mp4"))

    assert "-map" in cmd
    assert "[outv]" in cmd
    # Audio is the input right after the two image inputs -> index 2
    assert "2:a" in cmd


def test_build_video_sequence_command_output_path_is_last_arg():
    sequence = [(Path("a.png"), 10.0)]
    output_path = Path("out.mp4")
    cmd = build_video_sequence_command(Path("audio.wav"), sequence, output_path)

    assert cmd[-1] == str(output_path)


def test_build_video_sequence_command_empty_sequence_raises():
    with pytest.raises(ValueError):
        build_video_sequence_command(Path("audio.wav"), [], Path("out.mp4"))


def test_build_video_sequence_command_does_not_execute_anything():
    """Pure function: returns a list, never touches the filesystem/subprocess."""
    sequence = [(Path("nonexistent.png"), 1.0)]
    cmd = build_video_sequence_command(
        Path("also_nonexistent.wav"), sequence, Path("also_nonexistent.mp4")
    )
    assert isinstance(cmd, list)
    assert all(isinstance(arg, str) for arg in cmd)


# --- video_sequence_stage (orchestration, FFmpeg execution mocked) ------


def test_video_sequence_stage_rejects_empty_sequence(tmp_path, logger):
    with pytest.raises(ValidationError):
        video_sequence_stage(Path("audio.wav"), [], tmp_path, logger)


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_sequence_stage_total_duration_matches_sum(
    mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, logger
):
    """Total rendered duration (per probe/audio) should line up with the
    sum of per-image hold durations -- no warning should be logged when
    they match."""
    from soundweave.ffmpeg.probe import AudioMetadata

    sequence = [
        (tmp_path / "a.png", 12.0),
        (tmp_path / "b.png", 8.0),
        (tmp_path / "c.png", 5.0),
    ]
    for image_path, _ in sequence:
        image_path.touch()

    total = calculate_sequence_duration(sequence)
    mock_probe.return_value = AudioMetadata(
        duration_s=total, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    output_path = video_sequence_stage(audio_path, sequence, tmp_path, logger)

    assert total == pytest.approx(25.0)
    assert output_path == tmp_path / "final_video.mp4"
    mock_run_ffmpeg.assert_called_once()
    # First positional arg to run_ffmpeg is the built command
    built_command = mock_run_ffmpeg.call_args[0][0]
    assert built_command[-1] == str(output_path)


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_sequence_stage_warns_on_duration_drift(
    mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, caplog
):
    from soundweave.ffmpeg.probe import AudioMetadata

    sequence = [(tmp_path / "a.png", 10.0)]
    sequence[0][0].touch()

    # Audio duration is way off from the sequence's 10.0s
    mock_probe.return_value = AudioMetadata(
        duration_s=50.0, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    log = logging.getLogger("test_video_drift")
    with caplog.at_level(logging.WARNING):
        video_sequence_stage(audio_path, sequence, tmp_path, log)

    assert any("differs from" in record.message for record in caplog.records)


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_sequence_stage_copies_first_image_as_thumbnail(
    mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, logger
):
    from soundweave.ffmpeg.probe import AudioMetadata

    sequence = [(tmp_path / "first.png", 10.0), (tmp_path / "second.jpg", 10.0)]
    for image_path, _ in sequence:
        image_path.touch()

    mock_probe.return_value = AudioMetadata(
        duration_s=20.0, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    video_sequence_stage(audio_path, sequence, tmp_path, logger)

    mock_copy2.assert_called_once()
    src, dst = mock_copy2.call_args[0]
    assert src == tmp_path / "first.png"
    assert dst == tmp_path / "thumbnail.png"
