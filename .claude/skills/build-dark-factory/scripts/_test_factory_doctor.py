"""Tests for factory_doctor.

The skill's own rule is that a gate which has never failed is a gate nobody has
tested. The doctor is the only deterministic thing this skill ships, so it gets
the same treatment: build a minimal healthy factory, break exactly one thing, and
require the doctor to notice.

Every case below is a defect the doctor missed at some point during development.
The last two are regressions with scars attached: the doctor once read its own
vendored files as evidence about the repo it was auditing, and its holdout check
never scanned the markdown prompts where judge instructions actually live.

    python _test_factory_doctor.py          # from this directory, no network, no API
"""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DOCTOR = HERE / "factory_doctor.py"
RANK = {"OK": 0, "INFO": 0, "WARN": 1, "FAIL": 2}

MISSION = """# Mission

**Derived from:** `docs/product.prd.md` - vendored 2026-01-01.

## What it is
A thing that does a thing for people who need that thing.

## Core capabilities (in scope)
- the loop
- the hub

## Out of scope, forever
- No multiplayer
- No networking of any kind
- No monetisation
- No second genre
- No platforms beyond desktop
- No imported binary assets
"""

RULES = """# Factory Rules

## 5. Protected files
`MISSION.md`, `FACTORY_RULES.md`, `CLAUDE.md`, `.factory/locks/**`

## 7. Escalation
Touch `.factory-stop` in the repo root to halt the dispatcher.
"""

VALIDATE = """#!/usr/bin/env bash
# The validator. Reads governance from the base branch, never from the PR.
git show origin/main:MISSION.md > /tmp/mission.md
git fetch origin
grep -q "APP_STARTED" "$LOG" || fail "app never started"
grep -q "E2E_PASSED" "$LOG"  || fail "e2e never ran"
STEPS=$(grep -oP 'E2E_PASSED steps=\\K[0-9]+' "$LOG" || echo 0)
[ "$STEPS" -ge 7 ] || fail "only $STEPS steps ran"
SCOPE=$(git diff --name-only origin/main...HEAD)
gh pr merge "$PR" --squash
"""


def build(root: pathlib.Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "factory").mkdir(parents=True)
    (root / ".factory" / "locks").mkdir(parents=True)
    (root / "MISSION.md").write_text(MISSION, encoding="utf-8")
    (root / "FACTORY_RULES.md").write_text(RULES, encoding="utf-8")
    (root / "CLAUDE.md").write_text("# Conventions\n\nUse tabs. Never npm.\n", encoding="utf-8")
    (root / "docs" / "product.prd.md").write_text("# PRD\n\nNon-goals: lots.\n", encoding="utf-8")
    (root / "factory" / "validate.sh").write_text(VALIDATE, encoding="utf-8")
    (root / ".factory" / "locks" / "floor.json").write_text('{"checks": 7}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)


def audit(root: pathlib.Path) -> dict[str, int]:
    r = subprocess.run([sys.executable, str(DOCTOR), "--repo", str(root), "--json", "--audit"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    data = json.loads(r.stdout)
    worst: dict[str, int] = {}
    for f in data["findings"]:
        # The field is "check". A test that reads "category" silently passes forever.
        worst[f["check"]] = max(worst.get(f["check"], 0), RANK[f["level"]])
    return worst


# (name, check that must get worse, mutation)
CASES = [
    ("mission deleted", "guidance-layer",
     lambda r: (r / "MISSION.md").unlink()),

    ("out-of-scope list too short", "out-of-scope",
     lambda r: (r / "MISSION.md").write_text(
         MISSION.split("## Out of scope")[0] + "## Out of scope, forever\n- No multiplayer\n",
         encoding="utf-8")),

    ("governance not on the protected list", "protected-list",
     lambda r: (r / "FACTORY_RULES.md").write_text(
         RULES.replace("`MISSION.md`, `FACTORY_RULES.md`, `CLAUDE.md`, ", ""), encoding="utf-8")),

    ("no PRD provenance", "prd",
     lambda r: (r / "MISSION.md").write_text(
         "\n".join(l for l in MISSION.splitlines() if not l.startswith("**Derived from")),
         encoding="utf-8")),

    ("validator greps for the ABSENCE of an error", "empty-is-not-pass",
     lambda r: (r / "factory" / "badgate.sh").write_text(
         '#!/usr/bin/env bash\nif [ -z "$(echo "$OUT" | grep ERROR)" ]; then merge_pr; fi\n',
         encoding="utf-8")),

    # Regression: prompts are markdown, and READ_RE only knew about code reads, so a
    # judge told in English to read the plan audited perfectly clean.
    ("judge PROMPT told to read the plan", "holdout",
     lambda r: (r / "factory" / "judge.md").write_text(
         "Read the implementation plan at .factory/runs/last/plan.md before judging.\n",
         encoding="utf-8")),
]


def main() -> int:
    if not DOCTOR.exists():
        print(f"cannot find {DOCTOR}")
        return 3

    with tempfile.TemporaryDirectory() as td:
        healthy = pathlib.Path(td) / "healthy"
        healthy.mkdir()
        build(healthy)
        base = audit(healthy)
        failing = [k for k, v in base.items() if v == 2]
        print(f"healthy fixture: {len(failing)} FAIL {failing if failing else ''}")
        if failing:
            print("  the fixture itself is unhealthy, so every result below is meaningless")
            return 3

        passed = failed = 0
        for name, check, mutate in CASES:
            with tempfile.TemporaryDirectory() as td2:
                work = pathlib.Path(td2) / "repo"
                shutil.copytree(healthy, work)
                mutate(work)
                after = audit(work)
            ok = after.get(check, 0) > base.get(check, 0)
            print(f"  {'PASS' if ok else 'FAIL'}  {name:44s} "
                  f"{check} {base.get(check, 0)} -> {after.get(check, 0)}")
            passed, failed = passed + ok, failed + (not ok)

        # Regression: the doctor must not audit its own vendored payload. A skill copied
        # into the repo it audits once satisfied `gate-is-code` with its own template.
        with tempfile.TemporaryDirectory() as td3:
            work = pathlib.Path(td3) / "repo"
            shutil.copytree(healthy, work)
            payload = work / ".claude" / "skills" / "build-dark-factory" / "templates"
            payload.mkdir(parents=True)
            (payload / "validate-gate.sh").write_text(
                '#!/usr/bin/env bash\ngh pr merge "$PR" --squash\ngrep -q "E2E_PASSED" "$LOG"\n',
                encoding="utf-8")
            (work / "factory" / "validate.sh").unlink()   # remove the repo's own evidence
            after = audit(work)
            ok = after.get("gate-is-code", 0) > base.get("gate-is-code", 0)
            print(f"  {'PASS' if ok else 'FAIL'}  "
                  f"{'skill payload is not evidence about the repo':44s} "
                  f"gate-is-code {base.get('gate-is-code', 0)} -> {after.get('gate-is-code', 0)}")
            passed, failed = passed + ok, failed + (not ok)

    print(f"\nPASSED={passed}  FAILED={failed}  CHECKS_RAN={passed + failed}")
    if passed + failed != len(CASES) + 1:
        print("EMPTY_IS_NOT_PASS: not every case ran")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
