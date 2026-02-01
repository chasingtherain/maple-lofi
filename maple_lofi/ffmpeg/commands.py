"""FFmpeg command builders for each pipeline stage."""

from pathlib import Path

from maple_lofi.stages.ingest import AudioTrack


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
            "-af", "loudnorm=I=-20:TP=-1.5:LRA=11",
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

    # Step 1: Normalize loudness for each input track
    for i in range(len(tracks)):
        filter_parts.append(
            f"[{i}:a]loudnorm=I=-20:TP=-1.5:LRA=11[norm{i}]"
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
