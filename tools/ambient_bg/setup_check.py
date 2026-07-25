#!/usr/bin/env python3
"""Step 0 of the ambient background pipeline: environment / GPU detection.

Standalone, independently re-runnable. Run this before depth_render.py to
confirm the environment is sane instead of finding out 20 minutes into a
render.

Checks, in order:
  1. The `depthflow` PyPI package is installed and actually resolves to
     github.com/BrokenSource/DepthFlow (NOT depthflow.io, an unrelated
     paid SaaS product that happens to share a name).
  2. `ffmpeg` is on PATH.
  3. GPU mode, in priority order: NVIDIA (nvidia-smi) -> Apple Silicon (MPS)
     -> CPU-only. Each path prints what it means for render time; the
     CPU-only path warns explicitly rather than silently grinding for hours.

Usage:
    .venv/bin/python setup_check.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import shutil
import subprocess
import sys

EXPECTED_GITHUB = "github.com/BrokenSource/DepthFlow"


def check_depthflow_package() -> bool:
    try:
        meta = metadata.metadata("depthflow")
    except metadata.PackageNotFoundError:
        print("FAIL: 'depthflow' package is not installed.")
        print("      Run: pip install depthflow")
        return False

    version = meta["Version"]
    project_urls = meta.get_all("Project-URL") or []
    github_url = next((u for u in project_urls if EXPECTED_GITHUB in u), None)

    print(f"OK: depthflow {version} installed")
    if github_url:
        print(f"    Project-URL confirms {github_url.split(',')[-1].strip()}")
        print("    (this is the real BrokenSource/DepthFlow project, not the depthflow.io SaaS product)")
        return True

    print("WARNING: could not confirm this package resolves to "
          f"{EXPECTED_GITHUB} via Project-URL metadata.")
    print(f"    Project-URLs found: {project_urls or '(none)'}")
    print("    Double-check you didn't install a same-named impostor package.")
    return False


def check_cli_vs_library() -> None:
    """Resolve the open question from TASK.md: CLI or Python-library?

    Answer (verified against the installed package, not assumed): DepthFlow
    ships BOTH. `depthflow` on PATH is a real CLI (input/state/da1/da2/main
    subcommands) good for static single-pose renders. But animated motion
    (a slow drift/orbit over the loop duration) requires overriding
    DepthScene.update() per-frame in Python - the CLI's `state` subcommand
    only sets one static pose for the whole render, it has no per-frame
    animation hook. depth_render.py therefore imports depthflow as a
    library and subclasses DepthScene, the same pattern DepthFlow's own
    examples/presets.py uses.
    """
    path = shutil.which("depthflow")
    if path:
        print(f"NOTE: DepthFlow CLI also available at {path} (`depthflow --help`).")
    else:
        print("NOTE: DepthFlow CLI not found on PATH (only matters if you wanted static single-pose renders).")
    print("    This pipeline uses the Python library API (DepthScene subclass) instead of the CLI,")
    print("    because animated drift/orbit motion needs a per-frame update() hook that the CLI lacks.")


def check_ffmpeg() -> bool:
    path = shutil.which("ffmpeg")
    if not path:
        print("FAIL: ffmpeg not found on PATH.")
        return False
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        first_line = result.stdout.splitlines()[0] if result.stdout else "(version string unavailable)"
    except Exception as exc:  # noqa: BLE001 - best-effort version print
        first_line = f"(could not run -version: {exc})"
    print(f"OK: ffmpeg found at {path}")
    print(f"    {first_line}")
    return True


def detect_gpu_mode() -> str:
    """Returns one of: 'nvidia', 'apple_silicon', 'cpu'. Never hangs."""

    # 1. NVIDIA - fastest path, use NVENC for encoding if present.
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0:
            print("OK: NVIDIA GPU detected via nvidia-smi.")
            print("    -> depth estimation on CUDA, video encoding via NVENC (h264-nvenc).")
            return "nvidia"
        print("NOTE: nvidia-smi is on PATH but did not report a working GPU - falling through.")

    # 2. Apple Silicon - MPS backend, with an explicit fallback flag since
    #    some depth-model ops aren't implemented on MPS yet and would
    #    otherwise hard-crash instead of degrading gracefully.
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import torch  # noqa: PLC0415 - heavy import, only pay for it if relevant
            mps_available = torch.backends.mps.is_available()
        except ImportError:
            mps_available = False
        if mps_available:
            print("OK: Apple Silicon detected, PyTorch MPS backend available.")
            print("    Setting PYTORCH_ENABLE_MPS_FALLBACK=1 (some depth-model ops aren't implemented")
            print("    on MPS yet; without this flag those ops raise instead of falling back to CPU).")
            print("    WARNING: MPS is noticeably slower than a dedicated NVIDIA GPU for depth estimation.")
            print("    Expect it - this is not a hang.")
            return "apple_silicon"
        print("WARNING: Apple Silicon CPU detected but the MPS backend is unavailable in this torch build.")
        print("    Falling back to CPU-only. Render times will be significantly longer.")
        return "cpu"

    # 3. No GPU acceleration at all.
    print("WARNING: No GPU acceleration detected (no NVIDIA, not Apple Silicon).")
    print("    Falling back to CPU-only. Render times will be MUCH longer than GPU (often 5-10x+).")
    print("    This is expected behavior, not a hang - budget accordingly before starting a full render.")
    return "cpu"


def main() -> int:
    print("=== ambient_bg setup_check ===\n")

    print("[1/3] depthflow package")
    package_ok = check_depthflow_package()
    check_cli_vs_library()
    print()

    print("[2/3] ffmpeg")
    ffmpeg_ok = check_ffmpeg()
    print()

    print("[3/3] GPU / compute mode")
    mode = detect_gpu_mode()
    print()

    print("=== Summary ===")
    print(f"depthflow package : {'OK' if package_ok else 'FAIL'}")
    print(f"ffmpeg             : {'OK' if ffmpeg_ok else 'FAIL'}")
    print(f"compute mode       : {mode}")

    if not (package_ok and ffmpeg_ok):
        print("\nOne or more required checks failed - fix before running depth_render.py.")
        return 1

    print("\nEnvironment OK. Proceed to depth_render.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
