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

FACTORY = """# The factory

**Current autonomy level: 1** - an accepted issue opens a branch and a PR.
**Stop button:** `touch .factory-stop` in the repo root.
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
    (root / "FACTORY.md").write_text(FACTORY, encoding="utf-8")
    (root / "CLAUDE.md").write_text("# Conventions\n\nUse tabs. Never npm.\n", encoding="utf-8")
    (root / "docs" / "product.prd.md").write_text("# PRD\n\nNon-goals: lots.\n", encoding="utf-8")
    # A healthy factory has one, and the runner's own pre-flight refuses to start
    # without it. Leaving it out of the fixture made every later case meaningless.
    (root / ".gitignore").write_text(
        ".env\n.env.*\nsecrets.json\ncredentials.json\n*.local\n*credential*\n*secret*\n"
        "service-account.json\n.archon/config.yaml\n.archon/.env\n"
        ".claude/settings.local.json\nconfig/secrets.yml\n"
        ".factory/runs/\n.factory/locks-runtime/\nfactory-*.log\n",
        encoding="utf-8")
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


RUNNER_STUB = """#!/usr/bin/env bash
sed -e "s|{{issue}}|$ISSUE_FILE|g" \\
    -e "s|{{rundir}}|$RUNDIR|g" \\
    -e "s|{{attempts}}|${ATTEMPTS:-0}|g" \\
    "$prompt" > "$rendered"
