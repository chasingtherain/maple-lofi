"""FFmpeg command builders for each pipeline stage."""

from pathlib import Path

from soundweave.stages.ingest import AudioTrack


def build_merge_command(
    tracks: list[AudioTrack],
    output_path: Path,
    crossfade_durations: list[float],
) -> list[str]:
    """Build FFmpeg command for merging tracks with crossfades.

    Args:
        tracks: List of audio tracks to merge
        output_path: Path for output WAV file
        crossfade_durations: Crossfade duration (in seconds) between each pair

    Returns:
        FFmpeg command as list of arguments

    FFmpeg approach:
        - Use acrossfade filter for smooth crossfading
        - Resample all inputs to 48kHz, 16-bit PCM
        - Chain crossfades sequentially
    """
    if len(tracks) == 0:
        raise ValueError("Cannot merge zero tracks")

    if len(tracks) == 1:
        # Single track: normalize and convert to target format
        track = tracks[0]
        return [
            "ffmpeg",
            "-i", str(track.path),
            "-af", "silenceremove=stop_periods=1:stop_duration=0.5:stop_threshold=-50dB,loudnorm=I=-20:TP=-1.5:LRA=11",
            "-ar", "48000",              # Resample to 48kHz
            "-ac", "2",                  # Stereo
            "-sample_fmt", "s16",        # 16-bit PCM
            "-y",                        # Overwrite output
            str(output_path)
        ]

    # Multiple tracks: build crossfade filter chain
    cmd = ["ffmpeg"]

    # Add all input files
    for track in tracks:
        cmd.extend(["-i", str(track.path)])

    # Build filter_complex for crossfading
    # Strategy:
    # 1. Normalize loudness of each track to -20 LUFS
    # 2. Chain acrossfade filters
    # [0:a]loudnorm[norm0]; [1:a]loudnorm[norm1]; [norm0][norm1]acrossfade[a1]; ...

    filter_parts = []

    # Step 1: Trim trailing silence and normalize loudness for each input track
    for i in range(len(tracks)):
        filter_parts.append(
            f"[{i}:a]silenceremove=stop_periods=1:stop_duration=0.5:stop_threshold=-50dB,loudnorm=I=-20:TP=-1.5:LRA=11[norm{i}]"
        )

    # Step 2: Chain crossfades using normalized streams
    current_label = "norm0"

    for i in range(len(tracks) - 1):
        next_input = f"norm{i + 1}"
        crossfade_s = crossfade_durations[i]
        output_label = f"a{i + 1}"

        # acrossfade filter: [input1][input2]acrossfade=d=duration:c1=tri:c2=tri[output]
        # c1=tri, c2=tri gives smooth triangular crossfade curves
        filter_parts.append(
            f"[{current_label}][{next_input}]acrossfade=d={crossfade_s}:c1=tri:c2=tri[{output_label}]"
        )

        current_label = output_label

    filter_complex = ";".join(filter_parts)

    # Add filter_complex
    cmd.extend(["-filter_complex", filter_complex])

    # Map the final output and set format
    cmd.extend([
        "-map", f"[{current_label}]",  # Map final crossfaded audio
        "-ar", "48000",                 # 48kHz
        "-ac", "2",                     # Stereo
        "-sample_fmt", "s16",           # 16-bit PCM
        "-y",                           # Overwrite
        str(output_path)
    ])

    return cmd


def build_mp3_command(
    input_wav: Path,
    output_mp3: Path
) -> list[str]:
    """Build FFmpeg command for encoding WAV to MP3.

    Args:
        input_wav: Path to input WAV file
        output_mp3: Path for output MP3 file

    Returns:
        FFmpeg command as list of arguments
    """
    return [
        "ffmpeg",
        "-i", str(input_wav),
        "-codec:a", "libmp3lame",
        "-b:a", "320k",          # 320kbps CBR
        "-y",
        str(output_mp3)
    ]


