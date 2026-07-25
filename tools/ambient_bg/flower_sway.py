#!/usr/bin/env python3
"""Step 1.5 of the ambient background pipeline (optional): make flowers sway.

Independent of particles.py - operates on output/base.mp4 (DepthFlow's
parallax render) and rewrites it in place by default, before particles.py's
overlay is composited on top in composite.sh.

Why this needs its own approach, not DepthFlow or particles.py:
DepthFlow's parallax moves the *whole scene* based on depth (camera
simulation); particles.py adds independent floating dust unrelated to
anything in the painting. Making just the flowers sway means isolating
them from a single flat image with no separate layers.

Technique: build a color mask (HSV thresholds, calibrated against this
image's actual flower/grass/sky/cloud pixel values - see the constants
below) *fresh from every frame*, not tracked/computed once. This sidesteps
having to replicate DepthFlow's per-frame crop/zoom/pan math to keep a
mask aligned as the parallax camera moves things around: since the mask is
color-based and recomputed per frame, it automatically finds wherever the
flowers currently are in that frame's own pixels.

Displacement is a spatially-varying horizontal sine wave (amplitude *
sin(2*pi*t/period + x/wavelength)), applied only within the (softened)
flower mask via scipy.ndimage.map_coordinates. The x-dependent phase term
means neighboring flower clusters sway slightly out of phase with each
other - reads as wind moving across a field, not the whole mask lockstepping.

Usage:
    .venv/bin/python flower_sway.py
    .venv/bin/python flower_sway.py --amplitude 10 --wavelength 200
    .venv/bin/python flower_sway.py --input output/base.mp4 --output output/base_swayed.mp4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_opening, find_objects, gaussian_filter, label, map_coordinates

# This painting uses small bright sparkle/highlight dots on rocks, grass, and
# bush foliage for a glossy look - those share flowers' low-saturation/
# high-value signature and pass the HSV thresholds too. Real false positive
# hit during calibration (see the mask-overlay images from that session).
# Fix: flowers render as small, compact, roughly-round connected components;
# the highlight false positives are mostly larger/streakier. A max-area
# filter on connected components cleans this up without needing real
# segmentation - not perfect (a couple of small rock-highlight specks still
# slip through) but good enough for a subtle sway effect.
MAX_COMPONENT_AREA = 180

THIS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = THIS_DIR / "output"

# Calibrated against actual pixel samples from this project's scene image
# (real_assets/c3387f31601b9a2f95b61bf63496f8ab.jpg, rendered frame) - see
# the commit message for the sampled RGB/HSV values. Do not assume these
# generalize to a different source image without resampling.
YELLOW_HUE = (0.11, 0.19)      # ~40-68 degrees
YELLOW_SAT_MIN = 0.35
YELLOW_VAL_MIN = 0.85
WHITE_SAT_MAX = 0.22
WHITE_VAL_MIN = 0.85
WHITE_HUE = (0.16, 0.40)       # ~58-144 degrees. Excludes blue sky/clouds (~200deg,
                                # share white flowers' low-sat/high-val signature) AND
                                # the sandy dirt path (~48-53deg, also low-sat/high-val -
                                # a real false positive hit during calibration, narrowed
                                # the lower bound from 40 to 58 to exclude it specifically)


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Vectorized RGB[0,255] uint8 -> HSV[0,1] float32, no extra dependency."""
    arr = rgb.astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    delta = maxc - minc
    s = np.where(maxc > 1e-6, delta / np.maximum(maxc, 1e-6), 0.0)

    rc = np.where(delta > 1e-6, (maxc - r) / np.maximum(delta, 1e-6), 0.0)
    gc = np.where(delta > 1e-6, (maxc - g) / np.maximum(delta, 1e-6), 0.0)
    bc = np.where(delta > 1e-6, (maxc - b) / np.maximum(delta, 1e-6), 0.0)

    h = np.zeros_like(v)
    h = np.where(maxc == r, bc - gc, h)
    h = np.where(maxc == g, 2.0 + rc - bc, h)
    h = np.where(maxc == b, 4.0 + gc - rc, h)
    h = (h / 6.0) % 1.0
    h = np.where(delta <= 1e-6, 0.0, h)

    return np.stack([h, s, v], axis=-1)


