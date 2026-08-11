#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
SessionStart hook - the context you would otherwise paste every morning.

Fires when a session starts, resumes, or is cleared. It cannot block. Its job is
to inject the state that is TRUE RIGHT NOW and therefore does not belong in
CLAUDE.md: what branch you are on, what you changed since main, what you were
doing yesterday.

This is the distinction that makes it worth having. Your rules file holds what is
always true (conventions, architecture, house style). This hook holds what is
true today. Putting today's state in CLAUDE.md is how a rules file rots.

    exit 0, and print JSON with additionalContext INSIDE hookSpecificOutput.

That nesting is the single most common mistake with this hook. Put
`additionalContext` at the top level and Claude Code silently ignores it - no
error, no warning, it just does not arrive.

Fails OPEN and silent: if anything goes wrong we exit 0 with no context rather
than break session start.

============================================================================
EDIT THESE
============================================================================
"""

# Files whose contents get injected verbatim, if they exist. Relative to the
# project root. This is where a working-notes or current-sprint file goes.
CONTEXT_FILES = [
    "NOTES.md",
    ".claude/context/current.md",
]

# Include live git state (branch, uncommitted files, recent commits).
INCLUDE_GIT = True

# Claude Code caps injected context at 10,000 characters. Stay well under it -
# this text is prepended to EVERY session, so it is the most expensive context
# you own. If you need more than this, you want a skill, not a hook.
MAX_CHARS = 4000

# ============================================================================

import json
import subprocess
import sys
from pathlib import Path


def _git(args, cwd) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def git_context(root: Path) -> str:
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if not branch:
        return ""  # not a git repo, or git is unavailable

    parts = [f"Branch: {branch}"]

    dirty = _git(["status", "--porcelain"], root)
    if dirty:
        files = [line[3:] for line in dirty.splitlines()[:15]]
        parts.append("Uncommitted changes:\n" + "\n".join(f"  {f}" for f in files))
    else:
        parts.append("Working tree is clean.")

    log = _git(["log", "--oneline", "-5"], root)
    if log:
        parts.append("Recent commits:\n" + "\n".join(f"  {line}" for line in log.splitlines()))

    return "\n\n".join(parts)


def file_context(root: Path) -> str:
    blocks = []
    for relative in CONTEXT_FILES:
        path = root / relative
        try:
            if path.is_file():
                body = path.read_text(encoding="utf-8", errors="replace").strip()
                if body:
                    blocks.append(f"--- {relative} ---\n{body}")
        except Exception:
            continue
    return "\n\n".join(blocks)


def main() -> None:
    try:
        data = json.load(sys.stdin)
        root = Path(data.get("cwd") or ".")

        sections = []
        if INCLUDE_GIT:
            git = git_context(root)
            if git:
                sections.append(git)

        files = file_context(root)
        if files:
            sections.append(files)

        if not sections:
            sys.exit(0)  # nothing to say; do not inject an empty block

        context = "# Session context (injected automatically)\n\n" + "\n\n".join(sections)
        if len(context) > MAX_CHARS:
            context = context[:MAX_CHARS] + "\n... [truncated]"

        # additionalContext MUST be nested inside hookSpecificOutput.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }))
        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