def build_loop_command(
    input_file: Path,
    output_path: Path,
    count: int,
    gap_s: float,
    fade_s: float = 0.5,
    trim_db: float = -40.0,
    sample_rate: int = 48000,
) -> list[str]:
    """Build FFmpeg command to loop a single audio file N times.

    Each repetition has its quiet tail trimmed, then gets a fade-in at the
    start and a fade-out at the end. Between repetitions a silence segment
    is inserted.

    Args:
        input_file:   Path to the audio input file.
        output_path:  Path for the output MP3.
        count:        Number of times to play the file (>= 1).
        gap_s:        Silence between repetitions in seconds.
        fade_s:       Fade-in/out duration per repetition in seconds.
        trim_db:      dB threshold for trailing silence removal (e.g. -40.0).
                      Audio below this level at the end of each rep is removed
                      before the gap is inserted.
        sample_rate:  Sample rate for silence generation (default 48000).

    Returns:
        FFmpeg command as a list of argument strings.

    Raises:
        ValueError: If count < 1.

    Filter strategy per repetition:
        silenceremove  — trims trailing audio below trim_db
        afade=t=in     — fade in the start
        areverse       — reverse the stream
        afade=t=in     — fade in from the new start (= fade out original end)
        areverse       — reverse back to original order

    The areverse trick applies a fade-out without needing to know the
    post-trim duration, since silenceremove changes it dynamically.

    Segment concat:
        N reps + N-1 silence segments → concat=n=<2N-1>:v=0:a=1
        N=1 special case: no silence, no concat — [rep0] mapped directly.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")

    cmd = ["ffmpeg"]
    for _ in range(count):
        cmd.extend(["-i", str(input_file)])

    filter_parts = []

    for i in range(count):
        filter_parts.append(
            f"[{i}:a]"
            f"silenceremove=stop_periods=1:stop_duration=0.5:stop_threshold={trim_db}dB,"
            f"afade=t=in:st=0:d={fade_s:.6f},"
            f"areverse,"
            f"afade=t=in:st=0:d={fade_s:.6f},"
            f"areverse"
            f"[rep{i}]"
        )

    if count == 1:
        filter_complex = filter_parts[0]
        final_label = "rep0"
    else:
        for i in range(count - 1):
            filter_parts.append(
                f"aevalsrc=0:c=stereo:s={sample_rate}:d={gap_s:.6f}[sil{i}]"
            )

        concat_inputs = ""
        for i in range(count - 1):
            concat_inputs += f"[rep{i}][sil{i}]"
        concat_inputs += f"[rep{count - 1}]"

        n_segments = 2 * count - 1
        filter_parts.append(
            f"{concat_inputs}concat=n={n_segments}:v=0:a=1[out]"
        )
        filter_complex = ";".join(filter_parts)
        final_label = "out"

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", f"[{final_label}]"])
    cmd.extend([
        "-codec:a", "libmp3lame",
        "-b:a", "320k",
        "-y",
        str(output_path),
    ])

    return cmd


def escape_filtergraph_value(value: str) -> str:
    """Escape and single-quote a value for safe embedding in an ffmpeg
    filtergraph option (e.g. drawtext's ``textfile=``/``fontfile=``).

    Empirically verified against this project's ffmpeg build (8.0,
    libavfilter's option parser) while building the track-cards feature:
    unlike what the generic ffmpeg escaping docs might suggest, wrapping a
    value in single quotes does **not** protect an embedded ``:`` -- it
    still terminates option parsing early (``drawtext=text='A: B'`` fails
    with "No option name near ' B:...'"). ``:`` must be individually
    backslash-escaped regardless of quoting; backslashes themselves must
    be doubled.

    A literal single quote is deliberately **not** supported here: neither
    the shell-style ``'\\''`` breakout trick (which doesn't apply anyway
    since this project always execs ffmpeg via an argv list, never a
    shell) nor a backslash-escaped quote inside the quotes (which
    empirically renders the escaped text as-is except silently *dropping*
    the quote character, rather than erroring or keeping it) behaves
    correctly. That's an acceptable limitation because every caller of
    this function only ever passes a self-generated path (a temp filename
    this codebase creates itself, never arbitrary user text) -- see
    `build_track_card_drawtext_filters()` and
    `soundweave.stages.video.write_track_card_text_files()`. Track titles
    themselves (which realistically do contain quotes/colons/percent
    signs) never pass through this function -- they go through drawtext's
    ``textfile=`` + ``expansion=none``, which renders file content
    completely literally with no filtergraph escaping needed at all.

    Args:
        value: The raw value to embed (e.g. a filesystem path).

    Returns:
        The value, backslash-escaped and wrapped in single quotes, ready
        to splice directly into a filtergraph option string.
    """
    escaped = value.replace("\\", "\\\\").replace(":", "\\:")
    return f"'{escaped}'"


# Total on-screen window per track-title card, in seconds. Includes the
# fade-in and fade-out -- not additional to them. PRD/TASK.md spec: "fading
# in/out over ~4-5s ... one enable='between(t,start,start+5)' clause per
# track".
DEFAULT_TRACK_CARD_DURATION_S = 5.0
# Fade-in duration at the start of the window and fade-out duration at the
# end, in seconds. Must satisfy 2 * fade_s <= card_duration_s so the two
# fades don't overlap.
DEFAULT_TRACK_CARD_FADE_S = 1.0


def build_track_card_drawtext_filters(
    card_text_files: list[tuple[Path, float]],
    font_path: Path,
    card_duration_s: float = DEFAULT_TRACK_CARD_DURATION_S,
    fade_s: float = DEFAULT_TRACK_CARD_FADE_S,
) -> str:
    """Build the chained drawtext filter fragment for on-video "now playing"
    track-title cards (T1).

    Pure function: takes already-written text-file paths (one per track --
    see `soundweave.stages.video.write_track_card_text_files()` for the
    writing side, kept separate since this module's functions never touch
    the filesystem) paired with each track's actual start timestamp, and
    returns a comma-joined ffmpeg filter fragment with no leading/trailing
    comma. The caller splices it onto an existing ``-vf`` string (append
    ``,`` + fragment) or into a ``filter_complex`` graph (e.g.
    ``[outv]{fragment}[outv_cards]``) -- see `build_video_command()` and
    `build_video_sequence_command()`'s optional `track_cards_filter` param.

    Each card fades in over `fade_s` seconds starting at its track's start
    timestamp, holds fully opaque, then fades out over the final `fade_s`
    seconds of a `card_duration_s`-second on-screen window -- one
    ``enable='between(t,start,start+card_duration_s)'`` gate per track, per
    spec. Outside that window drawtext doesn't touch the frame at all (the
    ``enable`` timeline option short-circuits the filter), so the alpha
    expression only needs to handle in-window time.

    Text is loaded via ``textfile=`` with ``expansion=none`` rather than an
    inline ``text=`` value: empirical testing (see `escape_filtergraph_value()`'s
    docstring) found inline embedding unreliable for realistic titles --
    e.g. a lone ``%`` in a title text= value silently produced a blank
    render (exit 0, no error, no visible text) even after doubling to
    ``%%``, because drawtext's default ``expansion=normal`` mode still
    interprets ``%``/``\\`` specially even when the surrounding filtergraph
    quoting is correct. ``expansion=none`` + ``textfile=`` sidesteps all of
    that: the file's raw bytes are drawn completely literally, so a title
    like ``Artist: "Track" (Live)`` or ``50% Off: A Song`` just works with
    zero content escaping. Only the (self-generated, safe) file *path*
    needs filtergraph escaping, via `escape_filtergraph_value()`.

    Args:
        card_text_files: Ordered list of (text_file_path, start_s) pairs,
            one per track. Each text file must already exist and contain
            that track's display title as raw UTF-8 text.
        font_path: Path to a .ttf/.ttc/.otf font file to render with (see
            `soundweave.stages.video.resolve_track_card_font()` to resolve
            one).
        card_duration_s: Total on-screen window per card, in seconds.
        fade_s: Fade-in and fade-out duration within that window, in
            seconds.

    Returns:
        A comma-joined sequence of ``drawtext=...`` filter clauses (no
        leading/trailing comma), one per track, in the same order as
        `card_text_files`.

    Raises:
        ValueError: If `card_text_files` is empty, `card_duration_s`/`fade_s`
            aren't positive, or `fade_s` * 2 exceeds `card_duration_s`
            (the fades would overlap).
    """
    if not card_text_files:
        raise ValueError("Cannot build track-card filters with zero tracks")
    if card_duration_s <= 0 or fade_s <= 0:
        raise ValueError("card_duration_s and fade_s must both be positive")
    if fade_s * 2 > card_duration_s:
        raise ValueError(
            f"fade_s ({fade_s}) * 2 must not exceed card_duration_s "
            f"({card_duration_s}) -- the fade-in and fade-out would overlap"
        )

    font_value = escape_filtergraph_value(str(font_path))

    clauses = []
    for text_file, start_s in card_text_files:
        end_s = start_s + card_duration_s
        fade_in_end = start_s + fade_s
        fade_out_start = end_s - fade_s

        # Piecewise linear ramp: 0 -> 1 over the first fade_s seconds,
        # held at 1 through the middle, 1 -> 0 over the last fade_s
        # seconds. Only valid/evaluated while `enable` has this filter
        # active (t in [start_s, end_s]), so no branch is needed for
        # "before start" / "after end".
        alpha_expr = (
            f"if(lt(t,{fade_in_end:.3f}),(t-{start_s:.3f})/{fade_s:.3f},"
            f"if(lt(t,{fade_out_start:.3f}),1,({end_s:.3f}-t)/{fade_s:.3f}))"
        )

        text_value = escape_filtergraph_value(str(text_file))
        alpha_value = escape_filtergraph_value(alpha_expr)
        enable_value = escape_filtergraph_value(
            f"between(t,{start_s:.3f},{end_s:.3f})"
        )

        clauses.append(
            "drawtext="
            f"textfile={text_value}:"
            "expansion=none:"
            f"fontfile={font_value}:"
            "fontsize=54:"
            "fontcolor=white:"
            "box=1:"
            "boxcolor=black@0.5:"
            "boxborderw=20:"
            "x=(w-text_w)/2:"
            "y=h-th-100:"
            f"alpha={alpha_value}:"
            f"enable={enable_value}"
        )

    return ",".join(clauses)


def build_video_sequence_command(
    audio_path: Path,
    image_sequence: list[tuple[Path, float]],
    output_path: Path,
    track_cards_filter: str | None = None,
) -> list[str]:
    """Build FFmpeg command for rendering a per-track image-swap video.

    Companion to `build_video_command()` for the mashup "per-track images"
    mode (PRD.md §7): rather than one static image for the whole runtime,
    each image in `image_sequence` is shown for its own duration, in order,
    then hard-cut to the next. Total video duration is the sum of the
    per-image durations, matched against the audio track.

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        image_sequence: Ordered list of (image_path, duration_s) pairs, one
            per track. Must be non-empty.
        output_path: Path for output MP4
        track_cards_filter: Optional pre-built filter fragment from
            `build_track_card_drawtext_filters()` (T1, "now playing"
            track-title cards). When given, it's layered onto the
            concatenated video as an additional stage (``[outv]{filter}
            [outv_cards]``) rather than forking a separate command
            builder, so the existing scale/pad/concat logic here is
            reused unchanged. When omitted (default), output is byte-for-
            byte identical to before this parameter existed.

    Returns:
        FFmpeg command as list of arguments

    Raises:
        ValueError: If image_sequence is empty

    FFmpeg approach:
        - Each image is its own looped input, trimmed to its own duration
          via per-input `-t` (so ffmpeg only ever decodes/holds exactly as
          many frames as needed, rather than trimming after the fact)
        - Each image input is scaled/padded/letterboxed to 1920x1080 and
          normalized to 1fps, then concatenated (hard cut, no crossfade)
          via the `concat` filter
        - If track_cards_filter is given, it's applied to the concatenated
          video before mapping to output
        - Audio is the final input, mapped straight through untouched
        - Output: H.264 (yuv420p, high profile), AAC audio (192kbps)
    """
    if not image_sequence:
        raise ValueError("Cannot build video sequence command with zero images")

    cmd = ["ffmpeg"]

    # One looped, duration-trimmed input per image
    for image_path, duration_s in image_sequence:
        cmd.extend(["-loop", "1", "-t", str(duration_s), "-i", str(image_path)])

    # Audio is the last input
    audio_input_index = len(image_sequence)
    cmd.extend(["-i", str(audio_path)])

    # Per-image scale/pad/fps normalization, then concat
    filter_parts = []
    concat_labels = []
    for i in range(len(image_sequence)):
        filter_parts.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=1[v{i}]"
        )
        concat_labels.append(f"[v{i}]")

    filter_parts.append(
        "".join(concat_labels) + f"concat=n={len(image_sequence)}:v=1:a=0[outv]"
    )

    final_video_label = "outv"
    if track_cards_filter:
        filter_parts.append(f"[outv]{track_cards_filter}[outv_cards]")
        final_video_label = "outv_cards"

    filter_complex = ";".join(filter_parts)

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend([
        "-map", f"[{final_video_label}]",  # Concatenated (+ optional track-cards) video
        "-map", f"{audio_input_index}:a",  # Audio passthrough
        "-c:v", "libx264",               # H.264 codec
        "-preset", "medium",             # Encoding preset
        "-crf", "18",                    # Quality (lower = better, 18 is visually lossless)
        "-pix_fmt", "yuv420p",           # Pixel format for compatibility
        "-profile:v", "high",            # H.264 profile
        "-c:a", "aac",                   # AAC audio codec
        "-b:a", "192k",                  # Audio bitrate
        "-shortest",                     # Stop when shortest input ends
        "-y",                            # Overwrite output
        str(output_path)
    ])

    return cmd


def build_video_command(
    audio_path: Path,
    cover_image: Path,
    output_path: Path,
    duration_s: float,
    track_cards_filter: str | None = None,
) -> list[str]:
    """Build FFmpeg command for rendering static video.

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        cover_image: Path to cover image
        output_path: Path for output MP4
        duration_s: Audio duration in seconds
        track_cards_filter: Optional pre-built filter fragment from
            `build_track_card_drawtext_filters()` (T1, "now playing"
            track-title cards). When given, it's appended onto the
            existing scale/pad ``-vf`` chain (``,{filter}``) rather than
            forking a separate command builder. When omitted (default),
            output is byte-for-byte identical to before this parameter
            existed.

    Returns:
        FFmpeg command as list of arguments

    Output format:
        - 1920x1080 (scale/pad, preserve aspect ratio)
        - 1fps (static image) -- note: at 1fps, a drawtext alpha fade is
          sampled only once per second, so a ~1s fade-in/out reads as a
          coarse 1-2 step brightness change rather than a smooth
          dissolve. That's an inherent consequence of this mode's
          existing (deliberate, file-size-motivated) 1fps design, not
          something this parameter changes.
        - H.264 (yuv420p, high profile)
        - AAC audio (192kbps)
    """
    video_filter = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
    )
    if track_cards_filter:
        video_filter += "," + track_cards_filter

    return [
        "ffmpeg",
        "-loop", "1",                    # Loop image
        "-i", str(cover_image),
        "-i", str(audio_path),
        "-c:v", "libx264",               # H.264 codec
        "-preset", "medium",             # Encoding preset
        "-tune", "stillimage",           # Optimize for static image
        "-crf", "18",                    # Quality (lower = better, 18 is visually lossless)
        "-pix_fmt", "yuv420p",           # Pixel format for compatibility
        "-profile:v", "high",            # H.264 profile
        "-r", "1",                       # 1 frame per second
        "-vf", video_filter,             # Video filter for scaling/padding (+ optional track cards)
        "-c:a", "aac",                   # AAC audio codec
        "-b:a", "192k",                  # Audio bitrate
        "-shortest",                     # Stop when shortest input ends
        "-t", str(duration_s),           # Explicit duration
        "-y",                            # Overwrite output
        str(output_path)
    ]
