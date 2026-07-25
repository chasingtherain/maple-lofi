#!/bin/bash
# SessionStart hook: surfaces recent history + the current TASK.md "Next up"
# section automatically, so a fresh session doesn't need a manual briefing.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" || exit 0

COMMITS=$(git log --oneline -10 2>/dev/null)
STATUS=$(git status --porcelain 2>/dev/null)
NEXTUP=$(awk '
  /^## Next up/ {flag=1}
  flag && /^## / && !/^## Next up/ {exit}
  flag {print}
' TASK.md 2>/dev/null)

if [ -z "$STATUS" ]; then
  STATUS="(clean)"
fi

jq -n \
  --arg commits "$COMMITS" \
  --arg status "$STATUS" \
  --arg nextup "$NEXTUP" \
  '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: ("Project state, auto-loaded (see CLAUDE.md for the convention behind this):\n\n### Recent commits\n" + $commits + "\n\n### Working tree status\n" + $status + "\n\n### TASK.md — Next up\n" + $nextup)
    }
  }'
