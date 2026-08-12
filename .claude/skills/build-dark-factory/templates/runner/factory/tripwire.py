"""Fail loudly if a builder artifact reached the validator. FACTORY_RULES.md 9.

This should be impossible. The validator runs in its own worktree with its own context,
so the plan and the implementation report are simply not there.

It is checked anyway, because the failure it guards against is silent by construction.
If separation ever breaks -- a shared worktree, a stray copy, a `git add` that swept up
`.claude/plans/`, a future change to the workflow that reuses a directory -- the
validator keeps producing confident verdicts and every one of them is contaminated.
Nothing goes red. The verdicts just quietly start agreeing with the builder.

An independence property that nobody checks is an independence property nobody has.

    python factory/tripwire.py <validator-working-dir>
"""
from __future__ import annotations
import glob
import os
import sys

# Anything that reveals HOW the code was written rather than WHAT it does now.
FORBIDDEN = [
    ".claude/plans/**",
    ".claude/reports/**",
    ".factory/runs/*/priming.md",
    ".factory/runs/*/plan.md",
    ".factory/runs/*/report.md",
    "**/implementation-report*.md",
    "**/*-plan.md",
    ".claude/code-reviews/**",
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        print(f"TRIPWIRE_ERROR: {root} is not a directory. Failing closed.")
        return 2

    found: list[str] = []
    for pattern in FORBIDDEN:
        for hit in glob.glob(os.path.join(root, pattern.replace("/", os.sep)),
                             recursive=True):
            if os.path.isfile(hit):
                found.append(os.path.relpath(hit, root).replace("\\", "/"))

    print(f"TRIPWIRE_PATTERNS_CHECKED={len(FORBIDDEN)}")
    if found:
        print(f"TRIPWIRE_TRIPPED={len(found)}")
        for f in sorted(set(found)):
            print(f"  builder artifact in the validator's tree: {f}")
        print("The validator can see how the code was written. Its verdict is no longer "
              "independent evidence and must not be used to merge. This is a workflow "
              "bug, not a code bug (FACTORY_RULES.md 9).")
        return 1
    print("TRIPWIRE_CLEAR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
