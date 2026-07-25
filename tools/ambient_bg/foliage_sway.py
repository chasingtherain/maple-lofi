#!/usr/bin/env python3
"""Step 1.6 of the ambient background pipeline (optional): make bushes/trees sway.

Sibling to flower_sway.py, deliberately NOT built on top of it - a genuinely
different technique, not a parameter tweak. Why flower_sway.py's approach
doesn't generalize to bushes/trees:

1. Wrong motion model. flower_sway.py displaces every masked pixel by the
   SAME dx (a uniform horizontal shift, only modulated by a spatial phase
   term across x). That reads fine for a small flower head, but a whole
   bush/tree shifting rigidly sideways as one piece looks like a cardboard
   cutout sliding - obviously fake at this size. Real wind-sway is a bend
   anchored at the base: trunk/root barely moves, canopy moves more, and
   displacement increases with height above the ground. This script computes
   a *per-component height gradient* instead of a uniform shift: for each
   connected bush/tree blob, displacement is 0 at the blob's own bottom
   (anchor) and grows toward the blob's own top (canopy).

2. Weaker color segmentation. Flowers popped against flat grass with real
   contrast. Bushes/trees here are dark-to-medium saturated green *on top of
   grass that is also green* - see build_foliage_mask()'s docstring for the
   calibration story and its known false-positive: shadowed grass at a
   bush's base is colorimetrically almost identical to the bush itself, so
   it sometimes survives thresholding as part of the same connected
   component. The per-component anchor happens to make this mostly benign
   (that grass tends to sit near the component's bottom, i.e. near-zero
   grad, so it barely moves even when swept in) but it is a known,
   documented imperfection, not something claimed to be solved.

Compositing bug avoided (build this in from the start, not discovered the
hard way - see this repo's parallel flower_sway.py fix for the same class of
bug): a backward warp that blends `out = frame*(1-w) + warped*w` using raw
`frame` as the "unmoved" background is wrong even when `w` is correctly
sampled at the *source* position, because `frame` still has the original
foliage baked in at its original spot - nothing ever clears it, so you get
foliage-color painted at the new position AND the untouched original left
behind (a duplicate). Fix used here: blend against a foliage-removed
background PLATE (a gaussian-blurred copy of the frame, substituted in
within a dilated foliage mask region) instead of the raw frame. See
build_background_plate() and sway_frame().

Usage:
    .venv/bin/python foliage_sway.py
    .venv/bin/python foliage_sway.py --amplitude 18 --cycles 2
    .venv/bin/python foliage_sway.py --input output/base.mp4 --output output/base.mp4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_opening,
    distance_transform_edt,
    find_objects,
    gaussian_filter,
    label,
    map_coordinates,
)

# Reuse flower_sway.py's vectorized RGB->HSV helper rather than reimplementing
# it (per task instructions: import or copy, don't reinvent). flower_sway.py
# itself is NOT modified by this file.
from flower_sway import rgb_to_hsv

THIS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = THIS_DIR / "output"

# --------------------------------------------------------------------------
# Segmentation constants, calibrated against real pixel samples from this
# project's scene image (real_assets/c3387f31601b9a2f95b61bf63496f8ab.jpg,
# rendered frame 0 of output/base.mp4 at 1920x1080). Do not assume these
# generalize to a different source image without resampling - see the
# sampled RGB/HSV values in the commit message for this file.
#
# Calibration story: bushes/trees in this painting are dark-to-medium
# saturated green (hue ~0.32-0.46, sat ~0.4-0.8, val ~0.33-0.87 depending on
# lighting/shading), sampled from both foreground bushes and background
# treeline. This band is WIDER and noisier than flowers ever needed, and it
# overlaps real false positives:
#   - Shadowed/mossy grass on the rock mound and at bush bases lands in
#     almost the exact same HSV band (sampled (66,110,38) HSV h=0.27 s=0.66
#     v=0.43 right next to a bush - indistinguishable from bush color by
#     hue/sat/val alone). This is the reason for leaning on spatial priors
#     (component area, height, and a y-range cutoff) rather than trying to
#     tighten the color thresholds further - tightening them further starts
#     cutting into legitimate darker tree/bush pixels instead.
#   - Bright grass/dirt-path patches are excluded by hue (grass runs
#     yellower, ~0.22-0.30) and are not a real problem here.
FOLIAGE_HUE = (0.30, 0.47)
FOLIAGE_SAT_MIN = 0.42
FOLIAGE_VAL_MIN = 0.30
FOLIAGE_VAL_MAX = 0.90

# Spatial priors used to separate real bush/tree blobs from color-alike
# noise (grass blade texture, moss flecks, stray highlight specks) after
# thresholding. All calibrated at 1920x1080 (composite.sh's render size).
MIN_COMPONENT_AREA = 400  # px^2 - drops single-blade/speck noise, keeps small leaf clusters
MIN_COMPONENT_HEIGHT = 12  # px - drops flat slivers (thin grass-blade streaks)
MIN_COMPONENT_FILL = 0.15  # area / bbox_area - drops sparse streaky shapes (moss cracks)
# Flowers live in the bottom of the frame (flower_sway.py's min_y_frac=0.5
# is a LOWER bound). Bushes/trees are the opposite: real ones start well
# above the bottom "flower zone" grass texture. A component whose bounding
# box starts (top edge) below this fraction of frame height is almost
# certainly grass-blade texture or a rock/mound false positive, not a real
# bush/tree - this single cutoff, verified against real component dumps
# during calibration, was what actually separated the two classes, not the
# color thresholds.
MAX_COMPONENT_Y0_FRAC = 0.70

# Interior "hole" closing radius (px) applied before the blend-weight mask
# is built - NOT applied to the components used for segmentation/anchor
# geometry. Real defect hit during single-frame verification: this
# painting's leaf-highlight sparkle dots (flower_sway.py's docstring notes
# the same dots as a flower-detection false positive - low-saturation,
# high-value, so they FAIL this file's foliage color mask same as they'd
# fail flower's) sit inside canopy interiors as small holes in hard_mask.
# Without closing, those holes carry a near-zero blend weight even though
# they're surrounded by foliage on all sides, so after warping the
# surrounding leaf color shifts but the highlight dot's own position
# doesn't get repainted - visible as a hollow ring/donut ghost where a
# solid bright dot should be (seen directly in a before/after crop zoom
# during verification). Closing fills those interior holes so the blend
# weight treats "small bright/dark detail inside a canopy" as part of the
# solid silhouette, moving with it as texture instead of leaving a hole.
BLEND_CLOSE_SIZE = 15

# How many pixels each component's influence extends sideways beyond its
# own true pixel footprint, so a bending canopy has room to visibly reach
# into adjacent sky/grass rather than only recoloring in place (the same
# class of bug flower_sway.py's docstring describes - gating displacement
# magnitude by a value that's only nonzero exactly at the true footprint
# means destination pixels just outside it never get pulled from). Set from
# --amplitude at runtime (must be >= amplitude for full range of motion to
# be reachable).
GRAD_MARGIN_MIN = 8


def build_foliage_mask(frame: np.ndarray):
    """Segment bush/tree canopy blobs.

    Returns (hard_mask, labeled, components) where hard_mask is a bool
    [H,W] array (union of all kept components), labeled is the (pre-filter)
    connected-component label array from scipy.ndimage.label (needed so
    build_gradient_field can look up exactly which pixels belong to which
    kept component by label_id), and components is a list of dicts, one per
    kept connected component, with its bounding box, per-component height,
    and label_id.
    """
    h_img, w_img = frame.shape[:2]
    hsv = rgb_to_hsv(frame)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    color_mask = (
        (hue >= FOLIAGE_HUE[0]) & (hue <= FOLIAGE_HUE[1])
        & (sat >= FOLIAGE_SAT_MIN)
        & (val >= FOLIAGE_VAL_MIN) & (val <= FOLIAGE_VAL_MAX)
    )

    # Clean up single-pixel noise. A small kernel only - bushes/trees are
    # noisier shapes than flowers and a heavier opening starts eating real
    # canopy detail (leaf-cluster gaps) without actually disconnecting the
    # shadow-grass false positive documented above (tried up to 9x9 during
    # calibration: it thinned real canopies before it broke that bridge,
    # since the bridge is a solid patch, not a thin filament).
    cleaned = binary_opening(color_mask, structure=np.ones((3, 3)))

    labeled, _ = label(cleaned)
    components = []
    hard_mask = np.zeros_like(cleaned)
    for i, sl in enumerate(find_objects(labeled), start=1):
        if sl is None:
            continue
        ys, xs = sl
        comp_bool = labeled[sl] == i
        area = int(comp_bool.sum())
        height_px = ys.stop - ys.start
        width_px = xs.stop - xs.start
        fill = area / max(height_px * width_px, 1)

        if area < MIN_COMPONENT_AREA:
            continue
        if height_px < MIN_COMPONENT_HEIGHT:
            continue
        if fill < MIN_COMPONENT_FILL:
            continue
        if ys.start >= h_img * MAX_COMPONENT_Y0_FRAC:
            continue

        hard_mask[sl][comp_bool] = True
        components.append({
            "label_id": i,
            "y0": ys.start, "y1": ys.stop,
            "x0": xs.start, "x1": xs.stop,
            "height": max(height_px, 1),
        })

    return hard_mask, labeled, components


def build_blend_mask(hard_mask: np.ndarray) -> np.ndarray:
    """Soft [0,1] blend-weight mask used in sway_frame(), distinct from the
    strict per-pixel color mask used for segmentation. Closes small interior
    holes first - see BLEND_CLOSE_SIZE's comment for the ring/donut artifact
    this fixes - then softens edges with the same blur sigma flower_sway.py
    uses, for the same reason (blend rather than hard-cutout).
    """
    closed = binary_closing(hard_mask, structure=np.ones((BLEND_CLOSE_SIZE, BLEND_CLOSE_SIZE)))
    return np.clip(gaussian_filter(closed.astype(np.float32), sigma=1.5), 0.0, 1.0)


def build_gradient_field(h_img: int, w_img: int, hard_mask: np.ndarray, labeled: np.ndarray, components: list, margin: int) -> np.ndarray:
    """Per-pixel bend factor in [0, 1]: 0 at each component's own base
    (bbox bottom, y1 - the anchor), 1 at its own top (y0), computed
    independently per component.

    Extending this past each component's true pixel footprint is what lets
    a bending canopy visibly reach into the space beside it instead of only
    recoloring within its original silhouette (see GRAD_MARGIN_MIN's
    comment - same class of bug as gating displacement at the destination).
    Earlier version of this function did that extension with dilated
    bounding-BOX rectangles combined via elementwise max, but that let two
    components close together (bbox margins overlapping in empty space
    between them) leak each other's gradient values well past their own
    true edges - caught by the anchor/top numeric check in this file's test
    harness returning ~0.71 instead of ~0.0 at a component's own anchor row,
    traced to a neighboring component's rectangle overlapping that exact
    point. Fixed by extending via nearest-TRUE-PIXEL distance instead of
    nearest-bounding-box: every background pixel inherits the grad value of
    its closest actual foliage pixel (not just closest bounding box),
    linearly faded to 0 over `margin` px.
    """
    grad_true = np.zeros((h_img, w_img), dtype=np.float32)
    yy_full = np.arange(h_img, dtype=np.float32).reshape(-1, 1)
    for comp in components:
        y0, y1, x0, x1 = comp["y0"], comp["y1"], comp["x0"], comp["x1"]
        height = comp["height"]
        sub = labeled[y0:y1, x0:x1] == comp["label_id"]
        col = np.clip((y1 - yy_full[y0:y1]) / height, 0.0, 1.0)  # [rows, 1]
        rect = np.broadcast_to(col, sub.shape)
        grad_true[y0:y1, x0:x1][sub] = rect[sub]

    if not hard_mask.any():
        return grad_true

    dist, indices = distance_transform_edt(~hard_mask, return_indices=True)
    nearest_grad = grad_true[indices[0], indices[1]]
    falloff = np.clip(1.0 - dist / margin, 0.0, 1.0)
    return np.where(hard_mask, grad_true, nearest_grad * falloff)


def build_background_plate(frame: np.ndarray, hard_mask: np.ndarray, blur_sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Foliage-removed backdrop: gaussian-blur the frame and substitute it
    in within a dilated+softened version of the foliage mask. Returns
    (plate, alpha) - alpha is the soft [0,1] blend weight used both here and
    as the compositing weight base in sway_frame().
    """
    dilated = binary_dilation(hard_mask, iterations=3)
    alpha = gaussian_filter(dilated.astype(np.float32), sigma=3.0)
    alpha = np.clip(alpha, 0.0, 1.0)

    blurred = gaussian_filter(frame.astype(np.float32), sigma=(blur_sigma, blur_sigma, 0))
    plate = frame.astype(np.float32) * (1.0 - alpha[..., None]) + blurred * alpha[..., None]
    return plate, alpha


