# skill-system-creator

A [Claude Code](https://code.claude.com) skill that creates, extends, and audits
**skill chain systems** — sequences of skills that work together as phases of a larger
workflow, passing state between phases through a shared file on disk so the workflow
survives across separate sessions and context windows.

## What it does

- **Create chains** — design a multi-skill workflow ("scan → plan → implement → verify")
  and generate every phase's SKILL.md with correct state handling and handoffs
- **Audit chains** — walk the handoff graph to find broken handoffs, cycles, dead ends,
  orphaned skills, and mismatched state files
- **Fix YAML** — diagnose and repair the front matter errors that make skills invisible
  to Claude Code
- **List / extend / retire chains** — inventory existing chains, insert new phases,
  or cleanly delete a chain

## Install

```bash
git clone https://github.com/elev8tion/skill-system-creator.git ~/.claude/skills/skill-system-creator
```

Claude Code picks it up automatically. Trigger it with phrases like
"create a skill chain", "audit my chains", or "fix chain YAML".

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | The skill itself — rules, templates, and procedures |
| `EXAMPLE.md` | A complete worked 3-phase example chain (`demo-scan → demo-plan → demo-report`) |
| `validate-chain.py` | Standalone validator — YAML checks, handoff-graph walk, cycle/orphan/dead-end detection |

## Validator usage

```bash
python3 validate-chain.py                  # full audit of every chain
python3 validate-chain.py <chain-name>     # audit one chain
python3 validate-chain.py --list           # list detected chains
python3 validate-chain.py --yaml-only      # front matter validation only
python3 validate-chain.py --skills-dir D   # scan a different skills directory
```

Requires Python 3. PyYAML is optional (falls back to regex sanity checks without it).

## Key concepts

- **Pipeline vs. orchestrator** — separate skills invoked step-by-step (human review
  between phases) vs. one master skill running all phases in a session
- **Shared state contract** — one `.<chain-name>-state.md` per chain, YAML frontmatter
  header (`task`, `started`, `status`, `chain_version`), atomic temp-file+rename writes,
  advisory lock file, validated before every phase trusts it
- **Handoff protocol** — every phase ends with an unmissable quoted handoff line naming
  the next skill; the last phase terminates explicitly with "Chain complete"
