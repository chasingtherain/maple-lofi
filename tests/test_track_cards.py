"""Tests for T1 "now playing" track-title cards.

Covers:
- `escape_filtergraph_value()` / `build_track_card_drawtext_filters()`
  (pure, `soundweave.ffmpeg.commands`) -- exercised directly against
  tricky titles/paths (quotes, colons, percent signs, backslashes), not
  just the happy path, per this project's verification standard.
- `write_track_card_text_files()` / `resolve_track_card_font()`
  (`soundweave.stages.video`) -- filesystem-touching but not FFmpeg-
  touching; exercised against tmp_path directly.
- `build_video_command()` / `build_video_sequence_command()`'s optional
  `track_cards_filter` param -- confirms the two existing video modes are
  byte-for-byte unchanged when the param is omitted, and correctly
  layered on when given.
- `video_stage()` / `video_sequence_stage()` wiring -- `run_ffmpeg`/
  `probe_audio_file` mocked out, asserting on the built command.

Nothing here shells out to real FFmpeg -- see the manual verification
(real render + frame extraction) recorded in the T1 commit message for
that side of the verification standard.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from soundweave.ffmpeg.commands import (
    build_track_card_drawtext_filters,
    build_video_command,
    build_video_sequence_command,
    escape_filtergraph_value,
)
from soundweave.stages.video import (
    resolve_track_card_font,
    video_sequence_stage,
    video_stage,
    write_track_card_text_files,
)
from soundweave.utils.validators import ValidationError


@pytest.fixture
def logger():
    log = logging.getLogger("test_track_cards")
    log.addHandler(logging.NullHandler())
    return log


# --- escape_filtergraph_value --------------------------------------------


def test_escape_filtergraph_value_wraps_in_single_quotes():
    assert escape_filtergraph_value("plain") == "'plain'"


def test_escape_filtergraph_value_escapes_colon():
    # Empirically verified: unescaped ':' breaks filter-option parsing even
    # inside single quotes on this project's ffmpeg build.
    assert escape_filtergraph_value("a:b") == "'a\\:b'"


def test_escape_filtergraph_value_escapes_backslash():
    assert escape_filtergraph_value("a\\b") == "'a\\\\b'"


def test_escape_filtergraph_value_handles_windows_style_path():
    result = escape_filtergraph_value("C:\\Users\\weird")
    assert result == "'C\\:\\\\Users\\\\weird'"


def test_escape_filtergraph_value_empty_string():
    assert escape_filtergraph_value("") == "''"


# --- build_track_card_drawtext_filters -----------------------------------


def test_build_track_card_filters_empty_raises():
    with pytest.raises(ValueError):
        build_track_card_drawtext_filters([], Path("font.ttf"))


def test_build_track_card_filters_rejects_nonpositive_duration():
    with pytest.raises(ValueError):
        build_track_card_drawtext_filters(
            [(Path("a.txt"), 0.0)], Path("font.ttf"), card_duration_s=0
        )


def test_build_track_card_filters_rejects_overlapping_fades():
    with pytest.raises(ValueError):
        build_track_card_drawtext_filters(
            [(Path("a.txt"), 0.0)],
            Path("font.ttf"),
            card_duration_s=2.0,
            fade_s=1.5,  # 2 * 1.5 > 2.0
        )


def test_build_track_card_filters_one_clause_per_track():
    cards = [(Path("card_000.txt"), 0.0), (Path("card_001.txt"), 30.0)]
    result = build_track_card_drawtext_filters(cards, Path("font.ttf"))

    # comma-joined, one drawtext= clause per track, no leading/trailing comma
    assert result.count("drawtext=") == 2
    assert not result.startswith(",")
    assert not result.endswith(",")


def test_build_track_card_filters_includes_textfile_and_expansion_none():
    cards = [(Path("/tmp/cards/card_000.txt"), 0.0)]
    result = build_track_card_drawtext_filters(cards, Path("/tmp/font.ttf"))

    assert "textfile='/tmp/cards/card_000.txt'" in result
    assert "expansion=none" in result
    assert "fontfile='/tmp/font.ttf'" in result


def test_build_track_card_filters_enable_window_matches_start_and_duration():
    cards = [(Path("card_000.txt"), 12.5)]
    result = build_track_card_drawtext_filters(cards, Path("font.ttf"), card_duration_s=5.0)

    assert "enable='between(t,12.500,17.500)'" in result


def test_build_track_card_filters_alpha_expr_uses_fade_s():
    cards = [(Path("card_000.txt"), 0.0)]
    result = build_track_card_drawtext_filters(
        cards, Path("font.ttf"), card_duration_s=5.0, fade_s=1.0
    )

    # fade-in ramps 0->1 over [0, 1); fade-out ramps over [4, 5)
    assert "if(lt(t,1.000),(t-0.000)/1.000," in result
    assert "if(lt(t,4.000),1,(5.000-t)/1.000)" in result


def test_build_track_card_filters_colon_in_path_is_escaped():
    # Self-generated paths shouldn't normally contain colons, but the
    # escaping helper is applied defensively -- confirm it actually is.
    cards = [(Path("/weird:path/card.txt"), 0.0)]
    result = build_track_card_drawtext_filters(cards, Path("font.ttf"))

    assert "textfile='/weird\\:path/card.txt'" in result


def test_build_track_card_filters_preserves_track_order():
    cards = [
        (Path("card_000.txt"), 0.0),
        (Path("card_001.txt"), 10.0),
        (Path("card_002.txt"), 25.0),
    ]
    result = build_track_card_drawtext_filters(cards, Path("font.ttf"))
    clauses = result.split(",drawtext=")

    assert "card_000.txt" in clauses[0]
    assert "12.500" not in clauses[0]  # sanity: not the wrong track's window


def test_build_track_card_filters_does_not_touch_filesystem(tmp_path):
    """Pure function: nonexistent paths are fine, nothing is read/written."""
    cards = [(tmp_path / "does_not_exist.txt", 0.0)]
    result = build_track_card_drawtext_filters(cards, tmp_path / "no_font.ttf")
    assert isinstance(result, str)


# --- write_track_card_text_files -----------------------------------------


def test_write_track_card_text_files_creates_subdir(tmp_path):
    result = write_track_card_text_files([("Track One", 0.0)], tmp_path)

    assert (tmp_path / "track_cards").is_dir()
    assert result[0][0].parent == tmp_path / "track_cards"


def test_write_track_card_text_files_content_matches_title(tmp_path):
    result = write_track_card_text_files([("Simple Title", 0.0)], tmp_path)
    text_file, start_s = result[0]

    assert text_file.read_text(encoding="utf-8") == "Simple Title"
    assert start_s == 0.0


def test_write_track_card_text_files_round_trips_tricky_titles(tmp_path):
    """Real-world tricky titles: quotes, colons, percent signs, backslashes.
    Since drawtext reads this file with expansion=none, the file content
    must be the *exact* raw title, with zero escaping/mangling."""
    tricky_titles = [
        'Artist: "Track" (Live)',
        "Don't Stop",
        "50% Off: A Song",
        "C:\\Users\\weird",
        "Semi;colon,comma[bracket]test",
        "100%\\n literal backslash-n",
    ]
    cards = [(title, float(i)) for i, title in enumerate(tricky_titles)]

    result = write_track_card_text_files(cards, tmp_path)

    assert len(result) == len(tricky_titles)
    for (text_file, start_s), title, expected_start in zip(
        result, tricky_titles, range(len(tricky_titles))
    ):
        assert text_file.read_text(encoding="utf-8") == title
        assert start_s == float(expected_start)


def test_write_track_card_text_files_preserves_order_and_naming(tmp_path):
    result = write_track_card_text_files(
        [("First", 0.0), ("Second", 10.0), ("Third", 20.0)], tmp_path
    )

    names = [p.name for p, _ in result]
    assert names == ["card_000.txt", "card_001.txt", "card_002.txt"]


# --- resolve_track_card_font ----------------------------------------------


def test_resolve_track_card_font_explicit_path_exists(tmp_path):
    font_file = tmp_path / "my_font.ttf"
    font_file.touch()

    result = resolve_track_card_font(font_file)

    assert result == font_file


def test_resolve_track_card_font_explicit_path_missing_raises(tmp_path):
    with pytest.raises(ValidationError, match="not found"):
        resolve_track_card_font(tmp_path / "does_not_exist.ttf")


@patch("soundweave.stages.video.DEFAULT_FONT_CANDIDATES", new=[])
def test_resolve_track_card_font_no_candidates_raises():
    with pytest.raises(ValidationError, match="No font available"):
        resolve_track_card_font(None)


def test_resolve_track_card_font_falls_back_to_first_existing_candidate(tmp_path):
    missing = tmp_path / "missing.ttf"
    present = tmp_path / "present.ttf"
    present.touch()

    with patch(
        "soundweave.stages.video.DEFAULT_FONT_CANDIDATES", new=[missing, present]
    ):
        result = resolve_track_card_font(None)

    assert result == present


# --- build_video_command (track_cards_filter param) -----------------------


def test_build_video_command_unchanged_when_track_cards_filter_omitted():
    without_param = build_video_command(
        Path("audio.wav"), Path("cover.png"), Path("out.mp4"), 100.0
    )
    with_none = build_video_command(
        Path("audio.wav"), Path("cover.png"), Path("out.mp4"), 100.0, track_cards_filter=None
    )

    assert without_param == with_none
    vf = without_param[without_param.index("-vf") + 1]
    assert "drawtext" not in vf


def test_build_video_command_appends_track_cards_filter_to_vf():
    cmd = build_video_command(
        Path("audio.wav"),
        Path("cover.png"),
        Path("out.mp4"),
        100.0,
        track_cards_filter="drawtext=textfile='x.txt':expansion=none",
    )
    vf = cmd[cmd.index("-vf") + 1]

    assert vf.startswith("scale=1920:1080")
    assert vf.endswith("drawtext=textfile='x.txt':expansion=none")
    assert ",drawtext=" in vf


# --- build_video_sequence_command (track_cards_filter param) --------------


def test_build_video_sequence_command_unchanged_when_track_cards_filter_omitted():
    sequence = [(Path("a.png"), 10.0), (Path("b.png"), 20.0)]

    without_param = build_video_sequence_command(Path("audio.wav"), sequence, Path("out.mp4"))
    with_none = build_video_sequence_command(
        Path("audio.wav"), sequence, Path("out.mp4"), track_cards_filter=None
    )

    assert without_param == with_none
    assert "[outv]" in without_param
    assert "outv_cards" not in " ".join(without_param)


def test_build_video_sequence_command_layers_track_cards_onto_outv():
    sequence = [(Path("a.png"), 10.0), (Path("b.png"), 20.0)]

    cmd = build_video_sequence_command(
        Path("audio.wav"),
        sequence,
        Path("out.mp4"),
        track_cards_filter="drawtext=textfile='x.txt':expansion=none",
    )
    filter_complex = cmd[cmd.index("-filter_complex") + 1]

    assert "[outv]drawtext=textfile='x.txt':expansion=none[outv_cards]" in filter_complex
    # Final map should point at the track-cards output, not the raw concat
    map_idx = cmd.index("-map")
    assert cmd[map_idx + 1] == "[outv_cards]"


# --- video_stage / video_sequence_stage wiring -----------------------------


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_stage_no_track_cards_by_default(mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, logger):
    from soundweave.config import PipelineConfig
    from soundweave.ffmpeg.probe import AudioMetadata

    cover = tmp_path / "cover.png"
    cover.touch()
    mock_probe.return_value = AudioMetadata(
        duration_s=10.0, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    config = PipelineConfig(
        input_dir=tmp_path, output_dir=tmp_path, static_image=cover
    )
    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    video_stage(audio_path, config, logger)

    built_command = mock_run_ffmpeg.call_args[0][0]
    vf = built_command[built_command.index("-vf") + 1]
    assert "drawtext" not in vf
    assert not (tmp_path / "track_cards").exists()


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_stage_with_track_cards_writes_files_and_adds_drawtext(
    mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, logger
):
    from soundweave.config import PipelineConfig
    from soundweave.ffmpeg.probe import AudioMetadata

    cover = tmp_path / "cover.png"
    cover.touch()
    font_file = tmp_path / "font.ttf"
    font_file.touch()
    mock_probe.return_value = AudioMetadata(
        duration_s=10.0, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    config = PipelineConfig(
        input_dir=tmp_path, output_dir=tmp_path, static_image=cover
    )
    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    video_stage(
        audio_path,
        config,
        logger,
        track_cards=[("Artist: \"Track\" (Live)", 0.0), ("Second Track", 5.0)],
        font_path=font_file,
    )

    assert (tmp_path / "track_cards" / "card_000.txt").read_text(encoding="utf-8") == (
        'Artist: "Track" (Live)'
    )
    built_command = mock_run_ffmpeg.call_args[0][0]
    vf = built_command[built_command.index("-vf") + 1]
    assert vf.count("drawtext=") == 2


@patch("soundweave.stages.video.shutil.copy2")
@patch("soundweave.stages.video.run_ffmpeg")
@patch("soundweave.stages.video.probe_audio_file")
def test_video_sequence_stage_with_track_cards_adds_drawtext(
    mock_probe, mock_run_ffmpeg, mock_copy2, tmp_path, logger
):
    from soundweave.ffmpeg.probe import AudioMetadata

    sequence = [(tmp_path / "a.png", 10.0)]
    sequence[0][0].touch()
    font_file = tmp_path / "font.ttf"
    font_file.touch()

    mock_probe.return_value = AudioMetadata(
        duration_s=10.0, sample_rate=48000, channels=2, codec="pcm_s16le"
    )

    def _fake_render(*args, **kwargs):
        (tmp_path / "final_video.mp4").touch()

    mock_run_ffmpeg.side_effect = _fake_render

    audio_path = tmp_path / "merged.wav"
    audio_path.touch()

    video_sequence_stage(
        audio_path,
        sequence,
        tmp_path,
        logger,
        track_cards=[("Only Track", 0.0)],
        font_path=font_file,
    )

    built_command = mock_run_ffmpeg.call_args[0][0]
    filter_complex = built_command[built_command.index("-filter_complex") + 1]
    assert "outv_cards" in filter_complex
    map_idx = built_command.index("-map")
    assert built_command[map_idx + 1] == "[outv_cards]"
