#!/usr/bin/env python3
"""The gate's entrypoint. `FACTORY_VALIDATE_CMD` points here.

    python harness/ci.py            the whole gate
    python harness/ci.py --quick    the cheap subset an implementing node runs on itself

THIS FILE IS THE STEP LADDER, AND THE LADDER IS THE SAME IN EVERY FACTORY.

That is not an assumption. Two people built this harness independently, on different
products, never seeing each other's work, and both wrote this shape: an ordered ladder,
a positive marker per rung with a count, a namer that reports WHICH rung stopped the run,
and a `--quick` subset. Both separately invented a "zero tests discovered is not a pass"
guard. The structure is determined by the marker contract, not by the app.

**Every COMMAND it runs lives in `harness.config.json`, not here.** The first version of
this file hardcoded `python -m compileall` and `python -m unittest`, which made a
scaffold claiming to be universal quietly Python-only - a Go repo, a Node repo or a CLI
with no HTTP surface would have had to rewrite the ladder to change two strings.

WHAT IS STILL NOT TEMPLATABLE IS EVERY ASSERTION. What "working" means for your product
is the one thing nobody can write in advance, and it lives in `e2e.py`.

THE CONTRACT, in four parts:

  1. A POSITIVE marker for every rung that RAN. The gate greps these by name from
     FACTORY_REQUIRED_MARKERS; it never tests for the absence of "error".
  2. A COUNT wherever one exists. A skipped check and a passed check are
     indistinguishable without one.
  3. Exit NON-ZERO when the software is broken.
  4. Print to STDOUT. The runner appends this to guard.py's output in one gate.log.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
QUICK = "--quick" in sys.argv

CONFIG = json.loads((HERE / "harness.config.json").read_text(encoding="utf-8"))


def resolve(argv: list[str]) -> list[str]:
    """Make argv[0] something the OS can actually execute.

    On Windows the tools people configure here - `npm`, `npx`, `yarn`, `pnpm`, `tsc`,
    `cargo`? no, but most JS tooling - are `.cmd` shims, and `subprocess` without a shell
    does not consult PATHEXT. So a perfectly correct `"unit": "npm test"` fails with
    `[WinError 2] The system cannot find the file specified`, which reads like the tool
    is not installed when it is on PATH and works in any terminal.

    Found the first time this scaffold was pointed at a Node project. `shutil.which` does
    the PATHEXT lookup, so the config stays the command you would type.

    THE QUOTES COME OFF FIRST, and that is not cosmetic. Commands are split with
    `shlex.split(posix=False)`, which is right on Windows because it leaves backslashes in
    paths alone -- but it also leaves the QUOTES attached to the token. So a perfectly
    reasonable config whose interpreter path contains a space:

        "unit": "\\"C:\\\\Program Files\\\\Python312\\\\python.exe\\" -m pytest"

    arrived here as argv[0] == '"C:\\Program Files\\Python312\\python.exe"', quotes and
    all. `shutil.which` cannot match that, so it fell through unresolved and subprocess
    failed with `[WinError 2] The system cannot find the file specified` -- the exact
    misleading error this function exists to prevent, for the exact reason it was written:
    a command that is correct and works when typed. Quoting is not optional for a path
    with a space, and `C:\\Program Files` is where Windows puts things.
    """
    if not argv:
        return argv
    head = argv[0]
    if len(head) > 1 and head[0] == head[-1] and head[0] in "\"'":
        head = head[1:-1]
    found = shutil.which(head)
    # `head` even when unresolved: subprocess handles a space inside a single argv entry,
    # so the de-quoted form is strictly more runnable than the quoted one.
    return [found or head, *argv[1:]]


def run(step: str, cmd: str | list[str], timeout: int = 300) -> tuple[int, str]:
    """One rung. A timeout is a FAILURE, not a skip - a hung check reports nothing."""
    argv = resolve(shlex.split(cmd, posix=False) if isinstance(cmd, str) else list(cmd))
    try:
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except OSError as e:
        return 127, f"could not run {argv[0] if argv else cmd!r}: {e}"


def watchdog(seconds: int, label: str, app=None):
    """A hard deadline for the one rung that cannot have a subprocess timeout.

    THE RUNG MOST LIKELY TO HANG WAS THE ONLY UNPROTECTED ONE. Every other rung goes
    through `run()`, which passes `timeout=` to `subprocess.run`. The e2e rung does not:
    it imports `run_e2e` and calls it in-process, so nothing upstream could interrupt it.

    Found by pointing the scaffold at a frontend app. Browser CLIs - Playwright's driver
    server, chromedriver, agent-browser - spawn a PERSISTENT DAEMON that inherits the
    stdout pipe, so a `subprocess.run(..., capture_output=True)` inside `e2e.py` blocks on
    EOF forever after the CLI itself has exited. The gate printed `APP_STARTED` and then
    nothing at all: no marker, no `GATE_FAILED`, no exit. Five minutes of silence is
    indistinguishable from a slow test, and an unattended factory waits for it all night
    while holding its dispatch lock.

    A timeout is a FAILURE and not a skip, so this prints the marker and exits non-zero.
    It tears the app down first on a best-effort basis: `os._exit` skips context managers,
    and a leaked server holding the port poisons the next lap.
    """
    def bark() -> None:
        print(f"E2E_TIMEOUT after {seconds}s - the journey never returned. Nothing "
              f"upstream can interrupt this rung, so the run is being killed here. If a "
              f"browser CLI is involved, the usual cause is capture_output=True on a "
              f"process that spawns a daemon: redirect to a real file handle instead. "
              f"Raise e2e_timeout_s in harness.config.json if the journey is genuinely "
              f"this slow.", flush=True)
        print(f"GATE_FAILED: {label}", flush=True)
        try:
            if app is not None:
                app.__exit__(None, None, None)
        except Exception:                                          # noqa: BLE001
            pass
        sys.stdout.flush()
        os._exit(124)

    t = threading.Timer(seconds, bark)
    t.daemon = True
    t.start()
    return t


def fail(step: str, detail: str = "") -> int:
    """Name the rung that actually stopped the run.

    The gate asserts markers in a FIXED order rather than run order, so without this a
    suite that died early is reported as whichever marker is checked first - true, and
    several rungs downstream of the cause. Misnaming your own failure is most of the cost
    of a failure nobody watched.
    """
    if detail:
        print(detail.strip()[-2000:], flush=True)
    print(f"GATE_FAILED: {step}", flush=True)
    return 1


def optional_step(name: str, marker: str) -> bool:
    """A rung with no command configured. LOUD, never silent.

    An unconfigured rung that printed nothing was indistinguishable from one that passed,
    which is the exact failure this whole file exists to prevent - so absence is a fact
    in the log, and the gate can be told to require the marker.
    """
    print(f"{marker}_SKIPPED no '{name}' command in harness.config.json", flush=True)
    return True


def main() -> int:
    print(f"HARNESS_START mode={'quick' if QUICK else 'full'} driver={CONFIG.get('driver')}",
          flush=True)

    # --- 1. static -----------------------------------------------------------
    static_cmd = CONFIG.get("static", "").strip()
    if not static_cmd:
        optional_step("static", "STATIC")
    else:
        rc, out = run("static", static_cmd)
        if rc != 0:
            return fail("static", out)
        print("STATIC_OK", flush=True)

    # --- 2. unit -------------------------------------------------------------
    unit_cmd = CONFIG.get("unit", "").strip()
    if not unit_cmd:
        optional_step("unit", "UNIT")
    else:
        rc, out = run("unit", unit_cmd)
        if rc != 0:
            return fail("unit", out)
        pattern = CONFIG.get("unit_count_pattern", "").strip()
        if pattern:
            m = re.search(pattern, out)
            ran = int(m.group(1)) if m else 0
            # ZERO IS NOT A PASS. A suite that discovered nothing exits 0 and looks
            # perfect; both independent builds of this file added this guard unprompted.
            if ran == 0:
                return fail("unit", "UNIT_ERROR: the runner reported 0 tests - a suite "
                                    "that ran nothing is not a suite that passed. If the "
                                    "count is real, fix unit_count_pattern")
            print(f"UNIT_PASSED tests={ran}", flush=True)
        else:
            print("UNIT_PASSED tests=unknown (no unit_count_pattern set - a passing "
                  "suite and an absent one look identical here)", flush=True)

    if QUICK:
        # The subset an implementing node runs on itself. A STRICT subset: never a check
        # the full run lacks. Nothing downstream trusts it - the full gate re-runs
        # everything independently, which is why the builder may run anything at all.
        print("GATE_OK mode=quick", flush=True)
        return 0

    # --- 3. the app actually works -------------------------------------------
    # ONE OF THE TWO GATES THAT MUST BE CODE. Without a positive assertion here, a
    # crashed app produces a validator that reports "not testable" and something
    # downstream counts that as fine.
    sys.path.insert(0, str(HERE))
    from appproc import make_driver                              # noqa: E402
    from e2e import run_e2e                                      # noqa: E402

    with make_driver(CONFIG) as app:                             # prints APP_STARTED
        wd = watchdog(int(CONFIG.get("e2e_timeout_s", 300)), "e2e", app)
        try:
            steps = run_e2e(app)
        finally:
            wd.cancel()
        if steps is None:
            return fail("e2e")
        print(f"E2E_PASSED steps={steps}", flush=True)

        # --- 4. holdout ------------------------------------------------------
        # Assertions the BUILDER cannot read. Everything below the independence line
        # sits inside the agent's optimisation loop; given enough attempts it satisfies
        # those rather than the thing you meant.
        holdout = ROOT / ".factory" / "holdout" / "run.py"
        if holdout.exists():
            rc, out = run("holdout", [sys.executable, str(holdout)])
            if rc != 0:
                return fail("holdout", out)
            print(out.strip(), flush=True)
        else:
            print("HOLDOUT_ABSENT no .factory/holdout/run.py - NOTHING above the "
                  "independence line ran. Every check in this gate is one the builder "
                  "could read and iterate against.", flush=True)

    # --- 5. mutations ---------------------------------------------------------
    # NOT INSIDE A MUTATION RUN. The mutation runner copies harness/ into each throwaway
    # build, so without this the inner gate re-runs the whole suite - 6 defects becomes
    # 36 gate runs, and it also misattributes which rung caught the defect.
    mutate = ROOT / "harness" / "mutations" / "run.py"
    if os.environ.get("FACTORY_IN_MUTATION") == "1":
        print("MUTATIONS_SKIPPED running inside a mutation build", flush=True)
    elif mutate.exists():
        rc, out = run("mutations", [sys.executable, str(mutate)], timeout=900)
        print(out.strip(), flush=True)
        if rc != 0:
            return fail("mutations")
    else:
        print("MUTATIONS_ABSENT no harness/mutations/run.py - this gate has never been "
              "shown to fail. A gate that has never failed is a gate nobody has tested.",
              flush=True)

    print("GATE_OK mode=full", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
