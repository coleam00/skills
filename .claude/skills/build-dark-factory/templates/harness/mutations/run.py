#!/usr/bin/env python3
"""MUTATION TESTING. Break the software on purpose and require the gate to notice.

    python harness/mutations/run.py

THE ONLY THING THAT MEASURES YOUR HARNESS RATHER THAN YOUR CODE.

Everything else in the gate answers "is this build good?". This answers "would this gate
know if it were not?" - and they are completely different questions. A gate that has
never failed is a gate nobody has tested, and until you run this you do not have evidence
that any of your checks can fail at all.

HOW IT WORKS. For each defect: copy the repo to a temp dir, apply one textual mutation to
real source, run the gate there, and require it to go RED. A mutation the gate misses is
a class of bug that can currently merge unreviewed.

WHAT MAKES A GOOD DEFECT. Not typos - the compiler finds those. Aim at the seams where
your checks are weakest:

  * an invariant quietly inverted (a comparison flipped, a guard removed)
  * a value that stops changing (a counter that no longer increments)
  * an output that becomes constant (always the same code, always success)
  * an error path that silently succeeds
  * a value that is right on average and wrong in the specific case

The first run of a real mutation set found that zeroing a bonus escaped every check,
because the assertion only tested that a total MOVED rather than by how much. That hole
existed for weeks and no amount of reading the tests would have found it.

Emits `MUTATIONS_TOTAL=N` and `MUTATIONS_CAUGHT=N`. The gate requires them to be equal.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFECTS = Path(__file__).resolve().parent / "defects.json"

# What to copy into each throwaway build. Keep it small; this runs once per defect.
COPY = ["app", "tests", "harness", ".factory"]
SKIP_DIRS = {"__pycache__", ".git", "runs", "locks-runtime", "builds", ".worktrees"}


def build_copy(dest: Path) -> None:
    for item in COPY:
        src = ROOT / item
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dest / item,
                            ignore=shutil.ignore_patterns(*SKIP_DIRS))
        else:
            shutil.copy(src, dest / item)


def apply(dest: Path, d: dict) -> bool:
    """Textual mutation. Returns False if the anchor was not found."""
    target = dest / d["file"]
    if not target.exists():
        return False
    body = target.read_text(encoding="utf-8")
    if d["find"] not in body:
        return False
    target.write_text(body.replace(d["find"], d["replace"], 1), encoding="utf-8")
    return True


def main() -> int:
    if not DEFECTS.exists():
        print("MUTATIONS_ABSENT no defects.json next to this script", flush=True)
        return 0

    defects = json.loads(DEFECTS.read_text(encoding="utf-8"))["defects"]
    total = caught = not_injected = 0

    print("MUTATION_START", flush=True)
    for d in defects:
        total += 1
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "build"
            dest.mkdir()
            build_copy(dest)

            if not apply(dest, d):
                # NOT a pass. The anchor moved, so this defect tested nothing - and a
                # mutation set that silently stops injecting is a mutation set that
                # reports a perfect score for doing nothing at all.
                not_injected += 1
                print(f"  NOT_INJECTED  {d['id']:<38} anchor not found in {d['file']}",
                      flush=True)
                continue

            # Tell the inner gate not to recurse into its own mutation suite.
            env = dict(os.environ, FACTORY_IN_MUTATION="1")
            r = subprocess.run([sys.executable, "harness/ci.py"], cwd=dest, env=env,
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                caught += 1
                step = "gate"
                for line in (r.stdout or "").splitlines():
                    if line.startswith("GATE_FAILED:"):
                        step = line.split(":", 1)[1].strip()
                print(f"  CAUGHT        {d['id']:<38} by {step}", flush=True)
            else:
                print(f"  ESCAPED       {d['id']:<38} <-- {d['why']}", flush=True)

    print(f"MUTATIONS_TOTAL={total}", flush=True)
    print(f"MUTATIONS_CAUGHT={caught}", flush=True)
    print(f"MUTATIONS_NOT_INJECTED={not_injected}", flush=True)
    if caught == total and not_injected == 0:
        print("MUTATIONS_OK", flush=True)
        return 0
    print("MUTATIONS_FAILED - every escaped defect is a class of bug that can currently "
          "merge unreviewed", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
