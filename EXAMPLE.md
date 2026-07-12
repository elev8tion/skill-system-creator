# Worked Example: the `demo` Chain

A complete, concrete 3-phase pipeline chain — `demo-scan → demo-plan → demo-report` —
with every file filled in and the state file shown at each transition. Pattern-match
against this when generating a new chain. Nothing here is a placeholder except where
marked with angle brackets.

The chain's job (deliberately simple): scan a project for TODO comments, plan which
ones to address, and produce a report.

---

## File 1: `~/.claude/skills/demo-scan/SKILL.md`

````markdown
---
name: demo-scan
description: >
  Phase 1 of 3 in the demo chain. Scans the current project for TODO and FIXME
  comments and records them in the chain state file. Use this to start a demo chain
  run. Trigger: "demo-scan", "start the demo chain", "scan for TODOs with the demo
  chain".
---

# Demo: Scan

Chain version: 1

Phase 1 of 3: **scan** → plan → report

## Overview

Finds every TODO/FIXME comment in the project and writes them to the chain state
file so the plan phase can prioritize them.

## Workflow

### Step 1 — Initialize State

This is phase 1, so there is no previous phase to check. If `.demo-state.md` already
exists with `status: complete`, ask the user whether to start fresh (overwrite) or
stop. If it exists mid-flight, ask whether to resume or restart.

Check for `.demo-state.lock` — if present, another session may be running this chain;
abort and say so.

Create `.demo-state.lock`, then atomically write a fresh `.demo-state.md`:

```markdown
---
task: "scan project for TODOs and report on them"
started: 2026-07-12T14:00:00Z
status: in-progress
chain_version: 1
---
```

### Step 2 — Scan

