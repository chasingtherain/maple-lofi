
# AI Agent Adoption Maturity Model

A 5-stage framework (0–4) describing how an engineering org's use of AI coding agents evolves — from gated/no-access up to full AI-native operation. Each stage is defined by **your role**, **# of agents run**, **what it looks like**, **the bottleneck to progress**, **products that help**, and **guardrails to put in place**.

---

## Stage 0 — Gated

**Role:** N/A (no real agent use yet) · **Agents:** 0

**What it looks like:**

- Only older/lighter/slower models approved; latency compounds through AI gateways and custom auth
- No MCP governance; internal access to AI tools is gated or process-heavy
- No IT infra or approval path for hosting Claude-created code/artifacts — outputs only exist locally
- Legacy security/approval processes focused on cost-per-token containment rather than outcomes
- Lack of true technical voices in decision-making

**Products that help:**

- Claude.ai chat
- SSO/SCIM + role-based access
- Org-level budget caps
- Deploy inside existing approvals/IAM
- Data governance package

**Path to Stage 1:** Executive/buyer alignment and escalation of blockers; frameworks for launching Claude securely.

---

## Stage 1 — Assisted

**Role:** You + an agent (a pair) · **Agents:** ~1

**What it looks like:**

- One engineer, one agent, mostly supervised — a fast pair programmer
- One session at a time; you review almost every change before it merges
- **Unlock:** A change that used to fill an afternoon becomes something you finish between meetings
- Work is synchronous — you sit and watch while Claude works, rather than moving to the next task

**Bottleneck:**

- Your attention — low trust in the model's output and lack of self-verification means you feel you must read everything

**Products that help:**

- Claude Code (Desktop, CLI, IDE)
- Claude Cowork, Claude Design
- Usage via Anthropic API, Bedrock, Vertex, or Microsoft Foundry
- Claude Code analytics dashboard + Analytics API
- Compliance API for Claude Enterprise
- Plan mode (review intent before edits)
- Per-seat spend caps
- Centrally managed model/effort settings
- Centrally managed policy
- OpenTelemetry export into existing SIEM/observability stack

**Path to Stage 2:** Run more than one agent at a time; build a self-verification loop you trust (tests + build + lint + e2e in a real dev environment); use auto mode to avoid blocking permission prompts; automate code review.

---

## Stage 2 — Parallel

**Role:** Orchestrator · **Agents:** ~10

**What it looks like:**

- One engineer orchestrates 5–10 agents at once, each on its own worktree/git checkout, jumping between them
- Claude checks its own work (tests, build, lint, security scan) before you see it
- Auto mode always on; automated code review and security review on by default
- Output multiplies — you review final diffs, not keystrokes; backlog of maintenance work shrinks
- Claude writes most of the code
- **Unlock:** A backlog that used to take the team weeks becomes one engineer's afternoon of orchestration

**Bottleneck:**

- Reviewing output — less hand-writing code, more checking six streams of it
- Prompting/steering the model while juggling sessions

**Products that help:**

- Auto mode
- Agent view
- Claude Code Review
- Claude Security Review
- Claude Code on Mobile; cloud execution in Desktop
- Usage via Claude Teams or Claude Enterprise
- Claude Tag (single-task dispatch)
- Worktree isolation in CLI and Desktop
- Remote control (monitor agents from phone)
- Analytics to monitor team usage

**Guardrails:**

- Automatic code quality enforcement: lint, automated tests, typecheck
- Claude-powered end-to-end verification (e.g. Claude Chrome extension or iOS/Android simulator MCP)
- Manual code review, code merge, and security review — hold the same quality bar for human and agent-generated code
- Pre-approve common safe bash and MCP commands in `settings.json`

**Path to Stage 3:** Give Claude a way to pull in context (read code, wikis, discussions); improve agency and code-review speed (agents may touch code owned by other teams); break work into loops/routines; let Claude kick off Claude.

---

## Stage 3 — Supervised Autonomy

**Role:** Manager of managers (an org tree) · **Agents:** ~100

**What it looks like:**

- Claude writes all or nearly all of the code
- "Did you read the code?" becomes "what context was the model missing and how do we solve it for next time?"
- **Unlock:** Claude proactively does work you'd have had to kick off manually; maintenance/cleanup runs continuously in the background

**Bottleneck:**

- Trust in the loop and your team's decision throughput — the agent tree is too deep to babysit; the trap is scaling agent count before the loop has earned widespread trust
- Ensuring efficient token use as usage grows — requires monitoring (OTel/Analytics) and a culture that balances experimentation with cost control once use cases find PMF. Key question: _is this something an engineer would have done?_

**Products that help:**

- Subagents with worktree isolation (parallel agents don't collide)
- Routines, `/loop`, `/batch`, `/goal` to fan out repetitive work
- Dynamic workflows
- Claude Tag (monitor a channel/data source, kick off tasks proactively)
- Automatic code review
- Automatic security review
- Agent sandboxing
- CLAUDE.md and Skills to encode standards
- Tune Auto mode classifier to your team's usage
- Manage token use via model selection, advisors, LSPs, and breaking up CLAUDE.md into lazy Skills

**Path to Stage 4:** Scaled automation of domain-specific use cases (e.g. code migration, fuzzing, feature-building, feedback remediation).

---

## Stage 4 — AI-Native

**Role:** VP steering by intent · **Agents:** ~1,000+

**What it looks like:**

- The loop is fully closed; most agents are kicked off by Claude itself
- Hundreds to thousands of agents run; you steer by intent and monitor by exception
- **Unlock:** A quarter-long migration becomes a workflow you kick off and check on

**Bottleneck:**

- Identifying and automating work at scale, and enforcing the right guardrails for each type of work

**Products that help:**

- Claude Agent SDK — programmatically build and schedule agents
- Claude Tag — active in most Slack channels, auto-responding to posts
- Cost controls for automation
- Model selection for automation

---

## Quick-reference table

|Stage|Role|Agent count|Core bottleneck|Key unlock|
|---|---|---|---|---|
|0 – Gated|—|0|Legacy approval/security process|N/A|
|1 – Assisted|You + agent|~1|Your attention / low trust|Afternoon task → between meetings|
|2 – Parallel|Orchestrator|~10|Reviewing output, steering multiple sessions|Weeks of backlog → one afternoon|
|3 – Supervised autonomy|Manager of managers|~100|Trust in the loop, token efficiency|Proactive background maintenance|
|4 – AI-native|VP steering by intent|~1,000+|Identifying & guardrailing work at scale|Quarter-long migration → a workflow you kick off|