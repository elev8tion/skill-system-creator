---
name: skill-system-creator
description: >
  Creates, extends, and audits skill chain systems for Claude Code. A skill chain is a
  sequence of skills that work together as phases of a larger workflow — each skill passes
  state to the next via a shared file on disk so the workflow survives across separate
  skill invocations (separate sessions, separate context windows). Use this when the user
  wants to design a new multi-skill workflow ("I want a chain that does A then B then C"),
  add a phase to an existing chain, fix broken YAML front matter in any skill, or validate
  that a chain's handoffs and state links are complete. This skill does NOT create general
  single-file skills — for that, just write a plain SKILL.md directly. Trigger phrases:
  "create a skill chain", "new chain system", "add a phase to *", "chain creator",
  "skill-system-creator", "build a skill system", "make a multi-step skill", "chain audit",
  "fix chain YAML", "audit my chains", "chain integrity", "validate the chain".
---

# Skill System Creator

Creates and manages **skill chain systems** — sequences of skills where each phase hands off
to the next, passing state through a shared file so the chain survives across separate skill
invocations.

This is NOT a general skill creator. It only handles multi-skill chains. For a single
standalone skill, just write `~/.claude/skills/<name>/SKILL.md` directly.

---

## What a Skill Chain Is

A skill chain is a group of skills where:

- **Each skill is one phase** of a larger workflow
- **State flows between phases** via a shared state file on disk
- **Each skill tells the user what to invoke next** using a standard handoff line
- **The chain can be invoked as a whole** (orchestrator) or **step-by-step** (pipeline)

### Two Chain Patterns

| Pattern | Best for | Example |
|---|---|---|
| **Orchestrator** — one master skill runs all phases in one session | Short workflows (< 7 steps), tight feedback loops, need for speed | a single skill with internal Phase 1..N sections |
| **Pipeline** — separate skills, each invoked independently | Long workflows, human review between phases, shared state across sessions | e.g. `myapp-scan` → `myapp-plan` → `myapp-implement` → `myapp-verify` |

### Anatomy of a Chain Skill

Every skill in a chain must have three things:

1. **Clean YAML front matter** — Claude Code must be able to parse it
2. **Phase identity** — what phase this is, what comes before/after
3. **Handoff instruction** — clear text telling the user/assistant what to invoke next

---

## YAML Front Matter Rules

These rules prevent the two errors that most commonly break skill front matter.

### Rule 1: Use `>` for long descriptions

```yaml
# ✅ GOOD — folded block scalar, no escaping issues
description: >
  Does X and Y. Use this when the user says Z. The text can contain
  "quotes", colons: fine, or any other characters because YAML does
  not try to parse a block scalar's content. It folds newlines into
  spaces so keep each line under 80 chars for readability.

# ❌ BAD — double-quoted with unescaped inner quotes
description: "Does X. Use when user says "this phrase" or "that phrase"."
#              ^ YAML sees this as the closing quote — everything after is garbage

# ❌ BAD — empty string with dangling continuation
description: ""
  This text is not valid YAML. The description is already closed by "".
```

A single-line double-quoted description (as seen in some existing skills, e.g. `graphify`)
is also fine as long as it contains no unescaped inner double quotes. Prefer `>` whenever
the description is long or might contain quotes/colons.

### Rule 2: Keep front matter minimal

```yaml
---
name: my-skill
description: >
  One paragraph that tells the assistant WHEN to trigger this skill. Include trigger
  phrases people would actually say. Be a little "pushy" — Claude under-triggers by
  default, so say "use this whenever..." even if the user doesn't explicitly name
  the skill.
---
```

Only `name` and `description` are required. Don't add extra front matter fields unless
the skill genuinely needs one (e.g. a `trigger:` line naming an explicit `/slash-command`
form, as seen in `graphify`).

### Rule 3: One skill = one file at `~/.claude/skills/<name>/SKILL.md`

No nested directories unless the skill also needs scripts or reference docs — and even
then, keep `SKILL.md` at the root of the skill's directory.

---

## Shared State Contract

Every chain must define ONE shared state file that all phases read and write. This is
what makes the chain survive across separate invocations and separate context windows.

### State file location

For a chain called `my-chain` targeting the user's project, put the state file at the
root of the project being worked on — never inside `~/.claude/skills/`:

```
.my-chain-state.md
```

### State file format