def build_flower_mask(frame: np.ndarray, min_y_frac: float) -> np.ndarray:
    """Returns a soft [0,1] float32 mask, same H x W as frame."""
    h_img, w_img = frame.shape[:2]
    hsv = rgb_to_hsv(frame)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    yellow = (
        (hue >= YELLOW_HUE[0]) & (hue <= YELLOW_HUE[1])
        & (sat >= YELLOW_SAT_MIN) & (val >= YELLOW_VAL_MIN)
    )
    white = (
        (sat <= WHITE_SAT_MAX) & (val >= WHITE_VAL_MIN)
        & (hue >= WHITE_HUE[0]) & (hue <= WHITE_HUE[1])
    )

    # Flowers only ever appear in the lower part of this scene (grass) -
    # a cheap, robust safety net against any stray sky/cloud/rock false
    # positive regardless of color thresholds.
    y_grid = np.arange(h_img).reshape(-1, 1)
    lower_region = y_grid >= (h_img * min_y_frac)

    mask = (yellow | white) & lower_region

    # Clean up single-pixel noise first.
    mask_clean = binary_opening(mask, structure=np.ones((2, 2)))

    # Drop connected components larger than a real flower blob (rock/grass/
    # bush highlight sparkles - see MAX_COMPONENT_AREA's comment).
    labeled, _ = label(mask_clean)
    size_filtered = np.zeros_like(mask_clean)
    for i, sl in enumerate(find_objects(labeled), start=1):
        if sl is None:
            continue
        component = labeled[sl] == i
        if component.sum() <= MAX_COMPONENT_AREA:
            size_filtered[sl][component] = True

    # Soften edges so the sway blends rather than looking like a hard
    # cutout pasted on top.
    soft = gaussian_filter(size_filtered.astype(np.float32), sigma=1.5)
    return np.clip(soft, 0.0, 1.0)


