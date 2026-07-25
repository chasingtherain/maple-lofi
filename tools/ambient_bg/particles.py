#!/usr/bin/env python3
"""Step 2 of the ambient background pipeline: ambient particle overlay.

Independent of depth_render.py - can be built/tuned in parallel with it,
and re-run on its own without touching the parallax base video.

Soft, small floating particles (dust motes/pollen): slow upward drift,
gentle horizontal sway, varied size/opacity, low density. Pure NumPy/Pillow
rendering (both already installed as depthflow's own dependencies - no new
heavy dependency like OpenCV needed for something this simple).

Real technical constraint (flagged in TASK.md, handled here rather than
discovered mid-implementation): MP4/H.264 has no alpha channel. This script
exports a real alpha-channel video: raw RGBA frames piped to ffmpeg's qtrle
codec in a .mov container (`-pix_fmt argb`). qtrle is lossless and, being
designed for large flat runs of identical pixels, compresses a mostly-
transparent particle layer very efficiently. composite.sh then overlays
this .mov onto base.mp4 at reduced opacity.

Looping: each particle travels from below-frame to above-frame over its
own personal cycle, where that cycle is `loop_duration / k` for a random
integer k - so every particle's phase at t=duration exactly matches its
phase at t=0, guaranteeing the whole layer loops seamlessly. The vertical
travel range extends past the frame edges on both ends, so the instant
"teleport back to the bottom" happens while the particle is fully
off-screen and invisible.

Usage:
    .venv/bin/python particles.py
    .venv/bin/python particles.py --count 150 --duration 20 --fps 30
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = THIS_DIR / "output"


def make_gaussian_sprite(radius: float) -> np.ndarray:
    """A small soft white circular sprite, alpha channel only, float32 [0,1]."""
    size = max(3, int(round(radius * 4)))
    if size % 2 == 0:
        size += 1
    center = size / 2.0
    yy, xx = np.mgrid[0:size, 0:size]
    dist2 = (xx - center + 0.5) ** 2 + (yy - center + 0.5) ** 2
    sigma = max(radius * 0.5, 0.6)
    sprite = np.exp(-dist2 / (2.0 * sigma * sigma))
    return sprite.astype(np.float32)


class Particle:
    def __init__(self, rng: np.random.Generator, width: int, height: int, max_opacity: float):
        self.x0 = rng.uniform(0, width)
        # Sway amplitude in pixels - gentle, small relative to frame width.
        self.sway_amp = rng.uniform(8, 28)
        # Integer number of full sway oscillations per particle-cycle so
        # phase matches up at the loop boundary.
        self.sway_cycles = int(rng.integers(1, 3))
        self.sway_phase = rng.uniform(0, 2 * np.pi)

        # Vertical travel: bottom (off-screen) to top (off-screen).
        margin = height * 0.15
        self.y_bottom = height + margin
        self.y_top = -margin
        # Integer k => this particle completes k full bottom-to-top trips
        # within one loop duration. Slower (k=1) particles read as distant
        # dust, faster (k=2 or 3) as closer/lighter motes.
        self.k = int(rng.integers(1, 4))
        self.phase0 = rng.uniform(0, 1)

        self.radius = rng.uniform(1.5, 5.0)
        self.base_opacity = rng.uniform(0.25, 1.0) * max_opacity
        self.twinkle_cycles = int(rng.integers(1, 3))
        self.twinkle_phase = rng.uniform(0, 2 * np.pi)
        self.sprite = make_gaussian_sprite(self.radius)

    def state_at(self, tau: float):
        """tau: normalized time in [0, 1) across the whole loop duration."""
        phase = (tau * self.k + self.phase0) % 1.0
        y = self.y_bottom + phase * (self.y_top - self.y_bottom)
        sway = self.sway_amp * np.sin(2 * np.pi * (phase * self.sway_cycles) + self.sway_phase)
        x = self.x0 + sway
        twinkle = 0.7 + 0.3 * np.sin(2 * np.pi * (tau * self.twinkle_cycles) + self.twinkle_phase)
        opacity = self.base_opacity * twinkle
        return x, y, opacity


def splat(canvas: np.ndarray, x: float, y: float, opacity: float, sprite: np.ndarray) -> None:
    """Alpha-composite a white sprite onto an RGBA float32 canvas in place."""
    h, w = sprite.shape
    top = int(round(y - h / 2))
    left = int(round(x - w / 2))

    canvas_h, canvas_w = canvas.shape[0], canvas.shape[1]
    src_top = max(0, -top)
    src_left = max(0, -left)
    dst_top = max(0, top)
    dst_left = max(0, left)
    src_bottom = h - max(0, (top + h) - canvas_h)
    src_right = w - max(0, (left + w) - canvas_w)

    if src_bottom <= src_top or src_right <= src_left:
        return  # fully off-canvas

    region = canvas[dst_top:dst_top + (src_bottom - src_top), dst_left:dst_left + (src_right - src_left)]
    sprite_region = sprite[src_top:src_bottom, src_left:src_right] * opacity

    # Standard "over" alpha compositing, particle color is white/soft.
    src_a = sprite_region
    dst_a = region[..., 3]
    out_a = src_a + dst_a * (1.0 - src_a)
    with np.errstate(invalid="ignore", divide="ignore"):
        for c in range(3):
            region[..., c] = np.where(
                out_a > 1e-6,
                (255.0 * src_a + region[..., c] * dst_a * (1.0 - src_a)) / np.maximum(out_a, 1e-6),
                0.0,
            )
    region[..., 3] = out_a


def render_particles(args: argparse.Namespace) -> Path:
    rng = np.random.default_rng(args.seed)
    particles = [
        Particle(rng, args.width, args.height, args.max_opacity)
        for _ in range(args.count)
    ]

    total_frames = int(round(args.duration * args.fps))
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "particles.mov"

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgba",
        "-video_size", f"{args.width}x{args.height}",
        "-framerate", str(args.fps),
        "-i", "-",
        "-c:v", "qtrle", "-pix_fmt", "argb",
        str(output_path),
    ]
    print(f"Rendering {total_frames} frames of {args.count} particles at "
          f"{args.width}x{args.height}@{args.fps}fps -> {output_path}")
    print(f"ffmpeg command: {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    t0 = time.time()
    try:
        for frame_idx in range(total_frames):
            tau = frame_idx / total_frames
            canvas = np.zeros((args.height, args.width, 4), dtype=np.float32)
            for p in particles:
                x, y, opacity = p.state_at(tau)
                if opacity <= 0.001:
                    continue
                splat(canvas, x, y, opacity, p.sprite)
            # RGB channels are already scaled to [0, 255] by splat(); alpha
            # is accumulated in [0, 1] (straight "over" compositing math),
            # so it needs its own scale-up before the uint8 cast - doing
            # this uniformly with the RGB channels silently truncated every
            # alpha value to 0 (a real bug hit while verifying output).
            frame = canvas.copy()
            frame[..., 3] *= 255.0
            frame_bytes = np.clip(frame, 0, 255).astype(np.uint8).tobytes()
            proc.stdin.write(frame_bytes)
            if frame_idx % 60 == 0:
                print(f"  frame {frame_idx}/{total_frames}", flush=True)
    finally:
        proc.stdin.close()
        ret = proc.wait()

    elapsed = time.time() - t0
    if ret != 0:
        raise RuntimeError(f"ffmpeg exited with code {ret}")
    print(f"Rendered {total_frames} frames in {elapsed:.2f}s ({total_frames / elapsed:.1f} fps)")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--count", type=int, default=90, help="Number of particles (default: 90, low density).")
    parser.add_argument("--duration", type=float, default=20.0, help="Loop duration in seconds (must match depth_render.py's --duration to composite cleanly).")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--max-opacity", type=float, default=0.55,
                         help="Per-particle peak alpha (0-1). The overall layer is dimmed further "
                              "at composite time (~20-30%% per TASK.md) - this controls the "
                              "particles.mov layer's own internal contrast, not final on-screen strength.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = render_particles(args)
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
