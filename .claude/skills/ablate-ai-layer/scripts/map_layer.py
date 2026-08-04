#!/usr/bin/env python3
"""Map a repository's AI layer. Read-only. Agent-agnostic.

Finds every instruction/context artifact any mainstream coding agent would load,
classifies each by WHEN it loads, and estimates what the always-loaded set costs
on every single session.

  always-loaded : enters context every session whether the task needs it or not
  on-demand     : costs nothing until invoked or until its path matches
  enforcement   : deterministic, executes as code, spends no attention budget

Usage:
  python map_layer.py [repo_root] [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALWAYS, ONDEMAND, ENFORCE = "always-loaded", "on-demand", "enforcement"

# (glob, agent, default classification, note)
PATTERNS: list[tuple[str, str, str, str]] = [
    # --- Claude Code
    ("CLAUDE.md",                        "Claude Code", ALWAYS,   "root project instructions"),
    ("CLAUDE.local.md",                  "Claude Code", ALWAYS,   "personal, gitignored"),
    (".claude/CLAUDE.md",                "Claude Code", ALWAYS,   "alt project instructions"),
    (".claude/rules/**/*.md",            "Claude Code", ALWAYS,   "path-scoped if it has paths: frontmatter"),
    (".claude/skills/*/SKILL.md",        "Claude Code", ONDEMAND, "loads when invoked or matched"),
    (".claude/agents/*.md",              "Claude Code", ONDEMAND, "loads only inside a subagent"),
    (".claude/commands/**/*.md",         "Claude Code", ONDEMAND, "loads when the command runs"),
    (".claude/settings.json",            "Claude Code", ENFORCE,  "hooks and permissions"),
    (".claude/settings.local.json",      "Claude Code", ENFORCE,  "hooks and permissions"),
    # --- open standard / Codex / Amp / Gemini CLI / Zed
    ("AGENTS.md",                        "AGENTS.md",   ALWAYS,   "open standard, read by most agents"),
    (".agents/skills/*/SKILL.md",        "Codex",       ONDEMAND, "filesystem-discovered skills"),
    (".agents/rules/**/*.md",            "AGENTS.md",   ALWAYS,   "proposed rules dir"),
    # --- Cursor
    (".cursorrules",                     "Cursor",      ALWAYS,   "legacy single-file rules"),
    (".cursor/rules/**/*.mdc",           "Cursor",      ALWAYS,   "alwaysApply decides; parsed below"),
    # --- Windsurf
    (".windsurfrules",                   "Windsurf",    ALWAYS,   "root rules file"),
    (".windsurf/rules/**/*.md",          "Windsurf",    ALWAYS,   "rules dir"),
    # --- Cline
    (".clinerules",                      "Cline",       ALWAYS,   "root rules file"),
    (".clinerules/**/*.md",              "Cline",       ALWAYS,   "rules dir"),
    # --- GitHub Copilot
    (".github/copilot-instructions.md",  "Copilot",     ALWAYS,   "repo-wide instructions"),
    (".github/instructions/**/*.md",     "Copilot",     ONDEMAND, "applyTo-scoped"),
    # --- Aider
    ("CONVENTIONS.md",                   "Aider",       ALWAYS,   "conventions file"),
    (".aider.conf.yml",                  "Aider",       ENFORCE,  "config"),
]

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build",
             "__pycache__", ".next", "target", ".ablation"}


def frontmatter(path: Path) -> dict:
    """Parse leading YAML frontmatter shallowly. No yaml dependency."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def classify(path: Path, default: str) -> tuple[str, str]:
    """Refine classification using the file's own frontmatter."""
    name = path.name
    # Key PRESENCE, not truthiness: a YAML list renders as an empty value here
    # ("paths:\n  - src/**") and would otherwise read as absent.
    if name.endswith(".mdc"):                       # Cursor
        fm = frontmatter(path)
        if str(fm.get("alwaysApply", "")).lower() == "true":
            return ALWAYS, "alwaysApply: true"
        if "globs" in fm:
            return ONDEMAND, "glob-scoped"
        return ONDEMAND, "manual / description-matched"
    if "/.claude/rules/" in path.as_posix():
        fm = frontmatter(path)
        if "paths" in fm:
            return ONDEMAND, "path-scoped rule"
        return ALWAYS, "unscoped rule, loads every session"
    return default, ""


def iter_matches(root: Path):
    seen = set()
    for pattern, agent, default, note in PATTERNS:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            rp = p.relative_to(root)
            if rp in seen:
                continue
            seen.add(rp)
            kind, why = classify(p, default)
            yield {
                "path": rp.as_posix(),
                "agent": agent,
                "kind": kind,
                "note": why or note,
                "bytes": p.stat().st_size,
                "lines": len(p.read_text(encoding="utf-8", errors="replace").splitlines()),
            }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()
    as_json = "--json" in sys.argv

    items = sorted(iter_matches(root), key=lambda d: (d["kind"], d["path"]))
    if as_json:
        print(json.dumps({"root": str(root), "artifacts": items}, indent=2))
        return 0

    if not items:
        print(f"No AI layer artifacts found under {root}")
        print("Nothing to ablate. This repo has no agent instructions committed.")
        return 0

    agents = sorted({i["agent"] for i in items})
    print(f"AI layer under {root}")
    print(f"Agents detected: {', '.join(agents)}\n")

    for kind, header in ((ALWAYS, "ALWAYS LOADED  (paid on every session)"),
                         (ONDEMAND, "ON DEMAND  (free until it fires)"),
                         (ENFORCE, "ENFORCEMENT  (deterministic, no attention cost)")):
        group = [i for i in items if i["kind"] == kind]
        if not group:
            continue
        print(f"  {header}")
        for i in group:
            print(f"    {i['lines']:>5} ln  {i['path']:<52} {i['note']}")
        print()

    always = [i for i in items if i["kind"] == ALWAYS]
    total_bytes = sum(i["bytes"] for i in always)
    total_lines = sum(i["lines"] for i in always)
    print(f"  Always-loaded total: {total_lines} lines, roughly {total_bytes // 4:,} tokens "
          f"on every session before you type anything.")
    print()
    print("  Ablate the always-loaded set. Leave the on-demand set alone: it costs")
    print("  nothing until it fires, so deleting it buys you no context back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