```markdown
task: "<original task description>"
started: <ISO 8601 timestamp>
status: phase-1-done | phase-2-done | complete

## Phase 1 — <name>
**Output**: <what this phase produced>
**Key decisions**: <anything the next phase needs to know>

## Phase 2 — <name>
...
```

### Rules

1. **Write the state file at the start of every phase** — before any work, so if the
   session is interrupted, the next invocation knows what was happening.
2. **Update `status` at the end of every phase** — this is how the next skill knows it
   can proceed.
3. **Every skill reads the state file first** — to confirm the previous phase completed.
4. **Do NOT rely on conversation context** — it can be lost between skill invocations
   or compacted away. The state file is the source of truth.
5. **Write atomically** — never edit the state file in place with a partial write. Write
   the full new contents to a temp file in the same directory, then rename it over the
   real state file:
   ```bash
   cat > .my-chain-state.md.tmp <<'EOF'
   <full new state file contents>
   EOF
   mv .my-chain-state.md.tmp .my-chain-state.md
   ```
   A rename is a single filesystem operation — if the phase is interrupted mid-write,
   the old (still-valid) state file survives untouched instead of being left half-written.
   Never `sed -i` or append-in-place edit the live state file.
6. **Validate the state file before trusting it** — a phase must not act on a state file
   it hasn't sanity-checked. Before doing any work:
   - Confirm the file parses (has a `status:` line, has at least the frontmatter-style
     key block at the top).
   - Confirm `status` is one of the values this chain's phases actually produce — not a
     typo, not a stale value from a chain that was since edited to use different status
     names.
   - Confirm required fields for the current phase are present (e.g., if phase 3 needs
     `## Phase 2 — <name>` output, that section must actually exist in the file).
   - If any check fails, abort with a specific error naming what was expected vs. what
     was found. Do NOT guess or proceed on a malformed state file — that silently
     corrupts every phase after it.

---

## Handoff Protocol

Every skill MUST end with a clear handoff. This is the text that tells the user (or the
assistant, in an unattended run) what to invoke next. Make it impossible to miss.

### End-of-skill handoff template

Place this at the very end of every SKILL.md, after the closing `---`:

```markdown
## Handoff

After completing this phase, output exactly:

> Phase N complete. State written to `.my-chain-state.md`.
> Run `/<chain-name>-<next-phase>` to begin Phase N+1.

Do not start the next phase. Do not offer to continue. Output only the handoff line
and stop.
```

The quoted block (`>`) is important — it stands out visually. The assistant reads it
and outputs it verbatim, so the user can copy or type it to trigger the next skill.

### For orchestrator-style chains

The master skill does NOT hand off — it runs everything internally. But it still updates
the state file after each internal phase so that if a crash happens, the chain can resume.

### Human-in-the-loop vs. autonomous continuation

The default handoff template assumes a **human is in the loop**: the assistant stops and
waits for the user to invoke the next skill. That's correct whenever the chain wants
review between phases (the whole point of choosing "pipeline" over "orchestrator").

Some chains, however, are meant to run unattended (e.g., invoked from a scheduled job, a
background agent, or another orchestrating skill with no human watching). For those,
say so explicitly in the phase's SKILL.md — don't leave it implicit:

```markdown
## Handoff

**This chain runs unattended.** After completing this phase, do NOT stop and wait.
Immediately proceed to invoke `<chain-name>-<next-phase>` in the same turn, then report
the combined result once the full chain (or the current unattended segment) completes.

Still update the state file exactly as in the human-in-the-loop case — an unattended
run can still be interrupted, and the state file is what lets a later invocation resume
correctly.
```

