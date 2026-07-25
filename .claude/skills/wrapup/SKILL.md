---
name: wrapup
description: End-of-session ritual — updates TASK.md, seeds durable memory, and commits, so the next session (this one's SessionStart hook) never needs a manual briefing. Invoke when the user says "wrap up", "wrapup", or asks to close out the session.
---

# Wrapup

Run this at the end of a session to write this session's state back into the project, mirroring what `SessionStart` reads in. Follow the steps in order — don't skip the pull-before-commit step, this repo sometimes has multiple sessions running at once.

## 1. Reconstruct what happened this session

- `git log` for any commits made this session, `git status`/`git diff` for anything still uncommitted.
- Review the conversation itself for the parts a diff won't show: what was decided, what was tried and rejected, any surprising results, any user corrections. `TASK.md`'s existing entries (e.g. the DepthFlow full-record section) are the bar — capture the *why*, not just the *what*.

## 2. Settle any uncommitted work

If there's uncommitted code/feature work from this session, surface it to the user as part of the step-6 confirmation rather than silently folding it in — `TASK.md` entries cite commit hashes, so work generally needs a commit before it can be referenced that way. Don't invent a hash for uncommitted work.

## 3. Update TASK.md

Following the file's own established conventions:
- Move finished items out of "Next up" into "Completed", with the commit hash.
- If a task has enough tuning/verification/decision detail worth keeping (judgment call — the DepthFlow entry is the precedent), write a full-record section rather than a one-liner.
- Rewrite "Next up" to reflect the actual next actionable step. If nothing concrete is queued, say so plainly rather than leaving stale content.

## 4. Memory-seeding pass

Same bar as any other memory write — see the memory-type descriptions available to you. Only write something if it's a durable, cross-session lesson:
- A working approach the user confirmed or corrected (feedback memory).
- A new standing fact about the project's direction/constraints, with a *why* (project memory).
- Something new and load-bearing about how the user works (user memory).

Do **not** re-save anything that's just restating what `TASK.md`/`CLAUDE.md` now say — that's duplication, not memory. Update `MEMORY.md`'s index for anything new.

## 5. Pull before committing

This repo sometimes has multiple sessions running concurrently, so the local branch can be behind by the time a session wraps up:

```bash
git fetch origin 2>/dev/null && git pull --rebase 2>/dev/null || true
```

- If there's no remote configured, this is a no-op — proceed.
- If the pull/rebase hits conflicts, **stop and surface them to the user** — don't attempt to auto-resolve. Conflicts here usually mean another session touched `TASK.md`'s "Next up" section or the same code, and picking a resolution is a judgment call for the user.
- Do this *before* staging, so the commit lands on top of whatever the other session(s) already pushed.

## 6. Confirm, then commit

Show the user a summary: what's being committed (feature work if any, `TASK.md` changes, new memory files), and the drafted commit message. Wait for explicit confirmation — this mirrors the repo's normal git discipline, `/wrapup` being invoked doesn't itself authorize the commit content.

Once confirmed:
- Stage the relevant files (named explicitly, not `-A`).
- Commit with a message describing the *why*, ending with the `Co-Authored-By` trailer per standard convention.
- Run `git status` after, to confirm a clean result.
- **Do not push** unless the user separately asks — `/wrapup` closes out local state, it doesn't publish it.
