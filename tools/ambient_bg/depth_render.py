#!/usr/bin/env python3
"""Step 1 of the ambient background pipeline: depth-based 2.5D parallax render.

Independently re-runnable in two phases:

  1. Depth-map extraction (fast, always runs first) -> output/depth_map.png.
     Inspect this before committing to a full render - noisy/warped edges
     around foreground objects are the classic monocular-depth failure mode.
  2. Full parallax video render -> output/base.mp4 (skippable with
     --depth-map-only if you just want to check the depth map).

Uses DepthFlow's Python library API (subclassing DepthScene), not its CLI.
See setup_check.py's check_cli_vs_library() for why: animated drift/orbit
motion needs a per-frame update() hook that the CLI's `state` subcommand
doesn't expose (it only sets one static pose for the whole render).

Usage:
    .venv/bin/python depth_render.py --depth-map-only
    .venv/bin/python depth_render.py
    .venv/bin/python depth_render.py --preset circle --motion-intensity 0.15 --duration 15
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

# Must be set before torch is imported anywhere down the line (some
# depth-model ops aren't implemented on MPS yet and would otherwise hard
# error instead of falling back to CPU).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
DEFAULT_SCENE = REPO_ROOT / "real_assets" / "c3387f31601b9a2f95b61bf63496f8ab.jpg"
DEFAULT_OUTPUT_DIR = THIS_DIR / "output"


def build_motion(preset: str, intensity: float):
    """Returns a per-frame update(cycle) -> (isometric, offset) function.

    `intensity` is a fraction of DepthFlow's own example-preset amplitudes
    (see DepthFlow/examples/presets.py) - 1.0 would reproduce their
    full-strength motion, we default much lower since this sits behind an
    hour of music and should barely be noticed.
    """

    if preset == "orbit":
        def motion(cycle: float):
            isometric = intensity * (0.50 * math.cos(cycle) + 0.75)
            offset = (intensity * 0.50 * math.sin(cycle), 0.0)
            return isometric, offset
    elif preset == "circle":
        def motion(cycle: float):
            isometric = 0.60 * intensity
            offset = (
                intensity * 0.50 * math.sin(cycle + math.pi / 2.0),
                intensity * 0.50 * math.sin(cycle),
            )
            return isometric, offset
    elif preset == "horizontal":
        def motion(cycle: float):
            isometric = 0.60 * intensity
            offset = (intensity * 0.80 * math.sin(cycle), 0.0)
            return isometric, offset
    elif preset == "vertical":
        def motion(cycle: float):
            isometric = 0.60 * intensity
            offset = (0.0, intensity * 0.80 * math.sin(cycle))
            return isometric, offset
    else:
        raise ValueError(f"Unknown preset: {preset!r}")

    return motion


def make_scene_class(preset: str, intensity: float, depth_intensity: float,
                      zoom_crop: float, model: str):
    """Builds a DepthScene subclass with the requested motion baked in.

    Deferred import of depthflow so --help / argument errors don't pay the
    cost of importing torch/transformers first.
    """
    from attrs import define
    from depthflow.estimators.anything import DepthAnythingV2
    from depthflow.scene import DepthScene

    motion = build_motion(preset, intensity)

    @define
    class AmbientScene(DepthScene):
        def update(self):
            isometric, offset = motion(self.cycle)
            self.state.height = depth_intensity
            self.state.steady = 0.30
            self.state.focus = 0.30
            # Crop in slightly so parallax-revealed image edges never enter
            # frame (zoom=1.0 shows the full source image with no margin -
            # any offset/isometric motion then reveals the out-of-bounds
            # edge as a hard black line/seam, a real artifact hit during
            # tuning on this low-res 735x416 source).
            self.state.zoom = zoom_crop
            self.state.isometric = isometric
            self.state.offset = offset

    scene = AmbientScene()
    scene.estimator = DepthAnythingV2(model=model)
    return scene


def render_depth_map_only(scene_path: Path, output_dir: Path, model: str) -> Path:
    """Runs just the depth estimator and saves a viewable PNG. Fast."""
    import imageio.v3 as imageio
    import numpy as np
    from depthflow.estimators.anything import DepthAnythingV2
    from PIL import Image

    print(f"Loading scene image: {scene_path}")
    image = imageio.imread(str(scene_path))
    print(f"Image shape: {image.shape}")

    estimator = DepthAnythingV2(model=model)
    t0 = time.time()
    print(f"Running depth estimation (model={model})...")
    depth = estimator.estimate(image)
    elapsed = time.time() - t0
    print(f"Depth estimation took {elapsed:.2f}s")

    output_dir.mkdir(parents=True, exist_ok=True)
    depth_map_path = output_dir / "depth_map.png"

    # depth is float32 normalized [0, 1] -> 8-bit grayscale for inspection
    depth_8bit = (255.0 * depth).clip(0, 255).astype(np.uint8)
    Image.fromarray(depth_8bit).save(depth_map_path)
    print(f"Saved depth map: {depth_map_path} ({depth_8bit.shape[1]}x{depth_8bit.shape[0]})")
    print(f"min={depth.min():.4f} max={depth.max():.4f} mean={depth.mean():.4f}")
    return depth_map_path


def render_full_video(scene_path: Path, output_dir: Path, args: argparse.Namespace) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_path = output_dir / "base.mp4"

    print(f"Building scene: preset={args.preset} motion-intensity={args.motion_intensity} "
          f"depth-intensity={args.depth_intensity} model={args.model} zoom-crop={args.zoom_crop}")
    scene = make_scene_class(
        preset=args.preset,
        intensity=args.motion_intensity,
        depth_intensity=args.depth_intensity,
        zoom_crop=args.zoom_crop,
        model=args.model,
    )

    print(f"Loading scene image + depth map for: {scene_path}")
    t0 = time.time()
    scene.input(image=str(scene_path))
    print(f"Input ready in {time.time() - t0:.2f}s")

    print(f"Rendering {args.duration}s @ {args.width}x{args.height} {args.fps}fps -> {base_path}")
    t0 = time.time()
    scene.main(
        output=str(base_path),
        time=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )
    elapsed = time.time() - t0
    print(f"Render complete in {elapsed:.2f}s ({args.duration / elapsed:.2f}x realtime)")
    return base_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE,
                         help=f"Input scene image (default: {DEFAULT_SCENE})")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                         help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--depth-map-only", action="store_true",
                         help="Only run depth estimation and save depth_map.png; skip the full video render.")
    parser.add_argument("--skip-depth-map", action="store_true",
                         help="Skip the depth-map-inspection step and go straight to the full render "
                              "(only makes sense once you've already inspected it once).")
    parser.add_argument("--preset", choices=["orbit", "circle", "horizontal", "vertical"], default="orbit",
                         help="Camera motion preset (default: orbit - slow drift-orbit per TASK.md spec).")
    parser.add_argument("--motion-intensity", type=float, default=0.10,
                         help="Camera motion amplitude as a fraction of DepthFlow's own example-preset "
                              "amplitudes (default: 0.10 = 10%%, within the spec's 5-15%% range).")
    parser.add_argument("--depth-intensity", type=float, default=0.15,
                         help="Depth-map displacement strength (DepthState.height; default 0.2 upstream, "
                              "we default a bit lower at 0.15 for a gentler 2.5D effect).")
    parser.add_argument("--zoom-crop", type=float, default=0.90,
                         help="Camera zoom/crop factor (<1.0 crops in) to keep parallax-revealed image "
                              "edges out of frame. Lower = more margin, needed more on low-res sources "
                              "or with higher motion-intensity. Default 0.90.")
    parser.add_argument("--model", choices=["small", "base", "large", "giant"], default="small",
                         help="DepthAnything V2 model size (default: small - fast, good enough for a "
                              "gentle low-intensity effect; larger models are slower with diminishing "
                              "returns for this use case).")
    parser.add_argument("--duration", type=float, default=20.0, help="Loop duration in seconds (default: 20).")
    parser.add_argument("--fps", type=float, default=30.0, help="Frames per second (default: 30).")
    parser.add_argument("--width", type=int, default=1920, help="Output width (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Output height (default: 1080).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.scene.exists():
        print(f"FAIL: scene image not found: {args.scene}", file=sys.stderr)
        return 1

    if not args.skip_depth_map:
        print("=== Phase 1: depth map extraction ===")
        t0 = time.time()
        depth_map_path = render_depth_map_only(args.scene, args.output_dir, args.model)
        print(f"Phase 1 done in {time.time() - t0:.2f}s. Inspect {depth_map_path} before continuing.\n")

    if args.depth_map_only:
        print("--depth-map-only set, stopping here.")
        return 0

    print("=== Phase 2: full parallax video render ===")
    t0 = time.time()
    base_path = render_full_video(args.scene, args.output_dir, args)
    print(f"Phase 2 done in {time.time() - t0:.2f}s. Output: {base_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
