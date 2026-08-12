"""Protected paths, size cap, and the binary-asset ban. Structural, not prompted.

FACTORY_RULES.md 5, 6 and 8. This runs BEFORE any other evaluation, because a change
that can edit the rulebook must not be judged against the edited rulebook.

Usage:
    python factory/guard.py [--base <ref>] [--head <ref>]

Defaults to comparing the working tree against the base branch. Exits:
    0  PROTECTED_OK
    1  PROTECTED_VIOLATION   a protected file was touched -- auto-reject, no fix attempt
    2  GUARD_ERROR           the guard could not run, which is NOT a pass

Exit code 2 matters more than it looks. A guard that cannot determine the diff must fail
closed. Failing open here would mean "we could not check, so we merged", which is the
same class of mistake as counting a skipped check as a passed one.
"""
from __future__ import annotations
import fnmatch
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kept here, in code, rather than in a data file the factory could plausibly be asked to
# edit as part of some other task. factory/** is itself protected, so this list is
# protected by the rule it defines.
PROTECTED = [
    # Governance -- the constitution. The agent cannot amend the rules it is judged by.
    "MISSION.md", "FACTORY_RULES.md", "CLAUDE.md", "AGENTS.md", "FACTORY.md",
    # The PRD the mission was compressed from. ADD YOUR PATH.
    "docs/*.prd.md",
    # The locks: thresholds a human chose, and the ratchet floor. Protected so that
    # raising a floor is a deliberate human commit rather than something a builder can
    # do in the same PR that made the floor inconvenient.
    ".factory/locks/*",
    # The holdout: the assertions the builder does not get to weaken.
    ".factory/holdout/*",
    # The machinery, including this file. factory/* being on its own list is what stops
    # a PR supplying the guard that judges it.
    "factory/*",
    # The deliberate-defect set. A builder that can edit the mutations can pass them.
    # ADD YOUR PATH if you build one.
    "harness/mutations/*",
    # Secrets. Being unable to EDIT one does not stop `git add -A` from publishing one
    # that appears for the first time - see the pre-flight in run-workflow.sh.
    ".env", ".env.*", "*.local", "*credential*", "*secret*",
]

# ADD ANYTHING WITH A BLAST RADIUS YOU CANNOT ABSORB. Auth modules, rate-limit
# constants, payment code, migrations, CI config, Dockerfiles, deploy/ and infra/.
# The interview's R3 (the defaults table) exists to produce this list; seed it, do not just accept
# whatever came back.
PROTECTED += [
    # ".github/*",
    # "deploy/*", "infra/*",
    # "Dockerfile", "docker-compose*.yml",
    # "app/auth/*",
]

# Optional: a whole file category banned by extension rather than by intent, for the
# case where a mission says "no imported assets" or "no vendored binaries". Checked by
# extension because "just one placeholder" is how the exception becomes the rule.
# Leave empty if this does not apply to your project.
BINARY_ASSETS: list[str] = [
    # "*.png", "*.jpg", "*.gif", "*.wav", "*.mp3", "*.ttf",
]

# Crude, and it works. Unsupervised agents ship 3,000-line PRs nobody can review, and
# "nobody can review it" is where a factory stops being auditable even in principle.
SIZE_CAP = int(os.environ.get("FACTORY_SIZE_CAP", "500"))
SIZE_EXEMPT = [".factory/runs/*", ".factory/locks/*"]

# THE SCOPE LEASH, and it is a file count rather than a line count on purpose.
#
# The failure it catches is specific and it is not size: a cleanup or refactor node with
# no scope will grow a six-file PR into eleven, and introduce a bug in one of the five it
# was never asked to touch. That PR can be well under the line cap the whole way - five
# one-line "while I was in here" edits cost nothing in lines and are exactly the diff no
# reviewer would have approved.
#
# A cap enforced in code beats the same instruction in a prompt, which is a suggestion
# with good manners. Raise it deliberately for a repo whose changes genuinely span more
# files; set it to 0 to disable and accept that the line cap is your only scope control.
FILE_CAP = int(os.environ.get("FACTORY_FILE_CAP", "12"))


def git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def base_ref(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for cand in ("origin/HEAD", "main", "master"):
        rc, out = git("rev-parse", "--verify", "--quiet", cand)
        if rc == 0 and out:
            return cand
    return None


def matches(path: str, patterns: list[str]) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(os.path.basename(p), pat)
               for pat in patterns)


