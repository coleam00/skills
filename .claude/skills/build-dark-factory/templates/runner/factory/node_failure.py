"""Why a node failed, in one line, from the agent's own report.

    python factory/node_failure.py <node.json> <node-name> <max-budget-usd>

`run-workflow.sh` used to escalate every node failure as "a build node failed". A node that
ran out of turns, a node that refused on principle, a node that was denied a tool it needed
and a node that crashed all produced that same sentence -- and only one of them is a bug.
An escalation that does not name its cause sends whoever reads it at 3am to the wrong file,
and unattended it does that overnight.

The distinction that matters most is BUDGET versus BUG. A turn cap is a number the operator
picked; hitting it means the work was larger than the allowance, not that anything is
broken. It is the one failure here whose fix is "raise a number or split the issue", and it
is the one that looked most like a code fault.
"""
from __future__ import annotations
import json
import os
import sys


def denials(d: dict, name: str) -> str:
    """Tools the node asked for and was refused. Reported even on a clean exit.

    A denied tool does not make the agent exit non-zero -- it makes it stop and ask a human
    who is not there. The run then completes "successfully" having done nothing, and the
    next guard downstream reports whatever it happens to notice instead of the cause.
    """
    got = d.get("permission_denials") or []
    if not got:
        return ""
    cmds = []
    for item in got:
        inp = item.get("tool_input") or {}
        cmds.append(f"{item.get('tool_name')}({inp.get('command') or inp.get('file_path') or '?'})")
    uniq = list(dict.fromkeys(cmds))
    return (f"{name}: was DENIED a tool it asked for and stopped to ask a human who is not "
            f"there. Denied: {'; '.join(uniq[:3])}. Either the workflow's allowlist is too "
            f"narrow for what the issue needs, or the plan specified a step this node "
            f"cannot execute (FACTORY_RULES.md 8)")


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--denials-only"]
    denials_only = "--denials-only" in sys.argv
    sys.argv = [sys.argv[0], *argv]

    if denials_only:
        path = sys.argv[1]
        name = sys.argv[2] if len(sys.argv) > 2 else "node"
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (ValueError, OSError):
            return 0
        msg = denials(d, name)
        if msg:
            print(msg)
        return 0

    path = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "node"
    cap = sys.argv[3] if len(sys.argv) > 3 else "?"

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(f"{name}: the agent produced no output at all -- it did not start, or it "
              f"died before writing anything")
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (ValueError, OSError):
        print(f"{name}: the agent's output was not parseable JSON, so the reason is "
              f"unavailable. See {os.path.basename(path)}")
        return 0

    subtype = d.get("subtype") or d.get("stop_reason") or "unknown"
    turns = d.get("num_turns")

    denied = denials(d, name)
    if denied:
        print(denied)
        return 0
    cost = d.get("total_cost_usd")
    if subtype in ("error_max_budget", "error_max_turns"):
        # Naming this correctly is most of what an escalation is worth. A node that hit
        # the operator's own ceiling is a COST decision, not a bug, and sending someone
        # to look for a fault that does not exist is how a 3am page wastes an hour.
        print(f"{name}: hit the spend ceiling after {turns} turn(s) "
              f"(${cost} of ${cap}). This is a BUDGET, not a bug -- the node was still "
              f"working. Raise FACTORY_MAX_BUDGET_USD, or split the issue into "
              f"sub-issues (FACTORY_RULES.md 8)")
    elif subtype in ("error_during_execution", "error"):
        print(f"{name}: the agent errored after {turns} turns (subtype={subtype})")
    else:
        print(f"{name}: stopped after {turns} turns with subtype={subtype}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
