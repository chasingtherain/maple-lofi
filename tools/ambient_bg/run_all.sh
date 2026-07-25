#!/usr/bin/env bash
# T7: single-command orchestrator for the ambient background pipeline.
#
# Chains the independently re-runnable stages that today have to be run by
# hand, in the right order, with matching flags:
#
#   depth_render.py -> [flower_sway.py] -> [foliage_sway.py] -> particles.py -> composite.sh
#
# This is a *thin* orchestrator: it does not reimplement any stage's logic,
# it just forwards one shared set of user-facing flags (--scene, --duration,
# --output) to each stage's own existing CLI, in its own already-tuned
# defaults otherwise. Every stage remains independently re-runnable on its
# own afterward - this script only ever calls the stage scripts as
# subprocesses, it never inlines their behavior.
#
# Sway is opt-in and the two sway stages are independently toggleable
# (--flower-sway / --foliage-sway / --sway for both) because they are optional
# artistic layers, not required parts of the pipeline, and because
# foliage_sway.py has a known, documented visual artifact (streaking/tearing
# against detailed backgrounds - see its own module docstring and commit
# 77f9611 / merge 79327ef) that a caller should be choosing to accept, not
# have silently bundled in. Default: neither sway stage runs, matching the
# base pipeline's original (pre-sway) behavior.
#
# Both sway scripts default to reading and writing output/base.mp4 in place
# (--input/--output both default to the same path), so when both are
# requested they must run sequentially against the same file, in this order:
# flower first (fixed duplication bug, verified safe), then foliage (works,
# but carries the known artifact) - flower_sway.py is not built on top of
# foliage_sway.py or vice versa, they're independent techniques, so order
# between them doesn't matter for correctness, but running flower first
# means an operator who bails after seeing the foliage artifact still has a
# clean flower-swayed base.mp4 to fall back to.
#
# Usage:
#   ./run_all.sh
#   ./run_all.sh --scene path/to/scene.jpg --duration 15 --output output/final.mp4
#   ./run_all.sh --flower-sway
#   ./run_all.sh --flower-sway --foliage-sway
#   ./run_all.sh --sway                       # shorthand for both sway stages
#   ./run_all.sh --skip-depth-map             # skip depth_render's depth-map-inspection phase
#   ./run_all.sh --opacity 0.4                # forwarded to composite.sh
#
# Each stage remains independently re-runnable afterward, e.g.:
#   .venv/bin/python particles.py --count 150
#   ./composite.sh --opacity 0.3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "FAIL: $PYTHON not found. Set up the venv first (see requirements.txt / setup_check.py)." >&2
  exit 1
fi

# --- shared, user-facing flags (forwarded to each stage's own CLI) ---
SCENE=""            # empty = let depth_render.py use its own default
DURATION=20.0
OUTPUT=""            # empty = let composite.sh use its own default (output/final.mp4)
OUTPUT_DIR="$SCRIPT_DIR/output"
FLOWER_SWAY=0
FOLIAGE_SWAY=0
SKIP_DEPTH_MAP=0
OPACITY=""           # empty = let composite.sh use its own default (0.55)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scene) SCENE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --flower-sway) FLOWER_SWAY=1; shift ;;
    --foliage-sway) FOLIAGE_SWAY=1; shift ;;
    --sway) FLOWER_SWAY=1; FOLIAGE_SWAY=1; shift ;;
    --skip-depth-map) SKIP_DEPTH_MAP=1; shift ;;
    --opacity) OPACITY="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "${BASH_SOURCE[0]}" | grep -E '^#' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

BASE_VIDEO="$OUTPUT_DIR/base.mp4"
PARTICLES_VIDEO="$OUTPUT_DIR/particles.mov"
FINAL_OUTPUT="${OUTPUT:-$OUTPUT_DIR/final.mp4}"

echo "=== ambient_bg run_all.sh ==="
echo "duration    = ${DURATION}s"
echo "output-dir  = $OUTPUT_DIR"
echo "final output = $FINAL_OUTPUT"
if [[ $FLOWER_SWAY -eq 1 ]]; then FLOWER_STATUS="yes"; else FLOWER_STATUS="no"; fi
if [[ $FOLIAGE_SWAY -eq 1 ]]; then
  FOLIAGE_STATUS="yes (known streaking/tearing artifact on detailed backgrounds - see foliage_sway.py docstring)"
else
  FOLIAGE_STATUS="no"
fi
echo "flower-sway = $FLOWER_STATUS"
echo "foliage-sway = $FOLIAGE_STATUS"
echo ""

PIPELINE_START=$(date +%s)

# --- Stage 1: depth_render.py (parallax base) ---
DEPTH_ARGS=(--output-dir "$OUTPUT_DIR" --duration "$DURATION")
[[ -n "$SCENE" ]] && DEPTH_ARGS+=(--scene "$SCENE")
[[ $SKIP_DEPTH_MAP -eq 1 ]] && DEPTH_ARGS+=(--skip-depth-map)

echo "--- Stage 1/4: depth_render.py ---"
echo "+ $PYTHON depth_render.py ${DEPTH_ARGS[*]}"
"$PYTHON" "$SCRIPT_DIR/depth_render.py" "${DEPTH_ARGS[@]}"
echo ""

# --- Stage 1.5/1.6: optional sway passes, both operate on $BASE_VIDEO in place ---
if [[ $FLOWER_SWAY -eq 1 ]]; then
  echo "--- Stage 2a/4: flower_sway.py (optional) ---"
  echo "+ $PYTHON flower_sway.py --input $BASE_VIDEO --output $BASE_VIDEO"
  "$PYTHON" "$SCRIPT_DIR/flower_sway.py" --input "$BASE_VIDEO" --output "$BASE_VIDEO"
  echo ""
fi

if [[ $FOLIAGE_SWAY -eq 1 ]]; then
  echo "--- Stage 2b/4: foliage_sway.py (optional - known streaking/tearing artifact on detailed backgrounds, not suppressed here) ---"
  echo "+ $PYTHON foliage_sway.py --input $BASE_VIDEO --output $BASE_VIDEO"
  "$PYTHON" "$SCRIPT_DIR/foliage_sway.py" --input "$BASE_VIDEO" --output "$BASE_VIDEO"
  echo ""
fi

# --- Stage 3: particles.py (dust-mote overlay) ---
echo "--- Stage 3/4: particles.py ---"
echo "+ $PYTHON particles.py --output-dir $OUTPUT_DIR --duration $DURATION"
"$PYTHON" "$SCRIPT_DIR/particles.py" --output-dir "$OUTPUT_DIR" --duration "$DURATION"
echo ""

# --- Stage 4: composite.sh (combine + verify loop seam) ---
COMPOSITE_ARGS=(--base "$BASE_VIDEO" --particles "$PARTICLES_VIDEO" --output "$FINAL_OUTPUT")
[[ -n "$OPACITY" ]] && COMPOSITE_ARGS+=(--opacity "$OPACITY")

echo "--- Stage 4/4: composite.sh ---"
echo "+ $SCRIPT_DIR/composite.sh ${COMPOSITE_ARGS[*]}"
"$SCRIPT_DIR/composite.sh" "${COMPOSITE_ARGS[@]}"

PIPELINE_END=$(date +%s)
echo ""
echo "=== run_all.sh done in $((PIPELINE_END - PIPELINE_START))s -> $FINAL_OUTPUT ==="
