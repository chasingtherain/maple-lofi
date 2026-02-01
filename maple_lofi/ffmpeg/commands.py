"""FFmpeg command builders for each pipeline stage."""

from pathlib import Path

from maple_lofi.config import PipelineConfig
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
        return [
            "ffmpeg",
            "-i", str(tracks[0].path),
            "-af", "loudnorm=I=-20:TP=-1.5:LRA=11",  # Normalize loudness
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


def build_lofi_command(
    input_audio: Path,
    output_wav: Path,
    output_mp3: Path,
    config: PipelineConfig
) -> tuple[list[str], list[str]]:
    """Build FFmpeg commands for lofi processing.

    Args:
        input_audio: Path to merged_clean.wav
        output_wav: Path for merged_lofi.wav
        output_mp3: Path for merged_lofi.mp3
        config: Pipeline configuration

    Returns:
        Tuple of (wav_command, mp3_command)

    Processing chain (production-grade, taste-driven):
        1. Optional: Loop and mix texture at texture_gain_db
        2. Optional: Loop and mix drums (delayed) at drums_gain_db
        3. Optional: Tempo slowdown (0.75x by default for café vibe, pitch preserved)
        4. Gentle EQ: Highpass @ highpass_hz, Lowpass @ lowpass_hz
        5. Optional: Reverb (café ambience, ON by default)
        6. Optional: Subtle saturation (warmth, not distortion)
        7. Optional: Light compression (slow, transparent)
        8. Limiter @ -1dB (safety only, should rarely trigger)

    Philosophy: Restraint > layers. Default (reverb + tempo) creates café vibe.
    """
    # Build complex filter chain
    filter_parts = []
    input_labels = ["0:a"]  # Start with main audio

    # Input counter for additional files
    input_idx = 1

    # Add texture if specified
    if config.texture:
        # Loop texture to match main audio duration
        # aloop filter: loop=-1 means infinite loop, size=samples
        filter_parts.append(f"[{input_idx}:a]aloop=loop=-1:size=2e+09[texture]")
        input_labels.append("texture")
        input_idx += 1

    # Add drums if specified
    if config.drums:
        # Loop drums and delay start
        if config.drums_start_s > 0:
            filter_parts.append(
                f"[{input_idx}:a]aloop=loop=-1:size=2e+09,adelay={int(config.drums_start_s * 1000)}|{int(config.drums_start_s * 1000)}[drums]"
            )
        else:
            filter_parts.append(f"[{input_idx}:a]aloop=loop=-1:size=2e+09[drums]")
        input_labels.append("drums")
        input_idx += 1

    # Mix all inputs if we have texture/drums
    if len(input_labels) > 1:
        # Apply volume to texture/drums
        mix_inputs = ["[0:a]"]  # Main audio at unity gain

        if "texture" in input_labels:
            filter_parts.append(f"[texture]volume={config.texture_gain_db}dB[texture_vol]")
            mix_inputs.append("[texture_vol]")

        if "drums" in input_labels:
            filter_parts.append(f"[drums]volume={config.drums_gain_db}dB[drums_vol]")
            mix_inputs.append("[drums_vol]")

        # Mix all streams
        filter_parts.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0[mixed]")
        current_stream = "[mixed]"
    else:
        current_stream = "[0:a]"

    # Apply tempo change (slow down for café vibe)
    # atempo preserves pitch while changing speed
    # Limitation: each atempo can only do 0.5x-2.0x, chain multiple if needed
    if config.tempo_factor != 1.0:
        tempo = config.tempo_factor
        # Build atempo filter chain (each filter can only do 0.5x-2.0x)
        while tempo < 0.5:
            filter_parts.append(f"{current_stream}atempo=0.5[tempo_intermediate]")
            current_stream = "[tempo_intermediate]"
            tempo /= 0.5
        while tempo > 2.0:
            filter_parts.append(f"{current_stream}atempo=2.0[tempo_intermediate]")
            current_stream = "[tempo_intermediate]"
            tempo /= 2.0
        if tempo != 1.0:
            filter_parts.append(f"{current_stream}atempo={tempo:.3f}[tempo]")
            current_stream = "[tempo]"

    # Apply EQ (highpass → lowpass)
    filter_parts.append(f"{current_stream}highpass=f={config.highpass_hz}[hp]")
    filter_parts.append(f"[hp]lowpass=f={config.lowpass_hz}[lp]")

    current_stream = "[lp]"

    # Apply reverb (café ambience - subtle room sound)
    if config.enable_reverb:
        # aecho creates subtle reverb/room ambience
        # in_gain=0.8, out_gain=0.88: mostly original signal
        # delays=60|120, decays=0.3|0.25: short room reflections
        filter_parts.append(
            f"{current_stream}aecho=in_gain=0.8:out_gain=0.88:delays=60|120:decays=0.3|0.25[reverb]"
        )
        current_stream = "[reverb]"

    # Apply saturation (optional - adds warmth)
    if config.enable_saturation:
        # Use asubboost for harmonic warmth in low-mids
        # dry=0.5, wet=0.5 means 50/50 mix (more obvious for testing)
        # Adjust dry/wet ratio based on taste after testing
        filter_parts.append(
            f"{current_stream}asubboost=dry=0.5:wet=0.5:boost=3:decay=0.6:feedback=0.6:cutoff=150[sat]"
        )
        current_stream = "[sat]"

    # Apply compression (optional - gentle, transparent)
    if config.enable_compression:
        # Slow attack/release preserves transients and avoids pumping
        filter_parts.append(
            f"{current_stream}acompressor="
            f"ratio={config.comp_ratio}:"
            f"threshold={config.comp_threshold_db}dB:"
            f"attack={config.comp_attack_ms}:"
            f"release={config.comp_release_ms}[comp]"
        )
        current_stream = "[comp]"

    # Apply limiter (always on - safety only, should rarely trigger)
    filter_parts.append(f"{current_stream}alimiter=limit=-1dB:attack=5:release=50[out]")

    filter_complex = ";".join(filter_parts)

    # Build WAV command
    wav_cmd = ["ffmpeg", "-i", str(input_audio)]

    # Add texture/drums inputs if specified
    if config.texture:
        wav_cmd.extend(["-i", str(config.texture)])
    if config.drums:
        wav_cmd.extend(["-i", str(config.drums)])

    wav_cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", "48000",
        "-ac", "2",
        "-sample_fmt", "s16",
        "-y",
        str(output_wav)
    ])

    # Build MP3 command (from WAV output)
    mp3_cmd = [
        "ffmpeg",
        "-i", str(output_wav),
        "-codec:a", "libmp3lame",
        "-b:a", "320k",          # 320kbps CBR
        "-y",
        str(output_mp3)
    ]

    return wav_cmd, mp3_cmd


def build_video_command(
    audio_path: Path,
    cover_image: Path,
    output_path: Path,
    duration_s: float
) -> list[str]:
    """Build FFmpeg command for rendering static video.

    Args:
        audio_path: Path to final audio (merged_lofi.wav or merged_lofi.mp3)
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