def sway_frame(
    frame: np.ndarray,
    soft_mask: np.ndarray,
    grad_field: np.ndarray,
    background_plate: np.ndarray,
    t: float,
    amplitude: float,
    wavelength: float,
    period: float,
) -> np.ndarray:
    """Bend foliage sideways: dx grows with grad_field (0 at each
    component's base, max at its own canopy top), independent per component
    since grad_field was built per-component. Follows flower_sway.py's fix
    for the "gated at destination" bug: dx itself must NOT be gated by a
    field that is zero outside the true footprint (grad_field is deliberately
    extended past it via build_gradient_field's margin), and the blend
    weight must be sampled at the *source* position, not the destination,
    so foliage color actually relocates instead of just recoloring in place.

    On top of that fix, this also avoids the duplication bug: blending
    against `background_plate` (foliage removed) rather than the raw frame
    means the vacated original position is actually cleared, not left behind
    underneath the relocated color.
    """
    h_img, w_img = frame.shape[:2]
    yy, xx = np.mgrid[0:h_img, 0:w_img].astype(np.float32)

    phase = 2.0 * np.pi * (t / period) + xx / wavelength
    dx = amplitude * np.sin(phase) * grad_field  # pure per-pixel field, not gated at destination by mask

    src_x = np.clip(xx - dx, 0, w_img - 1)
    coords = np.stack([yy, src_x])

    # Weight sampled at the SOURCE position - "would this pixel have been
    # foliage-colored back where it's being pulled from?" Same fix as
    # flower_sway.py's sway_frame(), same reason.
    weight = map_coordinates(soft_mask, coords, order=1, mode="nearest")

    warped = np.empty_like(frame, dtype=np.float32)
    for c in range(3):
        warped[..., c] = map_coordinates(frame[..., c].astype(np.float32), coords, order=1, mode="nearest")

    out = background_plate * (1.0 - weight[..., None]) + warped * weight[..., None]
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

    period = duration / args.cycles
    margin = max(int(args.amplitude) + 5, GRAD_MARGIN_MIN)
    print(f"Sway: amplitude={args.amplitude}px wavelength={args.wavelength}px "
          f"period={period:.2f}s ({args.cycles} cycles/loop) grad_margin={margin}px")

    # Same temp-file/rename pattern as flower_sway.py, for the same reason:
    # reading and writing output/base.mp4 concurrently through two ffmpeg
    # processes corrupts the read stream mid-flight once the writer
    # truncates it.
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
    mask_cache_interval = args.mask_every
    cached = None  # (soft_mask, grad_field, background_plate)
    try:
        while True:
            buf = reader.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3).copy()

            if cached is None or frame_idx % mask_cache_interval == 0:
                hard_mask, labeled, components = build_foliage_mask(frame)
                soft_mask = build_blend_mask(hard_mask)
                grad_field = build_gradient_field(height, width, hard_mask, labeled, components, margin)
                background_plate, _ = build_background_plate(frame, hard_mask, args.blur_sigma)
                cached = (soft_mask, grad_field, background_plate)
            soft_mask, grad_field, background_plate = cached

            t = frame_idx / fps
            out_frame = sway_frame(frame, soft_mask, grad_field, background_plate, t, args.amplitude, args.wavelength, period)
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
                         help="Input video (default: output/base.mp4).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "base.mp4",
                         help="Output video (default: overwrite base.mp4 in place - run this AFTER "
                              "depth_render.py and flower_sway.py, and BEFORE composite.sh).")
    parser.add_argument("--amplitude", type=float, default=30.0,
                         help="Max horizontal sway in pixels at a component's own canopy top "
                              "(default: 30.0 - bushes/trees are much bigger on-screen than flowers, "
                              "so the same absolute pixel amplitude reads as proportionally weaker; "
                              "raised above flower_sway.py's 25px default for that reason).")
    parser.add_argument("--wavelength", type=float, default=250.0,
                         help="Pixel distance over which sway phase varies (default: 250 - larger than "
                              "flower_sway.py's 150 since bush/tree blobs are wider and further apart).")
    parser.add_argument("--cycles", type=int, default=3,
                         help="Integer number of full sway cycles over the loop duration (default: 3 - "
                              "must be an integer for the loop to stay seamless).")
    parser.add_argument("--blur-sigma", type=float, default=16.0,
                         help="Gaussian blur sigma (px) for the foliage-removed background plate "
                              "(default: 16, within the 12-20 range suggested for blur-fill).")
    parser.add_argument("--mask-every", type=int, default=1,
                         help="Recompute the foliage mask every N frames, reuse in between (default: 1 = "
                              "every frame, tracks parallax motion for free; raise for faster renders).")
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
