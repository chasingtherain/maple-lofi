# PRD — Soundweave Live (Local Studio → Public Product)

## 0. Status

This is the launch roadmap, organized in phases. **Phase 0 and Phase 1 are
both fully authorized to start.** Phases 2–4 are fully specced so no context
is lost, but each is explicitly gated — see each phase's Authorization line.
Do not dispatch subagents against any ungated item without a fresh, explicit
go-ahead, even though every package is written in dispatch-ready format
below.

Companion doc: `PRD.md` (feature-level spec for the `mashup` subcommand
itself — URL ingestion, crossfade, video modes). This doc is about turning
that already-built pipeline into something live users can reach, not about
changing pipeline behavior.

## 1. Problem

Soundweave's pipeline (crossfade, loudnorm, MP3 encode, video render,
YouTube description/timestamp generation) is fully built and works from the
CLI and a localhost-only browser UI (`mashup-ui`). It has no path to being
used by anyone other than the person running it on their own machine. This
doc specs that path.

## 2. Ground truth established before writing this (don't re-derive)

Verified directly against the code, not assumed:

- `mashup --urls` (YouTube URL list), `--loop-count`, and all three video
  modes (`--image` / `--images` / `--animated-background`) are implemented
  and wired end-to-end. Confirmed in `mashup_config.py` and `cli.py`.
- `youtube_description.txt` (description + chapter timestamps, real video
  titles) is generated on every mashup run. Confirmed in
  `cli.py::_run_mashup_subcommand`.
- `mashup-ui` (`soundweave/ui/server.py`, `templates.py`) already exposes
  all of the above as web forms, launches the CLI as a subprocess, and polls
  a status endpoint. It is bound to `127.0.0.1` only and holds job state
  in-memory (dict), by design (see `CLAUDE.md`).
- `manifest.json` (structured per-stage record) is only written to disk
  **once, at the end of a run** (`pipeline.py:195` / `:242`) — not
  incrementally. It cannot drive a live progress bar without a pipeline
  change.
- Stage-boundary log markers (`=== Stage N: ... ===`) exist for Stage 3
  (encode) and Stage 4 (video) in the mashup runner, but **not** for Stage 0
  (download) or Stage 2 (merge) — those are only code comments today. A
  progress bar built from log-parsing alone is therefore coarse (3–4
  phases), not per-track granular, unless `cli.py` gets new log lines.

**Conclusion this PRD is built on**: the pipeline is not the gap. The gap is
(a) the UI throws away the finished product instead of presenting it, and
(b) there is no way for anyone but the local operator to reach any of this.

## 3. Rejected approaches (don't re-litigate)

- **Google Apps Script as the processing backend** — hard no. Apps Script
  cannot execute arbitrary binaries (no subprocess/filesystem access), so it
  cannot run `ffmpeg`/`yt-dlp` at all, regardless of its time limits.
- **Firebase as the sole backend** — Cloud Functions *can* bundle ffmpeg/
  yt-dlp and run up to 60 min (2nd gen), so it's not disqualified the way
  Apps Script is. But the free (Spark) plan blocks all non-Google outbound
  network calls, which is yt-dlp's entire job — so "free" requires the paid
  Blaze plan immediately, at which point per-invocation/per-GB billing and
  memory-backed ephemeral `/tmp` make it a worse fit than a flat-fee VM for
  long-running, disk-heavy, CPU-heavy jobs. **Decision**: use Firebase only
  for what it's actually good at — Auth and Firestore (Phase 2) — not as the
  compute layer.
- **Lofi processing / audio effects** — out of scope for the whole project,
  per `CLAUDE.md` non-goals. Not resurrected by this doc.

## 4. Phase 0 — Legacy Cleanup

**Authorization**: fully authorized by JP, 2026-08-14. Worktree removal
(Package A) pre-authorized as verified low-risk. Docs audit (Package B)
resolved: keep `AI-stages.md` (confirmed intentional, out of scope), delete
both stale ADRs outright.

**Objective**: clear out cruft that's accumulated in the repo before more
work lands on top of it, so future phases (and future sessions) aren't
reading stale or orphaned state as if it were current.

**Findings** (verified directly against the repo, not assumed):

- **6 orphaned git worktrees** in `.claude/worktrees/agent-*`, left over
  from a previous parallel-agent orchestration session. Confirmed via
  `git worktree list`: all 6 sit on branches (`worktree-agent-*`) that are
  fully merged into `main` (`git log main..<branch>` is empty for all six)
  and have a clean working tree (`git status --porcelain` empty for all
  six). Nothing here is unique or at risk — these are pure leftover
  checkouts that should have been removed after their merges landed. This
  is exactly the failure mode this project's own orchestration standards
  warn about (worktrees not guaranteed fresh, must be cleaned up serially
  after merge).
