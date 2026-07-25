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


def build_video_sequence_command(
    audio_path: Path,
    image_sequence: list[tuple[Path, float]],
    output_path: Path,
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
    filter_complex = ";".join(filter_parts)

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend([
        "-map", "[outv]",                # Concatenated video
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


def build_animated_background_command(
    audio_path: Path,
    background_video: Path,
    output_path: Path,
    duration_s: float,
) -> list[str]:
    """Build FFmpeg command for pairing audio with a looping animated background.

    Companion to `build_video_command()`: instead of one static image held
    for the whole runtime, a short pre-rendered looping video (e.g.
    `tools/ambient_bg/`'s `final.mp4` — a seamless ~20s parallax/particle
    loop) is repeated via `-stream_loop -1` to cover the full audio
    duration, then re-encoded and trimmed to an exact length.
    `background_video` is expected to already be roughly YouTube-ready, but
    is still scaled/padded to 1920x1080 (same filter as
    `build_video_command()`'s static-image path) rather than trusted as-is —
    an odd width/height (not evenly divisible by 2) would otherwise fail the
    `yuv420p` encode only after the full audio pipeline has already run.

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        background_video: Path to the short looping background video
        output_path: Path for output MP4
        duration_s: Audio duration in seconds

    Returns:
        FFmpeg command as list of arguments

    Output format:
        - 1920x1080 (scale/pad, preserve aspect ratio — same as build_video_command)
        - H.264 (yuv420p, high profile) — re-encoded (not stream-copied) so
          the `-t` trim lands on an exact frame rather than the nearest
          keyframe in the looped source
        - AAC audio (192kbps)
        - Duration matches audio exactly
    """
    return [
        "ffmpeg",
        "-stream_loop", "-1",            # Loop background video indefinitely
        "-i", str(background_video),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", (                         # Guard against non-1920x1080/odd-dimension input
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-c:v", "libx264",               # H.264 codec
        "-preset", "medium",             # Encoding preset
        "-crf", "18",                    # Quality (lower = better, 18 is visually lossless)
        "-pix_fmt", "yuv420p",           # Pixel format for compatibility
        "-profile:v", "high",            # H.264 profile
        "-c:a", "aac",                   # AAC audio codec
        "-b:a", "192k",                  # Audio bitrate
        "-t", str(duration_s),           # Explicit duration (video is infinitely looped, so
                                          # this alone bounds output length -- -shortest would
                                          # be redundant)
        "-movflags", "+faststart",       # YouTube-ready fast start
        "-y",                            # Overwrite output
        str(output_path)
    ]


def build_video_command(
    audio_path: Path,
    cover_image: Path,
    output_path: Path,
    duration_s: float
) -> list[str]:
    """Build FFmpeg command for rendering static video.

    Args:
        audio_path: Path to final audio (merged.wav or merged.mp3)
        cover_image: Path to cover image
        output_path: Path for output MP4
        duration_s: Audio duration in seconds

    Returns:
        FFmpeg command as list of arguments

    Output format:
        - 1920x1080 (scale/pad, preserve aspect ratio)
        - 1fps (static image)
        - H.264 (yuv420p, high profile)
        - AAC audio (192kbps)
    """
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
        "-vf", (                         # Video filter for scaling/padding
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-c:a", "aac",                   # AAC audio codec
        "-b:a", "192k",                  # Audio bitrate
        "-shortest",                     # Stop when shortest input ends
        "-t", str(duration_s),           # Explicit duration
        "-y",                            # Overwrite output
        str(output_path)
    ]