"""


def _prompts(root: pathlib.Path, body: str) -> None:
    """A runner that renders three placeholders, and one prompt that uses `body`."""
    (root / "factory" / "run-workflow.sh").write_text(RUNNER_STUB, encoding="utf-8")
    d = root / "factory" / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "implement.md").write_text(body, encoding="utf-8")


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
    # The judge is REFERENCED by the validator here, deliberately. An orphan prompt is
    # not running and only earns a WARN; this case has to exercise the path where the
    # doctor is entitled to block, or the FAIL branch goes untested.
    ("judge PROMPT told to read the plan", "holdout",
     lambda r: (
         (r / "factory" / "judge.md").write_text(
             "Read the implementation plan at .factory/runs/last/plan.md before judging.\n",
             encoding="utf-8"),
         (r / "factory" / "validate.sh").write_text(
             VALIDATE + '\nrun_node judge "$ROOT/factory/judge.md"\n', encoding="utf-8"),
     )),

    # And the orphan, asserted separately: reported, never blocking.
    ("orphan judge prompt is reported but does not block", "holdout",
     lambda r: (r / "factory" / "unused-verdict.md").write_text(
         "Read the implementation plan at plan.md before judging.\n", encoding="utf-8")),

    # THE FRESH-INSTALL BLOCKER. The runner's pre-flight refuses to start when a
    # credential-shaped path is not ignored, and it does not care whether the file exists
    # yet - the danger is the one that appears in three weeks inside a `git add -A`. The
    # doctor skipped absent files, so it disagreed with the thing it audits, and a repo
    # on which the factory could not complete a single lap reported Clean.
    ("a credential path is unignored, and does not exist yet", "secrets",
     lambda r: (r / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")),

    # Committing .factory/runs/ puts the implementer's PLAN on the branch, where the
    # validator reads it. The holdout dies to a tidy-looking diff.
    ("the factory's own run artifacts are not ignored", "secrets",
     lambda r: (r / ".gitignore").write_text(
         ".env\n.env.*\nsecrets.json\ncredentials.json\n*.local\n*credential*\n*secret*\n"
         "service-account.json\n.archon/config.yaml\n.archon/.env\n"
         ".claude/settings.local.json\nconfig/secrets.yml\n",
         encoding="utf-8")),

    # Shipping the example. The scaffolds removed a day of plumbing and created a new
    # way to fail: a gate that is green about somebody else's product.
    ("the harness scaffold was never edited", "scaffold",
     lambda r: (
         (r / "FACTORY.md").write_text(
             "# The factory\n\n**Current autonomy level: 2** - the validator runs.\n",
             encoding="utf-8"),
         (r / "harness").mkdir(exist_ok=True),
         (r / "harness" / "e2e.py").write_text(
             "# SCAFFOLD_EXAMPLE_DELETE_THIS_LINE_WHEN_YOU_WRITE_YOUR_OWN\n"
             "def run_e2e(app):\n    return 5\n", encoding="utf-8"),
     )),

    # Auto-merging with nothing above the independence line means every check in the
    # gate is one the builder can read and iterate against.
    ("level 3 with no holdout at all", "independence-line",
     lambda r: (r / "FACTORY.md").write_text(
         "# The factory\n\n**Current autonomy level: 3** - it auto-merges.\n",
         encoding="utf-8")),

    # A factory whose gate points at a harness nobody wrote is not a factory. It once
    # audited Clean with 0 FAIL, because every OTHER component was real.
    ("the validate command points at a file that does not exist", "validate-command",
     lambda r: (
         (r / "factory" / "config.sh").write_text(
             'FACTORY_VALIDATE_CMD="${FACTORY_VALIDATE_CMD:-python harness/ci.py}"\n',
             encoding="utf-8"),
     )),

    # A stale worktree holds another commit's copy of the factory. It must never be
    # able to satisfy a check the tree under audit fails - the same failure as running
    # the protected-path guard from inside the branch it is judging.
    ("merge evidence only exists in a stale worktree", "gate-is-code",
     lambda r: (
         (r / ".worktrees" / "v1" / "factory").mkdir(parents=True),
         (r / ".worktrees" / "v1" / "factory" / "validate.sh").write_text(
             VALIDATE, encoding="utf-8"),
         (r / "factory" / "validate.sh").unlink(),
     )),

    # The fix node asked for the validator's findings through `{{prev_run}}`, which the
    # renderer had no rule for. It received the braces verbatim, opened nothing, and
    # committed a fix reasoned from no evidence - without crashing, refusing, or logging
    # anything. Prompts are the file users are told to rewrite, so a rewrite can invent a
    # placeholder and nothing else in the system would ever mention it.
    ("a prompt uses a placeholder the runner never renders", "prompt-placeholders",
     lambda r: _prompts(r, "Read the findings at "
                           ".factory/runs/{{prev_run}}/verdict.json and fix them.\n")),
]


# (name, check that must NOT get worse, mutation)
#
# The other direction, and the one that was missing. Every case here is a shape the
# doctor used to report as a defect on a factory that was doing the right thing. A
# false positive is not a harmless conservatism: the doctor's whole claim is that its
# output can be read instead of its source, and a check that cries wolf gets muted,
# which costs exactly as much trust as a missed failure.
NEGATIVE_CASES = [
    # The scar: `pr-review-scope` was reached only from the implement workflow - the
    # builder reviewing its own work, which is entitled to read the plan it just wrote -
    # and the doctor FAILed a repo whose holdout was intact.
    ("builder-side review step reading its own plan", "holdout",
     lambda r: (
         (r / "factory" / "pr-review-scope.md").write_text(
             "Read the implementation plan at plan.md to scope this review.\n",
             encoding="utf-8"),
         (r / "factory" / "implement-issue.sh").write_text(
             "#!/usr/bin/env bash\nrun_command pr-review-scope\n", encoding="utf-8"),
     )),

    # The regression that a real safety fix introduced: consolidating the pipeline into
    # one runner removed the filenames the check was looking at, so a factory that still
    # read governance from the base branch stopped being seen to do it.
    ("governance read from base lives in a non-validator-named runner", "holdout",
     lambda r: (
         (r / "factory" / "validate.sh").write_text(
             VALIDATE.replace("git show origin/main:MISSION.md > /tmp/mission.md\n", ""),
             encoding="utf-8"),
         (r / "factory" / "run-workflow.sh").write_text(
             '#!/usr/bin/env bash\ngit show "$BASE:MISSION.md" > "$RUNDIR/MISSION.base.md"\n',
             encoding="utf-8"),
     )),

    # Testing for emptiness and then failing hard IS the fix for empty-is-not-pass.
    # Flagging the remedy as the disease teaches the reader that the finding is noise,
    # which is how a real one gets skimmed past later.
    ("empty result is detected and then HARD FAILS", "empty-is-not-pass",
     lambda r: (r / "factory" / "goodgate.sh").write_text(
         '#!/usr/bin/env bash\n'
         'if [ -z "$FAILURES_JSON" ]; then\n'
         '  echo "REPORT_UNPARSEABLE: no fenced json block" >&2\n'
         '  exit 1\n'
         'fi\n',
         encoding="utf-8")),

    # Capability is not the same question as what is switched on. A repo built for 3 and
    # dialled to 0 is a repo doing its homework; failing it teaches people to ignore the
    # doctor at the moment it is most useful.
    ("repo built for auto-merge but declared at level 0, with a FAIL present",
     "autonomy-level",
     lambda r: (
         (r / "FACTORY.md").write_text(
             "# The factory\n\n**Current autonomy level: 0** - run by hand.\n",
             encoding="utf-8"),
         (r / "factory" / "dispatch.sh").write_text(
             "#!/usr/bin/env bash\n# */30 * * * * cron\n"
             "plan_issue; implement; triage; comprehensive\ngh pr merge --squash\n",
             encoding="utf-8"),
         (r / "MISSION.md").unlink(),          # force a FAIL elsewhere in the report
     )),

]

# A check that fires on a correct configuration teaches people to skim the report, which
# costs exactly as much trust as a missed failure. Appended to NEGATIVE_CASES below.
NEGATIVE_EXTRA = [
    ("prompts using only rendered placeholders stay quiet", "prompt-placeholders",
     lambda r: _prompts(r, "Work {{issue}} and write your report to {{rundir}}.\n"
                           "You are attempt {{attempts}} of 2.\n")),

    # The provenance check required a COLON, and warned "MISSION does not name the PRD it
    # came from" against a MISSION whose second line was `Derived from
    # \`docs/shortlink.prd.md\`.` - the exact thing it asks for, in the most natural
    # English wording. Found end to end on a real repo. A checker that fails on the thing
    # it just asked for teaches people its warnings are noise, and they are right.
    ("provenance written without a colon stays quiet", "prd",
     lambda r: (r / "MISSION.md").write_text(
         MISSION.replace("**Derived from:** `docs/product.prd.md` - vendored 2026-01-01.",
                         "Derived from `docs/product.prd.md`."),
         encoding="utf-8")),

    ("provenance written as a markdown link stays quiet", "prd",
     lambda r: (r / "MISSION.md").write_text(
         MISSION.replace("**Derived from:** `docs/product.prd.md` - vendored 2026-01-01.",
                         "Derived from [the PRD](docs/product.prd.md)."),
         encoding="utf-8")),
]


NEGATIVE_CASES = NEGATIVE_CASES + NEGATIVE_EXTRA


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
        print("\nmust FIRE:")
        for name, check, mutate in CASES:
            with tempfile.TemporaryDirectory() as td2:
                work = pathlib.Path(td2) / "repo"
                shutil.copytree(healthy, work)
                mutate(work)
                after = audit(work)
            ok = after.get(check, 0) > base.get(check, 0)
            print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} "
                  f"{check} {base.get(check, 0)} -> {after.get(check, 0)}")
            passed, failed = passed + ok, failed + (not ok)

        print("\nmust STAY QUIET:")
        for name, check, mutate in NEGATIVE_CASES:
            with tempfile.TemporaryDirectory() as td2:
                work = pathlib.Path(td2) / "repo"
                shutil.copytree(healthy, work)
                mutate(work)
                after = audit(work)
            ok = after.get(check, 0) <= base.get(check, 0)
            print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} "
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
                  f"{'skill payload is not evidence about the repo':52s} "
                  f"gate-is-code {base.get('gate-is-code', 0)} -> {after.get('gate-is-code', 0)}")
            passed, failed = passed + ok, failed + (not ok)

    expected = len(CASES) + len(NEGATIVE_CASES) + 1
    print(f"\nPASSED={passed}  FAILED={failed}  CHECKS_RAN={passed + failed}/{expected}")
    if passed + failed != expected:
        print("EMPTY_IS_NOT_PASS: not every case ran")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
