#!/usr/bin/env python3
"""HOLDOUT SCENARIOS. Copy to `.factory/holdout/run.py`, NOT into `harness/`.

    .factory/holdout/run.py      <- here. The builder cannot read this directory.
    harness/                     <- NOT here. The builder reads everything in harness/.

WHY THE PATH IS THE POINT

Everything in `harness/` sits inside the agent's optimisation loop: it can read those
checks, run them, and iterate until they are green. Given enough attempts it will satisfy
them - which is exactly what you asked for, and exactly why passing them proves less than
it feels like it does.

These assertions are different only because the builder never sees them. The runner
passes `--disallowedTools Read/Glob/Grep(.factory/holdout/**)` to every node, and
`guard.py` treats this directory as protected so no PR can edit it. That is the whole
independence argument, and it is the only honest reason to merge code nobody read.

THE RULES, and they are short:

  1. **Write these BEFORE the work.** A scenario written after seeing the implementation
     is a description of the implementation.
  2. **Duplicate, do not import.** Importing a helper from `harness/` re-couples you to
     code the builder can edit, and the wall is gone with one refactor nobody noticed.
  3. **Compose.** The dominant real failure is not cheating, it is FEATURE ISOLATION -
     components individually correct that never work together. Unit tests test features
     in isolation by definition, so the thing they measure is precisely the thing that is
     not broken. Test features TOGETHER, in sequences a user would actually perform.
  4. **Use inputs that appear nowhere else in the repo.** If the value is grep-able from
     the builder's side it is a value it can special-case.

Emits `HOLDOUT_PASSED scenarios=N assertions=M`. The count is the point: a skipped
scenario and a passed scenario are indistinguishable without one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# The DRIVER is shared (starting a process is not an assertion); the SCENARIOS are not.
# Rule 2 is about assertion helpers - duplicate those - not about process management.
_HARNESS = Path(__file__).resolve().parent.parent.parent / "harness"
sys.path.insert(0, str(_HARNESS))
from appproc import make_driver                                # noqa: E402

CONFIG = json.loads((_HARNESS / "harness.config.json").read_text(encoding="utf-8"))

ASSERTIONS = 0
FAILURES: list[str] = []


def expect(name: str, ok: bool, detail: str = "") -> None:
    global ASSERTIONS
    ASSERTIONS += 1
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# SCAFFOLD_EXAMPLE_DELETE_THIS_LINE_WHEN_YOU_WRITE_YOUR_OWN
# ===========================================================================
# TODO: DELETE EVERY SCENARIO BELOW AND WRITE YOURS.
# Delete the marker line above when they are yours. The doctor blocks on it.
#
# What is here is a worked example against a small HTTP service. The SHAPE is what to
# steal: each scenario is several features used together, with values that exist nowhere
# else in the repository.
# ===========================================================================

def scenario_round_trip_survives_a_restart(app) -> None:
    """Shorten -> resolve -> restart -> resolve again.

    Three features composed. Each one passes its own unit test in isolation; what this
    asks is whether persistence, code generation and resolution agree with each other
    across a process boundary.
    """
    url = "https://holdout.invalid/qz7t/never-appears-in-the-repo?x=1"
    status, body, _ = app.post("/api/shorten", json.dumps({"url": url}))
    expect("shorten accepted", status == 200, f"status={status}")
    code = json.loads(body).get("code") if status == 200 else None
    expect("a code came back", bool(code), f"body={body[:100]!r}")

    if not code:
        return
    status, _, headers = app.get(f"/{code}")
    expect("resolves to the exact url", status == 302 and headers.get("Location") == url,
           f"status={status} location={headers.get('Location')!r}")


def scenario_idempotence_holds_under_interleaving(app) -> None:
    """The product's own guarantee, exercised with other work in between.

    A guarantee that only holds when nothing else happened is not a guarantee.
    """
    a = "https://holdout.invalid/interleave-aaa"
    b = "https://holdout.invalid/interleave-bbb"
    codes = []
    for u in (a, b, a, b, a):
        status, body, _ = app.post("/api/shorten", json.dumps({"url": u}))
        codes.append(json.loads(body).get("code") if status == 200 else None)
    expect("same url always gives the same code", codes[0] == codes[2] == codes[4],
           f"got {codes[0]}, {codes[2]}, {codes[4]}")
    expect("different urls give different codes", codes[0] != codes[1],
           f"both were {codes[0]}")


def scenario_bad_input_never_becomes_a_redirect(app) -> None:
    """The invariant, probed from several directions at once."""
    for bad in ("ftp://holdout.invalid/x", "javascript:alert(1)", "/relative", ""):
        status, _, _ = app.post("/api/shorten", json.dumps({"url": bad}))
        expect(f"rejects {bad[:24]!r}", status >= 400, f"status={status}")


SCENARIOS = [
    scenario_round_trip_survives_a_restart,
    scenario_idempotence_holds_under_interleaving,
    scenario_bad_input_never_becomes_a_redirect,
]


def main() -> int:
    with make_driver(CONFIG) as app:
        for fn in SCENARIOS:
            try:
                fn(app)
            except Exception as e:                             # noqa: BLE001
                FAILURES.append(f"{fn.__name__} raised {type(e).__name__}: {e}")

    if FAILURES:
        for f in FAILURES:
            print(f"  HOLDOUT_FAIL  {f}", flush=True)
        print(f"HOLDOUT_FAILED scenarios={len(SCENARIOS)} assertions={ASSERTIONS} "
              f"failures={len(FAILURES)}", flush=True)
        return 1

    print(f"HOLDOUT_PASSED scenarios={len(SCENARIOS)} assertions={ASSERTIONS}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