def main() -> int:
    argv = sys.argv[1:]
    base = base_ref(argv[argv.index("--base") + 1] if "--base" in argv else None)
    head = argv[argv.index("--head") + 1] if "--head" in argv else None

    if base is None:
        print("GUARD_ERROR: no base branch found. The guard fails closed: a diff that "
              "cannot be computed is not a diff that was checked.")
        return 2

    # THREE dots, always. `git diff main` compares the two TIPS, so a branch cut before
    # main moved reports main's later commits as though this branch had made them -- and
    # main's later commits routinely touch factory/** and the locks. Every such branch was
    # auto-rejected under 6.1 for protected files it never went near: a false positive in
    # the most severe gate there is, firing more often the longer a branch lives.
    #
    # `main...HEAD` compares against the MERGE BASE: what this branch actually changed.
    rng = f"{base}...{head}" if head else f"{base}...HEAD"

    rc, out = git("diff", "--name-only", rng)
    if rc != 0:
        print(f"GUARD_ERROR: git diff {rng} failed. Failing closed.")
        return 2
    changed = [f for f in out.splitlines() if f.strip()]

    # A three-dot diff only sees COMMITTED work. In the workflow the guard runs after the
    # commit step so that is the whole story, but anything run by hand on a dirty tree
    # would otherwise be checked against nothing and print a confident PROTECTED_OK. The
    # union costs nothing and keeps the guard failing closed rather than blind.
    if not head:
        # `-uall`, and it is not optional. The default (`-unormal`) collapses an untracked
        # DIRECTORY into a single entry - `src/` rather than the forty files inside it. So
        # a node that creates a whole new directory reported one changed file, sailed past
        # any file-count scope cap, and had none of its contents checked against the
        # protected list or the banned categories individually. Found by pointing the new
        # scope leash at thirteen new files in a new folder and watching it report one.
        rc, dirty = git("status", "--porcelain", "--untracked-files=all")
        if rc != 0:
            print("GUARD_ERROR: git status failed. Failing closed.")
            return 2
        for row in dirty.splitlines():
            # porcelain is exactly two status columns, then the path. Slicing 3 eats the
            # first character of the filename when the second column is blank.
            path = row[2:].lstrip().strip('"')
            if " -> " in path:                      # a rename: check the destination
                path = path.split(" -> ", 1)[1]
            if path and path not in changed:
                changed.append(path)

    rc, stat = git("diff", "--numstat", rng)
    lines = 0
    if rc == 0:
        for row in stat.splitlines():
            parts = row.split("\t")
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                if not matches(parts[2], SIZE_EXEMPT):
                    lines += int(parts[0]) + int(parts[1])

    print(f"GUARD_START range={rng} files={len(changed)} lines={lines}")

    violations: list[tuple[str, str]] = []
    for f in changed:
        if matches(f, PROTECTED):
            violations.append((f, "protected file (FACTORY_RULES.md 5)"))
        elif matches(f, BINARY_ASSETS):
            violations.append((f, "banned file category (see BINARY_ASSETS)"))

    for f in changed:
        print(f"  {'BLOCK' if any(v[0] == f for v in violations) else 'ok   '}  {f}")

    print(f"GUARD_FILES_CHECKED={len(changed)}")

    if violations:
        print(f"PROTECTED_VIOLATION={len(violations)}")
        for f, why in violations:
            print(f"  {f}: {why}")
        print("Auto-reject, no fix attempt (FACTORY_RULES.md 6). Needing one of these "
              "touched means the scope was misunderstood, which is a triage bug rather "
              "than a code bug -- escalate to needs-human.")
        return 1

    scoped = [f for f in changed if not matches(f, SIZE_EXEMPT)]
    if FILE_CAP and len(scoped) > FILE_CAP:
        print(f"SCOPE_VIOLATION: {len(scoped)} files changed, cap is {FILE_CAP}. "
              "A node that can edit outside its own scope will grow the PR and introduce "
              "a bug in a file nobody asked it to touch. Split the work into a sub-issue.")
        return 1

    if lines > SIZE_CAP:
        print(f"SIZE_VIOLATION: {lines} lines changed, cap is {SIZE_CAP} "
              "(FACTORY_RULES.md 8). Split the work into a sub-issue rather than "
              "shipping something nobody could review even in principle.")
        return 1

    print("PROTECTED_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
