#!/usr/bin/env python3
"""Validate Claude Code skill chains.

A skill chain is a group of skills under ~/.claude/skills/ where each phase's
SKILL.md hands off to the next via a line like:

    > Run `/<chain-name>-<next-phase>` to begin Phase N+1.

This script:
  - validates YAML front matter on every SKILL.md (PyYAML if available,
    regex sanity-check fallback otherwise)
  - builds the handoff graph from actual "Run `/...`" handoff lines
  - detects chains as connected components of that graph (not name guessing)
  - flags cycles, dead ends, orphans, and mixed state-file references

Usage:
  validate-chain.py                 # full audit of every chain found
  validate-chain.py <chain-name>    # audit only chains whose members match the prefix
  validate-chain.py --list          # just list detected chains
  validate-chain.py --yaml-only     # only the YAML front matter pass
  validate-chain.py --skills-dir D  # scan D instead of ~/.claude/skills

Exit code 0 = no issues, 1 = issues found, 2 = usage/environment error.
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

HANDOFF_RE = re.compile(r"(?:Run|invoke)\s+`/?([a-z0-9][a-z0-9_-]*)`", re.IGNORECASE)
STATE_FILE_RE = re.compile(r"`(\.[a-z0-9][a-z0-9_-]*-state\.md)`")
CHAIN_COMPLETE_RE = re.compile(r"chain complete", re.IGNORECASE)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillInfo:
    def __init__(self, name, path, body):
        self.name = name
        self.path = path
        self.body = body
        self.yaml_error = None
        self.handoffs = []       # skill names this skill hands off to
        self.state_files = []    # state file paths referenced
        self.is_terminus = False


def check_frontmatter(text, path):
    """Return an error string or None."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "no YAML front matter block found at top of file"
    block = m.group(1)
    if HAVE_YAML:
        try:
            data = yaml.safe_load(block)
        except Exception as e:  # yaml errors vary by type
            return f"YAML parse error: {e}"
        if not isinstance(data, dict):
            return "front matter is not a mapping"
        for key in ("name", "description"):
            if key not in data:
                return f"missing required key: {key}"
        return None
    # Fallback: crude sanity checks only.
    if not re.search(r"^name:\s*\S", block, re.MULTILINE):
        return "missing name: line (regex fallback — install PyYAML for real parsing)"
    if not re.search(r"^description:", block, re.MULTILINE):
        return "missing description: line (regex fallback)"
    for line in block.splitlines():
        if line.count('"') % 2 == 1:
            return f"unbalanced quotes on line: {line.strip()!r} (regex fallback)"
    return None


def load_skills(skills_dir):
    skills = {}
    for skill_md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        name = skill_md.parent.name
        try:
            body = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"  ERROR reading {skill_md}: {e}")
            continue
        info = SkillInfo(name, skill_md, body)
        info.yaml_error = check_frontmatter(body, skill_md)
        info.handoffs = [t for t in HANDOFF_RE.findall(body) if t != name]
        info.state_files = sorted(set(STATE_FILE_RE.findall(body)))
        info.is_terminus = bool(CHAIN_COMPLETE_RE.search(body))
        skills[name] = info
    return skills


def connected_components(skills):
    """Weakly-connected components of the handoff graph, size >= 2."""
    adj = {}
    for s in skills.values():
        for t in s.handoffs:
            if t in skills:
                adj.setdefault(s.name, set()).add(t)
                adj.setdefault(t, set()).add(s.name)
    seen, components = set(), []
    for node in adj:
        if node in seen:
            continue
        comp, stack = set(), [node]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj.get(n, ()))
        if len(comp) >= 2:
            components.append(sorted(comp))
    return components


def common_prefix(names):
    prefix = os.path.commonprefix(names)
    # Trim to the last hyphen so the prefix is a whole name segment.
    if "-" in prefix and not all(n == prefix for n in names):
        prefix = prefix[: prefix.rfind("-") + 1]
    return prefix