When generating a chain, ask the user which mode they want (or ask per-phase, if some
phases need review and others don't) — don't assume. Default to human-in-the-loop
(stop-and-wait) when unspecified, since that's the safer failure mode.

---

## Creating a New Chain

When the user asks you to create a new skill chain system, follow these steps:

### Step 1 — Capture Intent

Ask:
1. **What's the overall workflow?** (e.g., "scan a project, plan changes, implement them, verify")
2. **How many phases?** (2–7 is ideal. If > 7, suggest splitting into sub-chains.)
3. **Orchestrator or pipeline?** (see comparison table above)
4. **What state needs to flow between phases?** (e.g., a scan result, a plan, a diff)
5. **What should each phase be called?** (e.g., "scanner", "planner", "implementer", "verifier")

### Step 2 — Define the State File

Design the shared state format. What fields does each phase produce? What fields does
the next phase consume? Write this as a template before generating any skill files.

### Step 3 — Generate Each Skill File

For each phase, generate `~/.claude/skills/<chain-name>-<phase-name>/SKILL.md`.

Each file must follow this structure:

```markdown
---
name: <chain-name>-<phase-name>
description: >
  Phase N of N in the <chain-name> chain. <What this phase does, when to trigger it.>
  Include both standalone trigger phrases and chain-context triggers. Trigger:
  "<chain-name>-<phase-name>", "phase N of <chain-name>", or when the previous phase
  says "run <chain-name>-<phase-name> next".
---

# <Chain Name>: <Phase Display Name>

Phase N of N in the <chain-name> chain: <full chain map showing all phases>.

## Overview

<What this phase does, in 2–3 sentences.>

## Workflow

### Step 1 — Load State

Read `.my-chain-state.md` from the project root:

- If missing: abort with "No state file found. Run `<chain-name>` first."
- If the file doesn't parse (no `status:` line, malformed sections): abort with
  "State file is malformed — missing `<expected thing>`. Not proceeding on an
  unreadable state file."
- If `status` is not one of this chain's known status values at all (not just wrong
  for this phase — genuinely unrecognized): abort with "Unrecognized status
  `<actual-status>` — this state file may belong to a different or since-edited chain."
- If `status` is a known value but not the expected previous phase: abort with
  "Expected status `<previous-status>` but found `<actual-status>`. Run the previous
  phase first."
- If the previous phase's output section this phase depends on is missing even though
  `status` looks right: abort with "Status says `<previous-status>` but the
  `## Phase N-1` section is missing from the state file. Treat as corrupted."
- If all checks pass: proceed.

### Step N — <phase-specific steps>

...

### Step N+1 — Update State

Write the full new state file contents (existing sections plus this phase's output,
with `status` updated to `<this-phase-done>`) to a temp file and rename it over the
live state file — see **Rule 5 (atomic writes)** in the Shared State Contract. Never
append-in-place to the live file.

## Handoff

After completing this phase, output exactly:

> Phase N complete. State written to `.my-chain-state.md`.
> Run `/<chain-name>-<next-phase>` to begin Phase N+1.

Do not start the next phase. Do not offer to continue. Output only the handoff line
and stop.
```

### Step 4 — Verify the Chain

After generating all files, validate:

- [ ] Every SKILL.md has clean YAML (parse with `python3 -c "import yaml; yaml.safe_load(open('SKILL.md').read().split('---')[1])"`)
- [ ] Phase 1 skill has NO "previous phase" check
- [ ] Last phase skill has NO handoff (it says "Chain complete")
- [ ] Every intermediate phase has a handoff to the next
- [ ] Handoff names match the actual skill directory names exactly
- [ ] All skills reference the same state file path
- [ ] All `status` values form a sequence (phase-1-done → phase-2-done → complete)

---

## Adding a Phase to an Existing Chain

1. Read all existing skill files in the chain
2. Find the insertion point (between existing phases or at the end)
3. Update the previous phase's handoff to point to the new phase
4. Generate the new phase skill file with:
   - Handoff to the next phase (or "Chain complete" if it's the last)
   - State file reads that check for the previous phase's status
   - State file update that writes its own status
5. Verify the chain integrity (same checklist as Step 4 above)

---

## Listing Existing Chains

Run this when the user says "what chains do I have", "list my chains", or similar —
a quick inventory, distinct from the full **Chain Integrity Audit** below (no YAML
parsing, no gap analysis, no report).

```bash
ls ~/.claude/skills/ | sed -E 's/-[^-]+$//' | sort | uniq -c | sort -rn
```

This groups skill directory names by shared prefix and counts members. Anything with
count ≥ 2 is a likely chain. Present it as a flat list:

```markdown
## Chains found

- `myapp-*` — 4 skills (scan, plan, implement, verify)
- `otherchain-*` — 2 skills (fetch, summarize)
```

Note: prefix-grouping is a heuristic — a skill named `myapp-helper` that isn't
actually part of the `myapp` chain will show up here too. If precision matters, tell
the user to run the full audit instead.

---

## Chain Integrity Audit

Run this when the user says "audit my chains" or "validate the chain".

### Step 1 — Scan All Skills

```bash
ls ~/.claude/skills/*/SKILL.md
```

### Step 2 — Check YAML on Every File

```bash
python3 -c "
import os, yaml, glob
errors = []
for f in glob.glob(os.path.expanduser('~/.claude/skills/*/SKILL.md')):
    try:
        content = open(f).read()
        parts = content.split('---')
        if len(parts) >= 3:
            yaml.safe_load(parts[1])
    except Exception as e:
        errors.append((f, str(e)))
for f, e in errors:
    print(f'{f}: {e}')
"
```

Report every file with broken YAML and the specific error.

### Step 3 — Detect Chains

Group skills by name prefix (e.g., all `myapp-*` skills form one chain). For each group:

1. **List chain members**: collect all skill names sharing the prefix
2. **Read each SKILL.md**: extract:
   - Does it reference a state file? Which one?
   - Does it have a handoff section? What skill does it name next?
   - Does it check for a previous phase?
3. **Build the chain map**: phase-1 → skill-A, phase-2 → skill-B, etc.
4. **Check for gaps**:
   - Every handoff target must be a real skill in the group
   - Every skill that checks for a previous phase must have a predecessor that produces it
   - All skills in the group must reference the same state file
   - The status values in the chain must form a logical sequence
5. **Check for cycles**: walk the handoff graph starting from the phase with no
   "previous phase" check (the entry point). If following handoff targets ever revisits
   a skill already on the current path, that's a cycle — flag it by name (e.g.
   `scanner → planner → scanner`). A chain is meant to be a straight line (or an
   explicit, intentionally-documented branch); an accidental cycle means someone edited
   a handoff and pointed it backward.
6. **Check for dead ends / orphans**:
   - **Dead end**: an intermediate skill (one that other skills hand off to) whose own
     handoff section is missing entirely, or that has no handoff and doesn't read like
     an intentional chain terminus ("Chain complete"). The chain silently stops there
     with no path forward.
   - **Orphan**: a skill whose directory name shares the group's prefix but that no
     other skill in the group hands off to, AND that isn't the phase-1 entry point.
     It's dead code sitting in the chain's namespace — either it belongs to a different
     chain that happens to share a prefix, or a handoff to it was deleted.
   - **Unreachable branch**: more than one skill in the group has no incoming handoff
     and isn't clearly the entry point — suggests two disconnected fragments living
     under one prefix.

### Step 4 — Report

```markdown
## Chain Audit: <chain-name>

### Chain Map
| Phase | Skill | State Check | Handoff To | Status |
|---|---|---|---|---|
| 1 | scanner | none | planner | ✓ |
| 2 | planner | checks phase-1-done | implementer | ✓ |
| 3 | verifier | checks phase-2-done | (none — chain end) | ✓ |

### Issues Found
- (none) / [list of broken handoffs, missing skills, YAML errors, state mismatches,
  cycles, dead ends, orphans]

### Fix Instructions
- [specific action to fix each issue]
```

### Step 5 — Fix Mode

If the user says "fix it", apply the fixes:
1. Fix any broken YAML front matter
2. Fix mismatched handoff names
3. Fix state file path inconsistencies
4. Add missing state checks or handoffs
5. Re-run the YAML validation to confirm

---

## YAML Fixer Mode

When the user says "fix the YAML in my skills" or points to a specific broken file,
use this procedure.

### For "Unexpected scalar at node end" errors

This happens when a double-quoted `description` contains unescaped `"` characters.

**Fix:** Convert to a folded block scalar (`>`):

```yaml
# Broken:
description: "This has "quotes" inside that break YAML."

# Fixed:
description: >
  This has "quotes" inside that no longer break YAML because
  block scalars don't parse content.
```

### For "All mapping items must start at the same column" errors

This happens when `description: ""` leaves an empty value and the next line has
indented content that YAML can't place.

**Fix:** Move the actual description text into a block scalar:

```yaml
# Broken:
description: ""
  This is the actual text but it's dangling after an empty string.

# Fixed:
description: >
  This is the actual text now properly attached to the description
  field via a block scalar indicator.
```

### For "mapping values are not allowed here" errors

This happens when a colon in the description text (e.g., `Trigger: "do thing"`)
is unquoted.

**Fix:** Same as above — use a block scalar. The `>` indicator prevents YAML from
parsing colons inside the value.

### Procedure

1. Read the broken file
2. Extract the intended description text
3. Rewrite the front matter with `description: >` followed by the text indented
   by 2 spaces on subsequent lines
4. Validate with:
   ```bash
   python3 -c "
   import yaml
   content = open('SKILL.md').read()
   yaml.safe_load(content.split('---')[1])
   print('YAML OK')
   "
   ```
5. Report what was fixed

---

## Templates

### Pipeline Chain — Phase N Skill (intermediate)

```markdown
---
name: <chain-name>-<phase-name>
description: >
  Phase N of N in the <chain-name> chain. <One-sentence description of what this
  phase does.> Trigger when the previous phase says "run <chain-name>-<phase-name>
  next", or standalone via "<chain-name>-<phase-name>".
---

# <Chain-Name>: <Phase Display Name>

Phase N of N: <prev-phase> → **<this-phase>** → <next-phase>

## Load State

Read `.my-chain-state.md`:

- If missing → "No state file. Run `<chain-name>` first."
- If status is not `<expected-status>` → "Expected `<expected-status>`, got `<actual>`.
  Run the previous phase first."
- Otherwise proceed.

## Workflow

<Phase-specific instructions — reading files, running commands, generating output.>

## Update State

Append to `.my-chain-state.md`:

```markdown
## Phase N — <Phase Display Name>
**Output**: <summary of what this phase produced>
**Key decisions**: <anything next phase must know>
```

Update `status: <done-status>`.

## Handoff

After completing, output exactly:

> Phase N complete. State written to `.my-chain-state.md`.
> Run `/<chain-name>-<next-phase>` to begin Phase N+1.

Do not start the next phase. Stop here.
```

### Pipeline Chain — Last Phase Skill

Same as above, but replace handoff with:

```markdown
## Handoff

After completing, output exactly:

> Chain complete! All N phases finished. State written to `.my-chain-state.md`.
> Run `<chain-name>` again to start a new session.

Do not continue. Stop here.
```

### Orchestrator Chain — Master Skill

For chains where one skill runs everything internally:

```markdown
---
name: <chain-name>
description: >
  Fully autonomous <chain-name> orchestrator. Runs all N phases in sequence without
  handoffs: <phase-1> → <phase-2> → <phase-3>. <One-sentence summary.> Trigger: "<chain-name>",
  "<chain-name> <task>", or any request that matches the chain's purpose. Use proactively
  when the user describes a workflow that maps to this chain.
---

# <Chain-Name>: <Display Name>

Fully autonomous. Runs all N phases in sequence without handoffs.

```
/<chain-name> "<task>"
  ↓ Phase 1: <name>     (<description>)
  ↓ Phase 2: <name>     (<description>)
  ↓ Phase N: <name>     (<description>)
```

## State File

Read and write `.my-chain-state.md` at the project root. Update `status` after each
internal phase so the chain can resume if interrupted.

## Phase 1 — <name>
...
## Phase 2 — <name>
...
## Phase N — <name>
...

## If Invoked Without a Task

- State file exists, `status: complete` → Show last run summary
- State file exists, `status: <partial>` → Resume from the incomplete phase
- No state file, no task → "Provide a task: `/<chain-name> \"your task\"`"
```

---

## Design Principles

1. **State file over context** — never rely on conversation history surviving between
   skill invocations. The state file is the source of truth.
2. **Validate before proceeding** — every phase must check that the previous phase
   completed before doing any work. This prevents double-work and cascading failures.
3. **Explicit handoffs only** — every skill ends with `> Run /<next-skill>` in a quoted
   block. No "you can continue" or "would you like to". Just the handoff.
4. **One state file per chain** — a single `.md` file that all phases append to. Never
   multiple state files for one chain.
5. **Clean YAML first** — if the front matter is broken, the skill is invisible. Use
   `>` for descriptions, never double-quoted strings with inner quotes.
6. **Orchestrator for speed, pipeline for safety** — if you need human review between
   phases, use pipeline. If the chain is short and deterministic, use orchestrator.
7. **Phase names must be unique** — `myapp-scan`, `myapp-plan` — not `myapp`, `myapp-2`.
   The name prefix is the chain identifier.
8. **Chain end must be explicit** — the last skill says "Chain complete." and does not
   hand off. This gives the user a clear stopping point.
