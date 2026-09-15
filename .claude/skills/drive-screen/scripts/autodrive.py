#!/usr/bin/env python3
"""Observe one Claude Code turn and optionally capture its quiet window.

This legacy-named helper never sends keystrokes or approves requests. It shares
session_watch's conservative completion detection and pins one transcript for
the whole wait. It cannot read Codex sessions. A quiet transcript is ambiguous;
a screenshot is evidence to inspect, never authority to approve anything.

Exit codes: 0 new completion marker; 1 missing/unreadable input or timeout;
2 screenshot/argument failure; 3 quiet state needs inspection. --approve-blind
is retained only to fail explicitly, before touching a session or window.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session_watch as sw  # noqa: E402


def screenctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HERE / "screenctl.py"), *args],
                          capture_output=True, text=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--title", help="window holding the driven session")
    target.add_argument("--id", help="window handle from screenctl list")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--session", help="unique Claude session UUID or prefix")
    ap.add_argument("--since", type=int, default=None, help="baseline record index from mark")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--idle", type=float, default=45)
    ap.add_argument("--poll", type=float, default=3)
    ap.add_argument("--shot-dir", help="retain a fresh screenshot in this directory")
    ap.add_argument("--dry-run", action="store_true", help="observe transcript without capture")
    ap.add_argument("--approve-blind", action="store_true", help="removed; fails without sending input")
    ap.add_argument("--max", type=int, help="legacy compatibility option; no approvals are sent")
    a = ap.parse_args(argv)
    if any(not math.isfinite(v) or v <= 0 for v in (a.timeout, a.idle, a.poll)) or (a.since is not None and a.since < 0):
        ap.error("--timeout, --idle, and --poll must be finite positive numbers")
    if a.approve_blind:
        print("APPROVAL_DISABLED: --approve-blind is unsupported. No session or window was accessed.")
        return 2
    print("Observation-only mode: no keystrokes are sent.")
    sw.PIN = a.session
    try:
        result = sw.cmd_wait(a)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1
    if result != 2:
        return result
    if a.dry_run:
        print("UNVERIFIED: inspect the current UI; --dry-run did not capture it.")
        return 3
    # Unique paths cannot accidentally reuse evidence from an earlier run. The
    # default lives in a tool-owned temp directory, never in the skill source.
    try:
        directory = Path(a.shot_dir) if a.shot_dir else Path(tempfile.mkdtemp(prefix="drive-screen-"))
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="quiet-", suffix=".png", dir=directory)
        os.close(fd)
        shot = Path(name)
        target_args = ["--id", a.id] if a.id else ["--title", a.title]
        capture = screenctl("shot", *target_args, "--out", str(shot))
        if capture.returncode or not shot.is_file() or shot.stat().st_size == 0:
            shot.unlink(missing_ok=True)
            print("SCREENSHOT_FAILED: " + ((capture.stdout + capture.stderr).strip()[:300] or "no image"))
            return 2
    except OSError as exc:
        print(f"SCREENSHOT_FAILED: {exc}")
        return 2
    print(f"Screenshot: {shot.resolve()}")
    print("Inspect the current UI and any actual request before taking a separate action.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
