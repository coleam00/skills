#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
PostToolUse hook - the observer.

Fires AFTER every tool call. It cannot block (the tool already ran), so its job
is to *see*: append one line per event to logs/agent-actions.jsonl. The result is
a complete audit trail of exactly what the agent did - every command, every edit -
that you can read back, grep, or pipe into a dashboard.

    Pre = gate. Post = log.

Why JSONL and not JSON: the course version rewrote a single JSON array on every
tool call, which is O(n^2) writes and corrupts if two hooks fire at once. One
append-only line per event is cheap, concurrent-safe enough, and greppable:

    grep '"tool_name":"Bash"' logs/agent-actions.jsonl | tail -20
    python -c "import json,sys;[print(json.loads(l)['summary']) for l in open('logs/agent-actions.jsonl')]"

Fails OPEN: any error exits 0, so logging can never break your session.

MAKE IT YOURS: the common upgrades are auto-formatting a file the moment it is
edited, or notifying you on a specific tool. Both are PostToolUse. Change
`summarize()` if you want different fields, or set FULL_PAYLOAD = True to keep
everything.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# The one line most people edit.
LOG_PATH = Path("logs") / "agent-actions.jsonl"

# True keeps the entire hook payload per line (verbose, but complete).
FULL_PAYLOAD = False

# Long tool inputs are truncated to keep the log readable.
MAX_FIELD = 300


def _clip(value: object) -> object:
    text = str(value)
    return text if len(text) <= MAX_FIELD else text[:MAX_FIELD] + f"... [+{len(text) - MAX_FIELD} chars]"


def summarize(data: dict) -> dict:
    """One readable line per tool call: what ran, on what, and when."""
    tool_input = data.get("tool_input", {}) or {}
    tool_name = data.get("tool_name", "")

    # The field that actually says what happened differs per tool.
    target = (
        tool_input.get("command")
        or tool_input.get("file_path")
        or tool_input.get("pattern")
        or tool_input.get("url")
        or ""
    )

    return {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "session": data.get("session_id", ""),
        "tool_name": tool_name,
        "summary": _clip(target),
        "cwd": data.get("cwd", ""),
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)

        log_path = Path(data.get("cwd") or ".") / LOG_PATH
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = data if FULL_PAYLOAD else summarize(data)

        # Append one line. No read-modify-write, so concurrent tool calls do not
        # clobber each other and the file never needs re-parsing to grow.
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