Search the project for TODO and FIXME comments (e.g. `grep -rn "TODO\|FIXME" --include="*.py" .`
adapted to the project's languages). Collect file, line, and comment text.

### Step 3 — Update State

Atomically rewrite `.demo-state.md` with `status: phase-1-done` and the findings:

```markdown
---
task: "scan project for TODOs and report on them"
started: 2026-07-12T14:00:00Z
status: phase-1-done
chain_version: 1
---

## Phase 1 — Scan
**Output**: 12 TODO comments found across 5 files (list below)
**Key decisions**: skipped vendored code in vendor/ and node_modules/

| File | Line | Comment |
|---|---|---|
| src/auth.py | 42 | TODO: handle token refresh |
| src/api.py | 108 | FIXME: race condition on retry |
| ... | ... | ... |
```

Delete `.demo-state.lock`.

## Handoff

After completing this phase, output exactly:

> Phase 1 complete. State written to `.demo-state.md`.
> Run `/demo-plan` to begin Phase 2.

Do not start the next phase. Do not offer to continue. Output only the handoff line
and stop.
````

---

## File 2: `~/.claude/skills/demo-plan/SKILL.md`

````markdown
---
name: demo-plan
description: >
  Phase 2 of 3 in the demo chain. Reads the TODO scan results from the chain state
  file and prioritizes which items to address. Trigger when demo-scan says "run
  /demo-plan", or standalone via "demo-plan".
---

# Demo: Plan

Chain version: 1

Phase 2 of 3: scan → **plan** → report

## Overview

Turns the raw TODO list from phase 1 into a prioritized plan, marking each item
high / medium / low / won't-fix with a one-line reason.

## Workflow

### Step 1 — Load State

Read `.demo-state.md` from the project root:

- If missing → "No state file found. Run `demo-scan` first."
- If the frontmatter doesn't parse or is missing `status`/`chain_version` →
  "State file is malformed. Not proceeding."
- If `chain_version` is not `1` → "State file was written by an incompatible
  version of the demo chain."
- If `status` is not `phase-1-done` → "Expected status `phase-1-done` but found
  `<actual>`. Run the previous phase first."
- If the `## Phase 1 — Scan` section is missing despite the right status →
  "Status says phase-1-done but the Phase 1 section is missing. Treat as corrupted."
- Check/create `.demo-state.lock` as in phase 1.

### Step 2 — Prioritize

For each TODO in the Phase 1 table, assign a priority with a one-line rationale.
Group by priority.

### Step 3 — Update State

Atomically rewrite `.demo-state.md`: keep everything, append the Phase 2 section,
set `status: phase-2-done`:

```markdown
## Phase 2 — Plan
**Output**: 12 items prioritized — 3 high, 5 medium, 3 low, 1 won't-fix
**Key decisions**: the race condition in src/api.py:108 is the only blocker-class item
```

Delete `.demo-state.lock`.

## Handoff

After completing this phase, output exactly:

> Phase 2 complete. State written to `.demo-state.md`.
> Run `/demo-report` to begin Phase 3.

Do not start the next phase. Do not offer to continue. Output only the handoff line
and stop.
````

---

## File 3: `~/.claude/skills/demo-report/SKILL.md`

````markdown
---
name: demo-report
description: >
  Phase 3 of 3 (final) in the demo chain. Reads the scan and plan from the chain
  state file and writes TODO-REPORT.md in the project root. Trigger when demo-plan
  says "run /demo-report", or standalone via "demo-report".
---

# Demo: Report

Chain version: 1

Phase 3 of 3: scan → plan → **report**

## Overview

Produces the final deliverable: a human-readable `TODO-REPORT.md` summarizing what
was found and what the plan is.

## Workflow

### Step 1 — Load State

Same validation pattern as demo-plan, except:

- `status` must be `phase-2-done`
- both `## Phase 1 — Scan` and `## Phase 2 — Plan` sections must exist

### Step 2 — Write the Report

Generate `TODO-REPORT.md` in the project root from the state file's Phase 1 table
and Phase 2 priorities.

### Step 3 — Finalize State

Atomically rewrite `.demo-state.md`: append the Phase 3 section, set
`status: complete`:

```markdown
## Phase 3 — Report
**Output**: TODO-REPORT.md written (12 items, 3 high-priority)
**Key decisions**: none
```

Delete `.demo-state.lock`.

## Handoff

After completing, output exactly:

> Chain complete! All 3 phases finished. State written to `.demo-state.md`.
> The report is at `TODO-REPORT.md`. Run `demo-scan` again to start a new run.

Do not continue. Stop here.
````

---

## The state file across its lifetime

**After phase 1** — `status: phase-1-done`, has the Phase 1 section only.
**After phase 2** — `status: phase-2-done`, has Phase 1 + Phase 2 sections.
**After phase 3** — `status: complete`, has all three sections. Final form:

```markdown
---
task: "scan project for TODOs and report on them"
started: 2026-07-12T14:00:00Z
status: complete
chain_version: 1
---

## Phase 1 — Scan
**Output**: 12 TODO comments found across 5 files (list below)
**Key decisions**: skipped vendored code in vendor/ and node_modules/

| File | Line | Comment |
|---|---|---|
| src/auth.py | 42 | TODO: handle token refresh |
| src/api.py | 108 | FIXME: race condition on retry |

## Phase 2 — Plan
**Output**: 12 items prioritized — 3 high, 5 medium, 3 low, 1 won't-fix
**Key decisions**: the race condition in src/api.py:108 is the only blocker-class item

## Phase 3 — Report
**Output**: TODO-REPORT.md written (12 items, 3 high-priority)
**Key decisions**: none
```

## What makes this chain valid

Run `python3 validate-chain.py demo` and it passes because:

- `demo-scan` has no incoming handoff → it's the single entry point
- `demo-scan → demo-plan → demo-report` is a straight line, no cycles
- `demo-report` has no outgoing handoff but says "Chain complete" → intentional terminus
- all three reference the same state file, `.demo-state.md`
- all three declare `Chain version: 1`