- **`docs/ADRs/001-pipeline-architecture.md` and
  `002-dataclass-configuration.md`** contain code examples built entirely
  around the lofi processing stage (`lofi_stage`, `skip_lofi`,
  `apply_lofi_effects`, `lofi_handler` event wiring) — a feature `CLAUDE.md`
  confirms "was fully removed from the code in an earlier refactor."
  `soundweave/stages/` has no `lofi.py`; the code itself is clean. Only
  these two ADRs still describe lofi as if it's part of the live
  architecture. `CLAUDE.md` already flags this drift ("despite some
  historical ADRs using it as an example") but doesn't resolve it.
  **Decided by JP, 2026-08-14: delete both outright** — overrides the usual
  ADR-immutability convention (the other options considered were annotating
  with a superseded/historical header, or leaving as-is since `CLAUDE.md`
  already contextualizes the drift; JP chose deletion instead).
- **`AI-stages.md`** (repo root) is a generic "AI Agent Adoption Maturity
  Model" document — org-level AI-adoption stages, MCP governance, gateway
  latency — with no reference to Soundweave, audio processing, or this
  project's actual domain. **Decided by JP, 2026-08-14: keep** — confirmed
  intentional. Out of scope for Package B.
- **Not included in this phase** (checked, ruled out as a different
  category): the root `test_*/` directories (`test_output/`, `test_input/`,
  `test_refactor/`, `test_crossfade_4500/`, `test_assets/`,
  `test_t0_smoke/`) and `tools/ambient_bg/.venv/` + `tools/ambient_bg/
  output/` are all local scratch artifacts already covered by `.gitignore`
  patterns — never committed, so there's no repo cruft to remove, only
  local disk space to reclaim if you want it later. Not a code change, not
  something a subagent needs to touch. `real_assets/` (one untracked image)
  is left alone — ambiguous purpose, looks like active working material,
  not obviously dead.

**Packages**:

- **Package A — Worktree cleanup** · owns `.claude/worktrees/` only
  - Output: `git worktree remove` for each of the 6 verified-clean,
    verified-merged worktrees listed above (not raw `rm -rf` — must go
    through git so `.git/worktrees` metadata doesn't end up corrupted),
    followed by `git branch -d` (lowercase — refuses if a branch isn't
    actually merged, which is the correct safety check to keep here even
    though this audit already verified it) for the now-orphaned
    `worktree-agent-*` branches.
  - Failure mode to avoid: don't touch anything outside
    `.claude/worktrees/` and the branches this package itself identified —
    do not go hunting for other "cleanup" opportunities.
  - Stop condition: if any worktree shows uncommitted changes or an
    unmerged commit at dispatch time (state may have changed since this
    audit), stop and report it rather than removing it.
  - Not included: `.claude/worktrees/` as a directory can stay; only the
    stale checkouts inside it are in scope.

- **Package B — Docs audit** · owns `docs/ADRs/001-pipeline-architecture.md`,
  `docs/ADRs/002-dataclass-configuration.md`
  - Objective: delete both ADRs outright, per JP's decision above.
  - Failure mode to avoid: don't touch `AI-stages.md` or any other doc —
    it was explicitly kept, not in scope.
  - Not included: no replacement ADR documenting current (post-lofi)
    architecture is being written here — flag separately if that's wanted,
    don't add it unprompted.

---

## 5. Phase 1 — Local Studio Polish

**Authorization**: pre-authorized by JP (repo owner), this conversation,
2026-08-14. Scope limited exactly to what's listed below.

**Objective**: make the existing local product (mashup-ui) actually present
its output, with a real progress indicator, without touching any processing
code.

**Hard boundary**: zero changes to `pipeline.py`, `cli.py`, `stages/`,
`ffmpeg/`, `ytdlp/`, `logging/manifest.py`. Everything lives in
`soundweave/ui/` and `tests/`. No new pip dependencies — stdlib-served
HTML/CSS/JS only, per the project's existing constraint.

**Shared JSON contract** (so Package C and D never need to touch each
other's files):

```
GET /api/status/<job_id> →
{
  "phase": "preparing" | "encoding" | "video" | "done" | "failed",
  "log": "...",                       // unchanged, still available
  "running": bool,
  "returncode": int | null,
  "outputs": [{"name": str, "path": str, "size_mb": float}],
  "description_text": str | null,     // contents of youtube_description.txt once written
  "output_dir": str
}
```

**Design system** (researched and approved by JP, 2026-08-14 — see chat log
for sources; Package C implements this exactly, does not re-derive it):

Palette is Radix Colors' Slate/Indigo/Green/Amber/Red scales, hardcoded as
literal hex values in `templates.py`'s `<style>` block — no npm install, no
build step, consistent with the project's no-new-dependency rule. Dark-first
(matches developer-tool convention and long log-reading sessions) but must
respect `prefers-color-scheme` rather than forcing dark.

| Role | Light | Dark |
|---|---|---|
| Page background | `#fcfcfd` | `#111113` |
| Card background | `#f9f9fb` | `#18191b` |
| Border | `#cdced6` | `#43484e` |
| Body text | `#1c2024` | `#edeef0` |
| Accent (buttons/links/focus/progress fill) | `#3e63dd` solid, `#3a5bc7` text | `#3e63dd` solid, `#9eb1ff` text |
| Success | `#30a46c` solid | `#218358` text (light) / `#3dd68c` text (dark) |
| Running | `#ffc53d` solid | `#ab6400` text (light) / `#ffca16` text (dark) |
| Error | `#e5484d` solid | `#ce2c31` text (light) / `#ff9592` text (dark) |

Typography: system font stack for UI chrome, monospace for anything
technical (logs, file paths, job IDs, filenames) — already partially applied
in the current templates, extend consistently.

Layout rules:
- Keep the current single-column, ~640–760px max-width form layout; break it
  into visually distinct cards (card-bg + border from the table above)
  grouping related inputs, instead of one long unbroken form.
- Progress renders as a **horizontal step tracker** (Preparing → Encoding →
  Video → Done), current step highlighted, completed steps checked — **not**
  a smooth 0–100% bar. Deliberate: Phase 1's progress data is only
  phase-level (see §2 — no per-track granularity without touching
  `cli.py`), so a continuous percentage would fake precision the data
  doesn't have.
- Log collapsed behind a "View full log" disclosure by default, monospace,
  dark terminal-style surface even in light mode.
- Results page: one card per output file (icon, name, size, download
  button) + a dedicated card for the YouTube description with a copy
  button.
- Status is never color-only — always paired with a text label/icon (screen
  reader accessibility): "✓ Done", "● Running", "✕ Failed".
- Transitions subtle, 200–500ms.

**Build**:
1. Progress bar — 3–4 coarse phases parsed from existing log text
   server-side, rendered per the step-tracker rule above. Full log demoted
   to a collapsed "View log" detail.
2. Results view — inline `youtube_description.txt` preview with copy
   button, download links for every output file. Replaces the bare
   `"Done - output in {output_dir}"` line.
3. Visual redesign of Index/Loop/Job pages — professional look, still plain
   HTML/CSS/vanilla JS.
4. Merge Loop into Mashup as the primary flow (`--loop-count` already
   covers repeat); standalone single-file/URL loop becomes a secondary mode
   on the same page, not a disconnected nav item.
5. Lightweight job history — list past local runs by reading existing
   output directories on disk. No database.

**Remove**: the `<pre>` log as the *primary* status indicator; the bare
success message; the two-separate-pages Mashup/Loop nav (superseded by #4).

**Packages**:

- **Package C — Frontend** · owns `soundweave/ui/templates.py` (+ new
  `soundweave/ui/static/` if needed)
  - Implements the **Design system** spec above exactly (palette hex values,
    step-tracker progress, card layout, typography) — do not re-derive or
    substitute a different palette/layout approach.
  - Output: diff to `templates.py` (+ static assets), no server logic.
  - Failure mode to avoid: touching `server.py` routing, adding a JS
    framework or build step.
  - Stop condition: if the JSON contract doesn't cover a UI need, stop and
    report the gap rather than inventing a new field unilaterally.
  - Not included: job history markup may be time-boxed out — flag, don't
    skip silently.

- **Package D — Status/progress backend** · owns `soundweave/ui/server.py`
  (+ new `soundweave/ui/progress.py`)
  - Output: diff to `server.py`, new `progress.py`.
  - Failure mode to avoid: modifying `cli.py` to get finer progress
    granularity — coarse phases only, this phase.
  - Stop condition: if log-text phase detection is unreliable against a
    real captured run, stop and report the actual log sample rather than
    guessing at a fragile regex.
  - Not included: authentication, multi-user job isolation.

- **Package E — Tests** · owns `tests/test_ui_progress.py`,
  `tests/test_ui_server.py`
  - Output: new test files, must pass under `pytest tests/`.
  - Failure mode to avoid: mocking away the actual parsing logic under
    test.
  - Stop condition: if Package D's contract shape changes mid-flight, stop
    and re-sync rather than testing a stale contract.
  - Not included: browser/UI automation (no Selenium/Playwright — new
    dependency, out of scope).

---

## 6. Phase 2 — Production Backend

**Authorization**: **NOT authorized.** Specified for continuity only. Do not
start without an explicit go-ahead, separate from Phase 1's.

**Objective**: replace "runs on the operator's machine" with "runs on a
server multiple concurrent strangers can submit jobs to" — this is the
literal "backend that can process these jobs" from the original ask.

**Architecture decisions already made** (carry forward, don't re-decide):

- Compute: one Oracle Cloud **Always-Free** VM (real subprocess execution,
  no execution-time games). Fallback if capacity is unobtainable at build
  time: ~$5/mo Hetzner VM. Not serverless — see §3 for why.
- **Stay stdlib-first, per the project's existing "no external Python
  packages in production code" rule** (`CLAUDE.md`). This has concrete
  consequences for Phase 1 that don't exist yet in the codebase:
  - Job queue/state: **SQLite** (stdlib `sqlite3`), not Redis/Celery — a
    `jobs` table with status/timestamps/params, not a new service to run.
  - HTTP API: extend the existing stdlib `http.server`-based approach
    already used in `soundweave/ui/server.py`, not Flask/FastAPI.
  - Object storage (Cloudflare R2, S3-compatible): **open decision, not
    resolved** — R2 requires SigV4-signed requests. Either (a) implement
    minimal stdlib SigV4 signing (zero new deps, more code, consistent with
    project philosophy) or (b) take an explicit, scoped exception and add
    `boto3`. Whoever picks this up must raise it as a decision, not silently
    pick one.
- Exposure: Cloudflare Tunnel (free), no open ports/static IP needed on the
  VM.

**Packages** (file paths are proposed, not yet real — no Phase 2 code exists
in the repo today):

- **Package F — Job Queue & Worker Core** · new `soundweave/worker/queue.py`
  (SQLite-backed job table: enqueue/dequeue/heartbeat/status transitions),
  new `soundweave/worker/runner.py` (worker loop: pull job → build CLI argv
  from job params → subprocess the existing `soundweave` CLI unchanged →
  capture log → update job row → hand off outputs to Package G on success →
  clean up job dir on failure, mirroring today's `_launch_job` contract but
  persistent and safe for multiple workers instead of an in-memory dict).
  - Not included: does not change what the CLI does — it only invokes it.

- **Package G — Storage adapter** · new `soundweave/storage/r2.py` —
  upload/download/delete against R2. Must surface the SigV4-vs-boto3
  decision above rather than resolving it silently.

- **Package H — Public API** · extends `soundweave/ui/server.py` (or splits
  into a new `soundweave/api/server.py`) to accept job submissions over the
  network, serving Phase 1's JSON contract but backed by Package F's
  persistent queue instead of an in-memory dict.
  - Stop condition: if going from single-machine in-memory state to
    multi-worker SQLite state breaks Phase 1's contract shape, stop and
    reconcile — Phase 1's frontend should not need to change to consume
    this.

- **Package I — Ops runbook** (not code) · deliverable is
  `docs/RUNBOOK_PHASE2.md`: VM provisioning steps, Cloudflare Tunnel
  config, process supervision (systemd units) for the API and worker,
  basic backup notes. This is operational work, not something a subagent
  should "complete" unattended — provisioning a real internet-facing VM is
  exactly the kind of hard-to-reverse, shared-system action that needs a
  human running the actual commands, per this project's own orchestration
  standards.

---

## 7. Phase 3 — Accounts & Compliance

**Authorization**: **NOT authorized.** This phase is a **hard gate**, not
optional polish — it exists because the "public product, open signup"
choice was made explicitly earlier in this project's planning, and that
choice is what makes accountability infrastructure mandatory before Phase 2
is exposed to real strangers.

**Objective**: make it possible to know who submitted what, give a legal
path for takedown requests, and stop the operator (not the user) from
carrying unbounded legal exposure for downloading copyrighted audio on
strangers' behalf.

**Architecture decisions already made**:
- Auth: Firebase Auth (free at this scale, solves login without building
  one).
- Job state / live progress: Firestore, replacing Phase 1's log-parsing
  with realtime listeners once a real backend exists.

**Packages**:

- **Package J — Auth integration** · new `soundweave/auth/firebase.py` —
  verifies Firebase ID tokens on API requests from Package H.

- **Package K — Audit & takedown infrastructure** · per-account job log
  (who submitted which URL, when) persisted alongside Package F's job
  table; a takedown-intake form/endpoint that logs and routes requests.
  - **Explicit non-agent-owned item**: draft ToS/DMAC-agent-registration
    text can be scaffolded by an agent, but the actual legal language and
    DMCA agent registration **must be reviewed and approved by a human**
    (JP, or actual legal counsel) before Phase 3 can be marked done. A
    subagent completing this package does not mean this phase is done.

---

## 8. Phase 4 — Public Launch

**Authorization**: **NOT authorized. Also not fully specced** — blocked on
open business questions, listed below, that change what "done" means for
this phase. Don't start design work here until those are answered.

**Known components** (architecture-level only):
- Rate limiting — per-account job/day and concurrent-job limits.
- Retention/cleanup — output files must expire on a schedule; the VM disk
  will fill up otherwise. Window unspecified.
- Monitoring/alerting — at minimum, disk-usage alerting on the VM.

**Open questions blocking this phase** (need your input before it can be
specced further):
- Business model: free, ad-supported, or paid? This decides the rate-limit
  numbers, the retention window, and whether Phase 3's DMCA/legal effort is
  worth carrying before there's any usage signal.
- Growth/marketing: not discussed at all yet.

## 9. Out of scope, all phases

Full-video downloads (not just audio), true overlapping DJ-style mashups,
automated Content-ID/copyright risk scoring, lofi/audio-effects processing
— all per `PRD.md` §8 and `CLAUDE.md` non-goals. Not reopened by this doc.

## 10. Execution plan — dispatch mode per phase

Stress-tested by an independent adversarial review, 2026-08-14 (see chat
log). Four points below were sharpened or corrected as a result; everything
else in the table survived scrutiny unchanged and isn't re-litigated here.

| Phase | Packages | Dispatch mode | Why |
|---|---|---|---|
| 0 — Legacy Cleanup | A (worktree cleanup), B (delete 2 ADRs) | Inline, no subagent dispatch — still Stage 1 (an agent doing the work while JP watches), not zero-agent | For destructive git operations, synchronous inline execution is *more* reviewable than dispatch-then-review-the-diff, because by the time a diff exists to review, the deletion already happened. Git's own refusal-on-dirty/unmerged checks substitute for the isolation a subagent worktree would otherwise provide. |
| 1 — Local Studio Polish | C (frontend), D (backend), E (tests) | Stage 2 — C and D dispatched in parallel; E dispatched only after D's contract implementation has actually landed, not simultaneously | E's stop condition depends on D's real behavior (real log samples), not the documented contract shape — firing all three at once risks E idling or testing a contract that doesn't exist yet. |
| 2 — Production Backend | F, G, H, I | Stage 2 for F/G/H once authorized; I is Stage 1 (agent drafts the runbook, human executes the VM commands) | I is agent-assisted, human-executed — that's Stage 1's actual definition, not zero-agent. Provisioning a real internet-facing VM is hard-to-reverse and shared-system, so a human runs the commands directly. |
| 3 — Accounts & Compliance | J, K | Stage 2 for scaffolding, including drafting ToS/DMCA text; **legal approval only** is the human-only gate, not all of Package K | Drafting is agent work per the package's own definition. Only sign-off on that draft is outside any agent's authority. |

**Phase 0 — `/code-review` gate, resolved**: `TASK.md`'s ground rules make
`/code-review` non-negotiable for every diff; inline execution doesn't get a
silent exception.
- Package A (worktree/branch removal): no `/code-review` needed — nothing
  new is introduced, only already-merged, already-reviewed content is
  removed.
- Package B (delete 2 ADRs): still routes through `/code-review` despite
  being small — it's a real repo content change, and the rule carves out no
  exception for "simple."

**Phase 1 — merge order and partial-failure handling** (previously only
asserted as "serial with a gate," not operationalized):
1. Dispatch C and D in parallel, worktree-isolated.
2. When each lands, run its own test/build/lint gate individually — do not
   batch both and fix together.
3. Merge whichever of C/D is clean first, independently of the other's
   status — disjoint files, so one failing review does not block the other.
4. Only once D is *merged* (not just landed) does E get dispatched, against
   D's real code.
5. Merge E last, same individual-gate discipline.

**Phase 3 — rescoped**: "gated by a human loop" applies to legal approval of
Package K's ToS/DMCA text, not to the drafting itself, which is ordinary
agent scaffolding work like the rest of the phase.
