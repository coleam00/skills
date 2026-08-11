#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
PreToolUse hook - the coupling guard.

The problem: some files in every codebase are silently coupled. Edit the API
route without reading the schema and you ship a contract mismatch. Edit the
model without reading the migration and you ship a broken deploy. The agent
cannot know which is which - the coupling lives in your head, or in a rule it
skims past on turn forty.

This hook makes it structural. You declare the coupling once in
`.claude/hooks/dependencies.json`, and the agent cannot edit a file until it has
actually read that file's dependencies in this session.

How it works: the same hook fires on Read and on the edit tools.
  - On Read  -> remember that path for this session.
  - On Edit  -> look up what this file depends on. Anything not yet read is
                either injected as context or blocked, depending on MODE.

    MODE = "block"   the edit is refused, the agent is told what to read first
    MODE = "context" the edit proceeds, with the dependency contents injected

"block" is the guarantee and the better demo. "context" is usually the nicer
daily driver: no wasted turn, the contract just arrives at the moment it is
needed. Pick per project.

Fails OPEN: no config, unreadable config, or any error -> allow.

============================================================================
EDIT THESE
============================================================================
"""

MODE = "block"  # "block" | "context"

# Where the coupling map lives, relative to the project root.
CONFIG_PATH = ".claude/hooks/dependencies.json"

# In "context" mode, how much of each dependency to inject.
MAX_INJECT_CHARS = 2000

# ============================================================================

import fnmatch
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
READ_TOOLS = ("Read",)


def _state_path(session_id: str) -> Path:
    """Per-session scratch. Under the OS temp dir on purpose, so it never lands
    in the repo and never needs a .gitignore entry."""
    digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:16]
    directory = Path(tempfile.gettempdir()) / "claude-hook-deps"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{digest}.json"


def _load_seen(session_id: str) -> set:
    try:
        return set(json.loads(_state_path(session_id).read_text(encoding="utf-8")))
    except Exception:
        return set()


def _remember(session_id: str, relative: str) -> None:
    try:
        seen = _load_seen(session_id)
        seen.add(relative)
        _state_path(session_id).write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except Exception:
        pass  # forgetting is harmless; it only costs a redundant read


def _relative(root: Path, raw: str) -> str:
    """Project-relative, forward-slashed, so config globs are portable."""
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(raw).replace("\\", "/")


def _load_config(root: Path) -> dict:
    try:
        raw = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
        # Accept either {"globs": {...}} or a bare mapping.
        return raw.get("globs", raw) if isinstance(raw, dict) else {}
    except Exception:
        return {}


def required_for(config: dict, relative: str) -> list:
    """Every declared dependency whose glob matches this file, de-duplicated."""
    required = []
    for pattern, deps in config.items():
        if not isinstance(deps, list):
            continue
        if fnmatch.fnmatch(relative, pattern):
            for dep in deps:
                if dep not in required and dep != relative:
                    required.append(dep)
    return required


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {}) or {}
        session_id = data.get("session_id", "") or "unknown"
        root = Path(data.get("cwd") or ".")

        raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not raw_path:
            sys.exit(0)

        relative = _relative(root, raw_path)

        # Reading anything counts as having seen it.
        if tool_name in READ_TOOLS:
            _remember(session_id, relative)
            sys.exit(0)

        if tool_name not in EDIT_TOOLS:
            sys.exit(0)

        config = _load_config(root)
        if not config:
            sys.exit(0)  # nothing declared, nothing to enforce

        missing = [dep for dep in required_for(config, relative) if dep not in _load_seen(session_id)]
        if not missing:
            sys.exit(0)

        # Only enforce dependencies that actually exist on disk. A stale entry in
        # the config should not be able to deadlock an edit.
        missing = [dep for dep in missing if (root / dep).is_file()]
        if not missing:
            sys.exit(0)

        if MODE == "context":
            blocks = []
            for dep in missing:
                body = (root / dep).read_text(encoding="utf-8", errors="replace")
                if len(body) > MAX_INJECT_CHARS:
                    body = body[:MAX_INJECT_CHARS] + "\n... [truncated]"
                blocks.append(f"--- {dep} ---\n{body}")
                _remember(session_id, dep)  # injected counts as delivered

            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        f"`{relative}` is coupled to the following file(s). "
                        "Their current contents:\n\n" + "\n\n".join(blocks)
                    ),
                }
            }))
            sys.exit(0)

        # MODE == "block"
        listing = "\n".join(f"  - {dep}" for dep in missing)
        print(
            f"BLOCKED: `{relative}` is coupled to file(s) you have not read this session.\n"
            f"{listing}\n\n"
            "Read them first, then make this edit. They define the contract this "
            "file has to satisfy, and editing blind is how the two drift apart.",
            file=sys.stderr,
        )
        sys.exit(2)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
