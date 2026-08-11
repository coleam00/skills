#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Stop hook - the feedback loop you cannot forget to run.

Fires when the agent tries to finish its turn. It runs your test command. If the
tests fail, it BLOCKS the stop and hands the failure output back to the agent,
which goes straight back to work. The agent literally cannot say "done" on red.

This is the single highest-value hook most projects can add. A rule that says
"always run the tests before you finish" is guidance, and the agent skips it the
moment the context gets long. This is the same instruction as a guarantee.

    exit 0 -> let it finish     exit 2 -> block the stop, stderr goes to the agent

Fails OPEN on anything unexpected, so a broken hook never traps you in a loop.

============================================================================
EDIT THIS ONE LINE
============================================================================
"""

TEST_COMMAND = "python -m pytest -q"

# If your tests must run from a subdirectory (monorepo, or config that lives
# deeper like app/backend/), set it here. Relative to the project root.
TEST_SUBDIR = ""

# Seconds before we give up and let the agent finish anyway. A hook that hangs
# is worse than a hook that misses.
TIMEOUT_SECONDS = 300

# How much of the failure output to hand back. Enough to act on, not enough to
# blow out the context window.
MAX_OUTPUT_CHARS = 3000

# ============================================================================

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_env(project_root: Path) -> dict:
    """os.environ with uv's ephemeral venv removed and the PROJECT's venv put first.

    THIS IS THE PART EVERYONE GETS WRONG, and it fails in a way that looks like
    it works. This hook runs under `uv run` in an isolated throwaway environment.
    That interpreter is NOT your project's interpreter and has none of your
    project's dependencies.

    Two things have to happen, and most write-ups only mention the first:

      1. Drop uv's throwaway venv. If you rebuild the command with
         sys.executable, or leave uv's venv first on PATH, `python -m pytest`
         runs in an environment with no pytest at all.

      2. Put the project's OWN venv first. Removing uv's venv does not activate
         yours - a hook is not your shell, so `.venv` was never on PATH. Without
         this step `python` falls through to whatever global interpreter the
         machine has, which is a different, usually broken, set of packages.

    Skip step 2 and the hook exits 2 on a perfectly green suite, with an error
    about some unrelated module. Verified: that is exactly what happens.
    """
    env = os.environ.copy()

    # 1. uv's ephemeral venv, out.
    ephemeral = env.pop("VIRTUAL_ENV", None)
    path_parts = env.get("PATH", "").split(os.pathsep)
    if ephemeral:
        drop = {os.path.join(ephemeral, "Scripts"), os.path.join(ephemeral, "bin")}
        path_parts = [p for p in path_parts if p not in drop]

    # 2. The project's own venv, first - if it has one.
    for candidate in (".venv", "venv", ".env"):
        for bindir in ("Scripts", "bin"):
            venv_bin = project_root / candidate / bindir
            if venv_bin.is_dir():
                env["VIRTUAL_ENV"] = str(project_root / candidate)
                path_parts.insert(0, str(venv_bin))
                env["PATH"] = os.pathsep.join(path_parts)
                return env

    env["PATH"] = os.pathsep.join(path_parts)
    return env


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    # Keep the tail. Test runners put the summary at the bottom.
    return "... [output truncated] ...\n" + text[-MAX_OUTPUT_CHARS:]


def main() -> None:
    try:
        data = json.load(sys.stdin)

        # Loop guard. Without this the hook blocks the stop, the agent works,
        # tries to stop again, is blocked again, forever. If Claude Code tells us
        # we are already inside a stop-hook cycle, stand down.
        if data.get("stop_hook_active"):
            sys.exit(0)

        project_root = Path(data.get("cwd") or ".")
        run_dir = project_root / TEST_SUBDIR if TEST_SUBDIR else project_root

        result = subprocess.run(
            TEST_COMMAND,
            shell=True,               # run the command VERBATIM, as you typed it
            capture_output=True,
            text=True,
            cwd=str(run_dir),
            env=_project_env(run_dir),
            timeout=TIMEOUT_SECONDS,
        )

        if result.returncode == 0:
            sys.exit(0)  # green - let it finish

        output = _clip((result.stdout or "") + "\n" + (result.stderr or ""))
        print(
            "BLOCKED: the tests are not passing, so this turn is not done.\n"
            f"Command: {TEST_COMMAND}\n"
            f"Exit code: {result.returncode}\n\n"
            f"{output}\n\n"
            "Fix the failures and try again. Do not change the tests to make them "
            "pass unless the test itself is provably wrong.",
            file=sys.stderr,
        )
        sys.exit(2)

    except subprocess.TimeoutExpired:
        # Do not trap the user because the suite is slow. Say so and allow.
        print(
            f"Test command exceeded {TIMEOUT_SECONDS}s; allowing the stop. "
            "Raise TIMEOUT_SECONDS or scope TEST_COMMAND to a faster subset.",
            file=sys.stderr,
        )
        sys.exit(0)

    except Exception:
        # Fail open. A broken guarantee is better than a bricked session.
        sys.exit(0)


if __name__ == "__main__":
    main()
