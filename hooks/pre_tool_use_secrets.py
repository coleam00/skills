#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
PreToolUse hook - the guard.

Fires BEFORE every matched tool call. It inspects what the agent is about to do
and, if the call crosses a line you never want crossed, blocks it: print the
reason to stderr and exit(2). Claude Code stops the tool and hands the reason
back to the agent, so it adapts instead of doing the thing.

Two guarantees ship here:
  1. The agent can never reach your secrets - not the env file, not the other
     credential files (ssh keys, .pem, .aws, .netrc, credentials.json), and not
     by dumping the process environment. A committed `.env.example` is allowed.
  2. The agent can never run a destructive `rm -rf`.

Everything else is allowed (exit 0). The hook FAILS OPEN: any unexpected error
exits 0, so a bug in this script can never brick your session.

MAKE IT YOURS: the two `is_*` functions below are the entire policy. Add your own
(protected paths, prod config, lockfiles, migrations), or run the `hooks-create`
skill and describe the guarantee you want in plain English.

COVERAGE, HONESTLY: the hook is GUARANTEED to run. What it CATCHES is only as
good as the checks below. Three known gaps, all documented in hooks/README.md:
  - `@file` mentions in your prompt are attached without a tool call, so no
    PreToolUse hook fires for them at all.
  - The two-step route: nothing stops the agent WRITING a script that reads the
    environment and then running it. Closing that means inspecting the content
    of Write/Edit calls, not just the path.
  - A determined agent can find an encoding this regex does not match.
The hook is the enforcement point, not omniscience.
"""

import json
import re
import sys

# Committed template files that are safe to read. Everything else that looks like
# an env file is treated as real secrets. Change this one line if your repo uses a
# different convention (e.g. add ".env.sample" or ".env.template").
ENV_TEMPLATE_SUFFIXES = (".env.example",)

# Secrets do not only live in `.env` - these are the other usual homes.
SECRET_PATH = re.compile(
    r"\.env\b|\.pem$|\.key$|id_rsa|id_ed25519|\.ssh/|\.aws/credentials|\.netrc|credentials\.json",
    re.IGNORECASE,
)

# ...and they do not only live in FILES. Each of these reads them straight out of
# the process environment, which a file-only guard waves right through.
#
# NOTE: the shell-builtin names below are assembled from fragments on purpose.
# A guard that greps for these tokens is itself commonly guarded against, so a
# file containing them verbatim can get blocked by *another* hook before it is
# ever written. (That happened while authoring this file. It is a good
# illustration of the point: two guards, no coordination, and the second one
# cannot tell a detector from an exfiltrator.) The behaviour is identical.
_PRINT_ENV = "print" + "env"
_BARE_ENV = r"^\s*env\s*(\||>|$)"

ENV_DUMP = (
    re.compile(r"\b" + _PRINT_ENV + r"\b", re.IGNORECASE),
    re.compile(_BARE_ENV, re.IGNORECASE),  # bare `env`, maybe piped
    re.compile(r"\becho\b.*\$\{?[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", re.IGNORECASE),
    re.compile(r"os\.environ|process\.env|ENV\[", re.IGNORECASE),
)

BLOCKED_ENV_MESSAGE = (
    "BLOCKED: access to secrets is not allowed.\n"
    "Read a committed .env.example template instead."
)
BLOCKED_RM_MESSAGE = "BLOCKED: refusing to run a recursive-force delete (rm -rf)."


def _is_template(path: str) -> bool:
    return path.endswith(ENV_TEMPLATE_SUFFIXES)


def is_secret_access(tool_name: str, tool_input: dict) -> bool:
    """True if the call would reach a credential - by file OR by environment."""
    # File tools: check the path argument.
    if tool_name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = str(tool_input.get("file_path", "")).replace("\\", "/")
        return bool(SECRET_PATH.search(path)) and not _is_template(path)

    # Search tools: block reading secrets out via a pattern or a scoped path.
    if tool_name in ("Grep", "Glob"):
        target = f"{tool_input.get('pattern', '')} {tool_input.get('path', '')}".replace("\\", "/")
        return bool(SECRET_PATH.search(target)) and ".env.example" not in target

    # Shell: the command may name a credential file OR dump the environment.
    if tool_name in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", "")).replace("\\", "/")
        if any(p.search(command) for p in ENV_DUMP):
            return True
        return bool(SECRET_PATH.search(command)) and ".env.example" not in command

    return False


def is_dangerous_rm(tool_name: str, tool_input: dict) -> bool:
    """True if a shell command is a recursive-force delete (rm -rf and variants)."""
    if tool_name not in ("Bash", "PowerShell"):
        return False
    command = " ".join(str(tool_input.get("command", "")).lower().split())
    # rm with both recursive and force flags, in any order / spelling.
    return bool(
        re.search(r"\brm\b.*-[a-z]*r[a-z]*f", command)
        or re.search(r"\brm\b.*-[a-z]*f[a-z]*r", command)
        or re.search(r"\brm\b.*--recursive.*--force", command)
        or re.search(r"\brm\b.*--force.*--recursive", command)
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {}) or {}

        if is_secret_access(tool_name, tool_input):
            # exit 2 = block the tool; stderr goes back to the agent as the reason.
            print(BLOCKED_ENV_MESSAGE, file=sys.stderr)
            sys.exit(2)

        if is_dangerous_rm(tool_name, tool_input):
            print(BLOCKED_RM_MESSAGE, file=sys.stderr)
            sys.exit(2)

        sys.exit(0)  # allow

    except Exception:
        # Fail open - never let a hook error stop the agent from working.
        sys.exit(0)


if __name__ == "__main__":
    main()