def find_cycles(members, skills):
    """DFS for cycles within the directed handoff graph of one chain."""
    cycles = []
    member_set = set(members)

    def dfs(node, path):
        for t in skills[node].handoffs:
            if t not in member_set:
                continue
            if t in path:
                cycles.append(path[path.index(t):] + [t])
                continue
            dfs(t, path + [t])

    for m in members:
        dfs(m, [m])
    # Dedup by the set of nodes in the cycle.
    unique, seen_keys = [], set()
    for c in cycles:
        key = frozenset(c)
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(c)
    return unique


def audit_chain(members, skills, all_names):
    issues = []
    member_set = set(members)
    incoming = {m: 0 for m in members}
    for m in members:
        for t in skills[m].handoffs:
            if t in incoming:
                incoming[t] += 1
            elif t not in all_names:
                issues.append(f"{m}: hands off to `{t}` which is not an existing skill")

    entries = [m for m in members if incoming[m] == 0]
    if len(entries) == 0:
        issues.append("no entry point — every member has an incoming handoff (cycle?)")
    elif len(entries) > 1:
        issues.append(
            "multiple skills have no incoming handoff (disconnected fragments?): "
            + ", ".join(entries)
        )

    for cyc in find_cycles(members, skills):
        issues.append("cycle in handoff graph: " + " -> ".join(cyc))

    for m in members:
        outgoing = [t for t in skills[m].handoffs if t in member_set]
        if not outgoing and not skills[m].is_terminus:
            issues.append(
                f"{m}: dead end — no handoff and no 'Chain complete' terminus text"
            )

    prefix = common_prefix(members)
    if prefix:
        for name in sorted(all_names):
            if name.startswith(prefix) and name not in member_set:
                issues.append(
                    f"possible orphan: `{name}` shares prefix `{prefix}` but nothing "
                    "in the chain hands off to it"
                )

    state_refs = {}
    for m in members:
        for sf in skills[m].state_files:
            state_refs.setdefault(sf, []).append(m)
    if len(state_refs) > 1:
        issues.append(
            "members reference different state files: "
            + "; ".join(f"{sf} ({', '.join(ms)})" for sf, ms in sorted(state_refs.items()))
        )
    return entries, issues


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("chain", nargs="?", help="only audit chains matching this name/prefix")
    ap.add_argument("--list", action="store_true", help="just list detected chains")
    ap.add_argument("--yaml-only", action="store_true", help="only run the YAML pass")
    ap.add_argument("--skills-dir", default=os.path.expanduser("~/.claude/skills"))
    args = ap.parse_args()

    if not os.path.isdir(args.skills_dir):
        print(f"skills dir not found: {args.skills_dir}")
        return 2

    if not HAVE_YAML:
        print("note: PyYAML not installed — using regex sanity checks only "
              "(pip3 install pyyaml for full validation)\n")

    skills = load_skills(args.skills_dir)
    problems = 0

    yaml_bad = [(s.name, s.yaml_error) for s in skills.values() if s.yaml_error]
    if yaml_bad:
        print("== YAML front matter issues ==")
        for name, err in yaml_bad:
            print(f"  {name}: {err}")
            problems += 1
        print()
    elif args.yaml_only:
        print("All SKILL.md front matter OK.")
    if args.yaml_only:
        return 1 if problems else 0

    components = connected_components(skills)
    if args.chain:
        components = [c for c in components
                      if any(m == args.chain or m.startswith(args.chain + "-") for m in c)]
        if not components:
            print(f"no chain found matching '{args.chain}'")
            return 2

    if not components:
        print("No chains detected (no skill hands off to another skill).")
        return 1 if problems else 0

    for members in components:
        prefix = common_prefix(members) or "(no common prefix)"
        entries, issues = audit_chain(members, skills, set(skills))
        if args.list:
            entry = entries[0] if len(entries) == 1 else "?"
            print(f"{prefix.rstrip('-')}: {len(members)} skills, entry: {entry}")
            print("   members: " + ", ".join(members))
            continue
        print(f"== Chain: {prefix.rstrip('-')} ({len(members)} skills) ==")
        print("  members: " + ", ".join(members))
        print("  entry point(s): " + (", ".join(entries) or "(none)"))
        if issues:
            for i in issues:
                print(f"  ISSUE: {i}")
                problems += 1
        else:
            print("  OK — no issues")
        print()

    if not args.list:
        print(f"{problems} issue(s) found." if problems else "All chains OK.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