def sway_frame(frame: np.ndarray, mask: np.ndarray, t: float, amplitude: float, wavelength: float, period: float) -> np.ndarray:
    """Horizontally displace flower pixels by a spatially-varying sine wave.

    Real bug hit and fixed here: gating displacement by the mask value at
    the *destination* pixel (dx = amplitude*sin(phase)*mask[y,x]) only lets
    a flower's original footprint change color in place - it can never
    appear to relocate, because nothing ever paints flower-colored pixels
    at the new position outside that original footprint. Increasing
    amplitude barely helped (3133 -> 5493 -> 6365 changed pixels for
    8 -> 20 -> 30px, sublinear) because the effect was bounded by the
    mask's own small size, not actually moving anything.

    Fix: compute the candidate source position for every destination pixel
    first (pure spatial sine wave, no mask gating), then look up the mask's
    value *at that source position* - i.e. "would this pixel have been
    flower-colored back where it's being pulled from?" This correctly
    paints flower color into the new position AND clears the old one
    (since the old position's own new source-after-shift no longer points
    back to itself), which is what actually reads as motion.
    """
    h_img, w_img = frame.shape[:2]
    yy, xx = np.mgrid[0:h_img, 0:w_img].astype(np.float32)

    phase = 2.0 * np.pi * (t / period) + xx / wavelength
    dx = amplitude * np.sin(phase)  # pure spatial wave, NOT gated by mask here

    src_x = np.clip(xx - dx, 0, w_img - 1)
    coords = np.stack([yy, src_x])

    # Weight by the mask *at the source* (where we're pulling color from),
    # not at the destination - this is what makes the flower actually
    # appear to move rather than just churn in place.
    mask = map_coordinates(mask, coords, order=1, mode="nearest")

    warped = np.empty_like(frame)
    for c in range(3):
        warped[..., c] = map_coordinates(frame[..., c], coords, order=1, mode="nearest")

    out = frame.astype(np.float32) * (1.0 - mask[..., None]) + warped.astype(np.float32) * mask[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def process(args: argparse.Namespace) -> Path:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,duration",
         "-of", "csv=p=0", str(args.input)],
        capture_output=True, text=True, check=True,
    )
    w_str, h_str, fps_str, dur_str = probe.stdout.strip().split(",")
    width, height = int(w_str), int(h_str)
    num, den = fps_str.split("/")
    fps = float(num) / float(den)
    duration = float(dur_str)
    total_frames = int(round(duration * fps))
    print(f"Input: {args.input} ({width}x{height} @ {fps:.2f}fps, {duration:.2f}s, {total_frames} frames)")

    # Integer number of sway cycles over the loop duration -> phase at t=0
    # matches phase at t=duration exactly, so this stays seamless with the
    # rest of the pipeline's loop.
    period = duration / args.cycles
    print(f"Sway: amplitude={args.amplitude}px wavelength={args.wavelength}px "
          f"period={period:.2f}s ({args.cycles} cycles/loop)")

    # Write to a temp path and rename into place at the end, even when
    # --output is the same path as --input (the default: overwrite base.mp4
    # in place). Reading and writing the same file concurrently through two
    # separate ffmpeg processes corrupts the read stream mid-flight once the
    # writer truncates it - hit this for real on the first run (decode
    # errors after 53/600 frames). A temp file sidesteps it entirely.
    tmp_output = args.output.with_name(args.output.stem + ".sway_tmp" + args.output.suffix)

    read_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(args.input), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    write_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{width}x{height}", "-framerate", f"{fps}",
        "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        str(tmp_output),
    ]

    reader = subprocess.Popen(read_cmd, stdout=subprocess.PIPE)
    writer = subprocess.Popen(write_cmd, stdin=subprocess.PIPE)
    assert reader.stdout is not None and writer.stdin is not None

    frame_bytes = width * height * 3
    t0 = time.time()
    frame_idx = 0
    mask_cache_interval = args.mask_every  # recompute mask every N frames, reuse between (perf)
    cached_mask = None
    try:
        while True:
            buf = reader.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3).copy()

            if cached_mask is None or frame_idx % mask_cache_interval == 0:
                cached_mask = build_flower_mask(frame, args.min_y_frac)

            t = frame_idx / fps
            out_frame = sway_frame(frame, cached_mask, t, args.amplitude, args.wavelength, period)
            writer.stdin.write(out_frame.tobytes())

            if frame_idx % 60 == 0:
                print(f"  frame {frame_idx}/{total_frames}", flush=True)
            frame_idx += 1
    finally:
        reader.stdout.close()
        writer.stdin.close()
        reader.wait()
        ret = writer.wait()

    elapsed = time.time() - t0
    if ret != 0:
        tmp_output.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg writer exited with code {ret}")
    if frame_idx != total_frames:
        tmp_output.unlink(missing_ok=True)
        raise RuntimeError(
            f"Only processed {frame_idx}/{total_frames} frames - input read ended early "
            "(this is the failure mode of reading/writing the same file concurrently; "
            "should not happen now that output goes through a temp file first, but "
            "checked explicitly rather than silently shipping a truncated result)"
        )
    print(f"Processed {frame_idx} frames in {elapsed:.2f}s ({frame_idx / elapsed:.1f} fps)")

    tmp_output.replace(args.output)
    print(f"Output: {args.output}")
    return args.output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "base.mp4",
                         help="Input video (default: output/base.mp4, i.e. depth_render.py's output).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "base.mp4",
                         help="Output video (default: overwrite base.mp4 in place, so composite.sh "
                              "picks it up unchanged - run this AFTER depth_render.py and BEFORE "
                              "composite.sh in the pipeline).")
    parser.add_argument("--amplitude", type=float, default=25.0,
                         help="Max horizontal sway in pixels (default: 25.0, raised from an initial 8.0 - "
                              "these flower blobs are small/soft in this painting, and every other "
                              "gentle-by-default effect in this pipeline needed a much stronger push "
                              "than expected to actually read as visible motion, not just a first guess).")
    parser.add_argument("--wavelength", type=float, default=150.0,
                         help="Pixel distance over which sway phase varies (default: 150 - smaller "
                              "= more independent-looking clusters, larger = more uniform field sway).")
    parser.add_argument("--cycles", type=int, default=3,
                         help="Integer number of full sway cycles over the loop duration (default: 3 - "
                              "must be an integer for the loop to stay seamless).")
    parser.add_argument("--min-y-frac", type=float, default=0.5,
                         help="Only consider flowers below this fraction of frame height (default: 0.5 - "
                              "this scene's grass/flowers are in the lower half; a safety net against "
                              "sky/cloud false positives regardless of color thresholds).")
    parser.add_argument("--mask-every", type=int, default=1,
                         help="Recompute the flower mask every N frames, reuse in between (default: 1 = "
                              "every frame, most correct since it tracks parallax motion for free; "
                              "raise for faster but slightly-stale-mask renders).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"FAIL: input not found: {args.input} (run depth_render.py first)", file=sys.stderr)
        return 1
    process(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
