#!/usr/bin/env python3
"""The regression suite `templates/runner/factory/` never had.

    python scripts/_test_runner.py                 # run everything
    python scripts/_test_runner.py --only escal    # substring filter on the test name
    python scripts/_test_runner.py --keep          # leave the fixtures on disk to poke at
    python scripts/_test_runner.py --mutate        # does the suite actually CATCH anything?
    python scripts/_test_runner.py --list          # names only

WHY THIS EXISTS, since it is the same argument the skill makes about your code.

The skill's thesis is that you cannot ship unattended without a harness that proves the
code works. The skill shipped ~4,200 lines of runner with no test that ever EXECUTED it.
`factory_doctor` greps those files as text and `harness/ci.py` validates the user's product,
not this machinery. So every defect found in the runner was found by hand, once, and the
only record that it was ever fixed was a sentence in a markdown file. Nothing went red when
one came back.

That is why the same four failure shapes kept reappearing for weeks:

  * a state a node writes that the transition table forbids, killing the workflow mid-lap
  * an escalation that parks work without telling anybody
  * an unguarded command dying under `set -e` before the escalate on the next line
  * a gate that passes on the ABSENCE of a failure marker rather than the presence of a
    success marker

Every test below is named after the defect it locks. Adding a test here is how a fix stops
being a fact in a document and becomes a thing that cannot silently come back.

DETERMINISTIC AND FREE. The fixture stubs `FACTORY_AGENT` with a shell script and the
validator with a fake `harness/ci.py`, so a full lap costs nothing and repeats exactly. No
network, no model, no GitHub. That is deliberate: a suite that costs money per run is a
suite nobody runs.

READ `--mutate` BEFORE TRUSTING ANY OF IT. A green suite proves nothing on its own -- the
same argument this skill makes about mutation testing your product. `--mutate` reintroduces
each historical defect into a throwaway copy of the runner and asserts the suite goes RED.
A test whose defect can be restored while everything stays green is decoration, and it says
so by name.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TEMPLATES = SKILL / "templates"

# What is under test. Defaults to the shipped template; `--repo` points it at a factory
# somebody already BUILT, which is the case that matters after the first month: the runner
# is COPIED into a repo and never linked, so a template fix reaches nothing already built,
# and a hand-edited factory drifts from the template with nothing watching.
RUNNER_SRC = TEMPLATES / "runner"
FACTORY_SRC: Path | None = None          # set by --repo; None means "the template"

# Windows ships a `bash` with git; everything here drives the real shell scripts.
BASH = shutil.which("bash") or "bash"


# =============================================================================
# the fixture
# =============================================================================
class Factory:
    """A real git repo with the real shipped factory/ in it, and everything else faked.

    One is built ONCE per run and copied per test -- `git init` plus the template copy is
    most of the cost, and copying a built tree is far cheaper than rebuilding it.
    """

    def __init__(self, root: Path):
        self.root = root

    # --- running things ---------------------------------------------------
    def sh(self, cmd: str, env: dict | None = None, timeout: int = 180):
        e = dict(os.environ)
        e.update({
            "PYTHONIOENCODING": "utf-8",
            "FACTORY_BACKEND": "files",
            "FACTORY_AUTONOMY": "3",
            # keep tests off each other's Task Scheduler / cron entries
            "FACTORY_TASK_NAME": "fixture-never-installed",
        })
        e.update(env or {})
        p = subprocess.run([BASH, "-c", cmd], cwd=self.root, env=e,
                           capture_output=True, text=True, timeout=timeout,
                           errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def py(self, args: str, env: dict | None = None):
        return self.sh(f"python factory/state.py {args}", env=env)

    def tick(self, env: dict | None = None):
        return self.sh("bash factory/orchestrator.sh", env=env)

    def run(self, workflow: str, target: str, env: dict | None = None):
        return self.sh(f"bash factory/run-workflow.sh {workflow} {target}", env=env)

    # --- reading state ----------------------------------------------------
    def read(self, rel: str) -> str:
        p = self.root / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

    def write(self, rel: str, text: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def state_of(self, rel: str) -> str:
        m = re.search(r"^state:\s*(\S+)", self.read(rel), re.M)
        return m.group(1) if m else "<no state line>"

    def notifications(self) -> str:
        return self.read(".factory/notifications/feed.log")

    def ledger(self) -> str:
        return self.read(".factory/needs-human.md")

    def clear_signals(self):
        for rel in (".factory/notifications/feed.log", ".factory/needs-human.md"):
            p = self.root / rel
            if p.exists():
                p.unlink()

    # --- fixture authoring -------------------------------------------------
    def issue(self, ident: str, state="accepted", title="The widget does not gad",
              body="The widget should gad. It does not.", extra=""):
        """Write an issue file. `title=None` omits the title line entirely."""
        fm = [f"id: {ident}"]
        if title is not None:
            fm.append(f"title: {title}")
        fm += [f"state: {state}", "priority: high", "area: widget"]
        if extra:
            fm.append(extra)
        rel = f"issues/{ident}.md"
        self.write(rel, "---\n" + "\n".join(fm) + "\n---\n\n" + body + "\n")
        return rel

    def pr(self, ident: str, state="open", issue=None, attempts=0, branch=None):
        issue = issue or f"issues/{ident}.md"
        branch = branch or f"factory/{ident}"
        rel = f".factory/prs/{ident}.md"
        self.write(rel, "---\n"
                   f"id: {ident}\ntitle: a pr\nissue: {issue}\nstate: {state}\n"
                   f"branch: {branch}\nattempts: {attempts}\n---\n\nA PR record.\n")
        return rel

    def node_action(self, node: str, script: str):
        """Make the stubbed agent DO something when a given node runs.

        The stub receives `$1` = the run directory. Everything the real nodes are
        supposed to produce -- a PR record, a verdict, a triage decision -- is produced
        here instead, so the machinery around the model is exercised without one.
        """
        self.write(f".factory/fixture/{node}.sh", script)

    def stale_lock(self, name: str, pid: int = 999999, age_min: int = 600):
        """A lock whose owner is gone and whose FILE MTIME is old enough to act on.

        Both reapers select with `find -mmin`, so the age that matters is the file's,
        not the timestamp written inside it. A test that only backdates the text is
        testing nothing -- the lock is zero minutes old and correctly inside the grace
        window that guards against PID reuse.
        """
        rel = f".factory/locks-runtime/{name}"
        self.write(rel, f"{pid} 2020-01-01T00:00:00Z\n")
        old = time.time() - age_min * 60
        os.utime(self.root / rel, (old, old))

    def await_log(self, rel: str, needle: str, seconds: float = 25.0) -> str:
        """Wait for a BACKGROUNDED dispatch to write something.

        `dispatch` ends in `&`. The tick returns immediately, so reading the log without
        waiting reads an empty file and reports the dispatcher as broken.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            body = self.read(rel)
            if needle in body:
                return body
            time.sleep(0.25)
        return self.read(rel)

    def gate_log(self, rundir_rel: str, text: str):
        self.write(f"{rundir_rel}/gate.log", text)

    def verdict(self, rundir_rel: str, text: str):
        self.write(f"{rundir_rel}/verdict.json", text)


PRISTINE: Path | None = None
TMP_FOR_SUBCASES: Path | None = None
_SEQ = [0]


def unique(name: str) -> str:
    """A fixture name no other run can collide with.

    Sub-fixtures used fixed names in a temp dir shared across every mutation run, so a
    leftover from one mutation made the NEXT one fail in a completely unrelated test.
    """
    _SEQ[0] += 1
    return f"{name}-{_SEQ[0]}"


def build_pristine(dest: Path) -> Path:
    """The one real build. Everything else is a copy of this."""
    dest.mkdir(parents=True, exist_ok=True)
    f = Factory(dest)

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    for k, v in (("core.autocrlf", "false"), ("user.email", "f@f.f"),
                 ("user.name", "fixture"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "config", k, v], cwd=dest, check=True)

    src = FACTORY_SRC or (RUNNER_SRC / "factory")
    shutil.copytree(src, dest / "factory")
    shutil.rmtree(dest / "factory" / "__pycache__", ignore_errors=True)
    gi = RUNNER_SRC / ".gitignore"
    shutil.copy(gi, dest / ".gitignore") if gi.exists() else (dest / ".gitignore").write_text(
        ".factory/runs/\n.worktrees/\n", encoding="utf-8")
    for d in ("issues", ".factory/prs", ".factory/locks", ".factory/holdout",
              ".factory/fixture", "harness", "docs"):
        (dest / d).mkdir(parents=True, exist_ok=True)

    f.write("MISSION.md", """# Mission

**Derived from:** `docs/thing.prd.md` - vendored 2026-08-13.

## What it is
A fixture. It exists so the machinery can be exercised without paying for a model.

## Core capabilities (in scope)
- the widget
- the gadget

## Out of scope, forever
- No multiplayer
- No networking of any kind
- No monetisation
- No second genre
- No platforms beyond desktop
- No imported binary assets
""")
    f.write("FACTORY_RULES.md", """# Factory Rules

## 5. Protected files
`MISSION.md`, `FACTORY_RULES.md`, `CLAUDE.md`, `.factory/locks/**`, `.factory/holdout/**`,
`factory/**`

## 7. Escalation
Touch `.factory/STOP` in the repo root to halt the dispatcher.

## 8. Fix attempts
Two, then escalate.
""")
    f.write("FACTORY.md", "# The factory\n\n"
            "**Current autonomy level: 3**\n**Stop button:** `touch .factory/STOP`\n")
    f.write("CLAUDE.md", "# Conventions\nPython, stdlib only.\n")
    f.write("docs/thing.prd.md", "# PRD\nNon-goals: lots.\n")
    f.write(".factory/locks/floor.json", '{"e2e_steps_asserted": 3}\n')
    f.write("app.py", "print('app')\n")

    # A validator that always passes, emitting every required marker WITH counts.
    f.write("harness/ci.py", """import sys
print("STATIC_OK", flush=True)
print("PROTECTED_OK", flush=True)
print("UNIT_PASSED tests=9", flush=True)
if "--quick" in sys.argv:
    print("GATE_OK mode=quick", flush=True); raise SystemExit(0)
print("APP_STARTED driver=library", flush=True)
print("E2E_PASSED steps=5", flush=True)
print("HOLDOUT_PASSED scenarios=2 assertions=6", flush=True)
print("MUTATIONS_TOTAL=4", flush=True)
print("MUTATIONS_CAUGHT=4", flush=True)
print("GATE_OK mode=full", flush=True)
""")

    # The stubbed agent. It works out which node it is standing in for from the prompt
    # the runner just rendered, then runs whatever that test scripted for that node.
    f.write("factory/stub-agent.sh", """#!/usr/bin/env bash
# Stands in for the coding agent. Deterministic, free, and scriptable per node.
P="$(ls -t .factory/runs/*/nodes/*.prompt.md 2>/dev/null | head -1)"
if [ -n "$P" ]; then
  NODE="$(basename "$P" .prompt.md)"
  RUNDIR="$(dirname "$(dirname "$P")")"
  if [ -f ".factory/fixture/$NODE.sh" ]; then
    bash ".factory/fixture/$NODE.sh" "$RUNDIR" "$NODE" >&2 || {
      echo "{\\"result\\":\\"stub node refused\\",\\"total_cost_usd\\":0}"; exit 1; }
  fi
fi
echo "{\\"result\\":\\"stub\\",\\"total_cost_usd\\":0}"
exit 0
""")
    # The shebang is load-bearing now that it is invoked directly rather than via bash.
    import stat as _stat
    for _exe in ("factory/stub-agent.sh", "factory/notify.sh"):
        pass
    f.write("factory/notify.sh", """#!/usr/bin/env bash
mkdir -p .factory/notifications
cat >> .factory/notifications/feed.log
echo >> .factory/notifications/feed.log
""")

    # Point config.sh at the fakes. Everything else stays as shipped.
    # A BUILT factory's config.sh is customised by definition -- that is the file users
    # are told to edit -- so these are rewritten by pattern rather than by exact text.
    # Every project-specific value is replaced with a fake, because what is under test is
    # the machinery, not the product it happens to be building.
    cfgp = dest / "factory" / "config.sh"
    if not cfgp.exists():
        raise SystemExit(
            "this factory has no factory/config.sh, so there is nothing to point at the "
            "stubs. It predates the template that ships one; port config.sh first "
            "(scripts/_audit_runner.py --repo <repo> reports this too).")
    cfg = cfgp.read_text(encoding="utf-8")
    for var, val in (("FACTORY_BACKEND", "files"),
                     # ONE EXECUTABLE, never a command with arguments. The runner
                     # invokes it as `"$AGENT" -p ...`, so `bash ./factory/stub-agent.sh`
                     # is looked up as a single filename and fails `No such file or
                     # directory` -- the documented FACTORY_AGENT defect, reproduced
                     # inside the fixture meant to test for it. The stub never ran in ANY
                     # test: every node reported NODE_FAILED, escalate() supplied the
                     # needs-human state and the notification, and tests asserting on
                     # those passed while exercising nothing they claimed to.
                     ("FACTORY_AGENT", "./factory/stub-agent.sh"),
                     ("FACTORY_AUTONOMY", "3")):
        pat = re.compile(rf'^{var}="\$\{{{var}:-[^}}]*\}}"', re.M)
        if not pat.search(cfg):
            raise SystemExit(
                f"FIXTURE CANNOT NEUTRALISE {var}: config.sh does not define it in the "
                f'`{var}="${{{var}:-default}}"` shape this fixture rewrites. Running the '
                f"suite anyway would test a factory pointed at real models or a real "
                f"remote, so it refuses instead.")
        cfg = pat.sub(f'{var}="${{{var}:-{val}}}"', cfg, count=1)
    cfg = re.sub(r'FACTORY_NOTIFY_CMD="\$\{FACTORY_NOTIFY_CMD:-[^}]*\}"',
                 'FACTORY_NOTIFY_CMD="${FACTORY_NOTIFY_CMD:-bash factory/notify.sh}"', cfg)
    cfg = re.sub(r'FACTORY_VALIDATE_CMD="\$\{FACTORY_VALIDATE_CMD:-[^}]*\}"',
                 'FACTORY_VALIDATE_CMD="${FACTORY_VALIDATE_CMD:-python harness/ci.py}"', cfg)
    cfg = re.sub(r'FACTORY_VALIDATE_QUICK="\$\{FACTORY_VALIDATE_QUICK:-[^}]*\}"',
                 'FACTORY_VALIDATE_QUICK="${FACTORY_VALIDATE_QUICK:-python harness/ci.py --quick}"', cfg)
    cfgp.write_text(cfg, encoding="utf-8", newline="\n")

    for _exe in ("stub-agent.sh", "notify.sh"):
        _p = dest / "factory" / _exe
        _p.chmod(_p.stat().st_mode | 0o111)

    f.issue("0001-widget")
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=dest, check=True)
    return dest


def fresh(tmp: Path, name: str) -> Factory:
    dest = tmp / name
    shutil.copytree(PRISTINE, dest, symlinks=True)
    return Factory(dest)


# =============================================================================
# the test registry
# =============================================================================
TESTS: list[tuple[str, str, callable]] = []


def test(defect: str):
    """Register a test. `defect` is the failure it locks, in one line."""
    def deco(fn):
        TESTS.append((fn.__name__, defect, fn))
        return fn
    return deco


class Failed(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Failed(msg)


def has(hay: str, needle: str, what: str):
    if needle not in hay:
        raise Failed(f"{what}: expected {needle!r}\n--- got ---\n{hay[-1400:]}")


def hasnt(hay: str, needle: str, what: str):
    if needle in hay:
        raise Failed(f"{what}: did NOT expect {needle!r}\n--- got ---\n{hay[-1400:]}")


# =============================================================================
# scripted node behaviour -- what the stubbed agent DOES for a given node
# =============================================================================
# The real nodes produce artifacts: a PR record, a verdict, a triage decision. These are
# those artifacts, produced without a model, so the machinery AROUND the model is what is
# under test. `$1` is the run directory.

TRIAGE_NEEDS_HUMAN = """RUNDIR="$1"
cat > "$RUNDIR/triage.json" <<'JSON'
{"state": "needs-human", "note": "two governance statements contradict each other", "priority": "high"}
JSON
"""

TRIAGE_ACCEPT = """RUNDIR="$1"
cat > "$RUNDIR/triage.json" <<'JSON'
{"state": "accepted", "note": "in scope, the detail is decidable", "priority": "high"}
JSON
"""

TRIAGE_REJECT = """RUNDIR="$1"
cat > "$RUNDIR/triage.json" <<'JSON'
{"state": "rejected", "note": "MISSION says no networking of any kind", "priority": "low"}
JSON
"""

NODE_WRITES_A_FILE = """
printf 'def gad():\\n    return "gadded"\\n' > widget.py
"""

NODE_TOUCHES_PROTECTED = """
printf '# weakened\\n' >> factory/guard.py
"""


# =============================================================================
# GROUP A -- the dispatcher wedges. "Looks exactly like a factory with nothing to do."
# =============================================================================
# Every defect in this group presented identically: the queue stopped moving and every
# later tick printed `idle` or `at capacity`, which is indistinguishable from success.

@test("fix loop could never complete: `failed -> open` was not a legal transition, so "
      "fix-pr died mid-workflow and the dispatcher answered `idle` forever")
def test_failed_can_return_to_open(f: Factory):
    f.pr("0001-widget", state="failed", attempts=1)
    rc, out = f.py("set .factory/prs/0001-widget.md state=open")
    ok(rc == 0, f"failed -> open was refused (rc={rc}):\n{out}")
    ok(f.state_of(".factory/prs/0001-widget.md") == "open", "PR did not reach open")


@test("passed -> open deadlock: raising the floor is a commit on main, merge.sh then "
      "refuses a behind-base branch, and the documented remedy was the one move the "
      "table forbade")
def test_passed_can_requeue_to_open(f: Factory):
    f.pr("0001-widget", state="passed")
    rc, out = f.py("set .factory/prs/0001-widget.md state=open")
    ok(rc == 0, f"passed -> open was refused (rc={rc}):\n{out}")


@test("needs-human is terminal for every node: a node that could move work out of it "
      "could un-escalate its own escalation")
def test_needs_human_is_terminal_for_nodes(f: Factory):
    f.pr("0001-widget", state="needs-human")
    rc, out = f.py("set .factory/prs/0001-widget.md state=open")
    ok(rc != 0, "a node was allowed to move a PR OUT of needs-human")
    has(out, "ILLEGAL_TRANSITION", "the refusal should name itself")


@test("a same-state write is a no-op, not an error -- an escalation route that re-parks "
      "already-parked work must not fail (checked because the opposite is the obvious "
      "assumption and it is wrong)")
def test_same_state_write_is_a_noop(f: Factory):
    f.pr("0001-widget", state="needs-human")
    rc, _ = f.py("set .factory/prs/0001-widget.md state=needs-human")
    ok(rc == 0, "needs-human -> needs-human should be an accepted no-op")


@test("a `validating` PR with no run holding its lock was invisible to `next`, so a "
      "validation killed mid-flight parked the queue silently")
def test_stalled_validation_is_reported_not_idle(f: Factory):
    f.pr("0001-widget", state="validating")
    f.issue("0001-widget", state="in-progress")
    rc, out = f.py("next")
    hasnt(out, "idle", "a stalled validation must not report idle")
    has(out, "stalled", "next should report the stall")


@test("an escalated PR left its ISSUE reading `in-progress` on 2 of 3 routes, so `next` "
      "walked straight past the escalation to unrelated work")
def test_escalation_parks_the_issue_too(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="failed", attempts=2)
    f.clear_signals()
    rc, out = f.tick()
    ok(rc == 0, f"the tick died instead of escalating (rc={rc}):\n{out[-1200:]}")
    ok(f.state_of(".factory/prs/0001-widget.md") == "needs-human",
       "the PR was not parked")
    ok(f.state_of("issues/0001-widget.md") == "needs-human",
       "the ISSUE behind the escalated PR was left in-progress -- invisible as a problem")


@test("FACTORY_MAX_PARALLEL > 1 was inert: `next` names ONE target and a target already "
      "in flight consumed the whole tick, so the knob silently did nothing")
def test_max_parallel_dispatches_more_than_one(f: Factory):
    for n in ("0001-widget", "0002-gadget", "0003-gizmo"):
        f.issue(n, state="in-progress")
        f.pr(n, state="open")
    rc, out = f.tick(env={"FACTORY_MAX_PARALLEL": "3"})
    n = out.count("DISPATCH validate-pr")
    ok(n == 3, f"MAX_PARALLEL=3 dispatched {n} targets, expected 3\n{out[-1200:]}")


@test("MAX_PARALLEL=1 must still dispatch exactly one -- the loop that fixed the knob "
      "must not turn the default into a fan-out")
def test_max_parallel_one_dispatches_exactly_one(f: Factory):
    for n in ("0001-widget", "0002-gadget", "0003-gizmo"):
        f.issue(n, state="in-progress")
        f.pr(n, state="open")
    rc, out = f.tick(env={"FACTORY_MAX_PARALLEL": "1"})
    n = out.count("DISPATCH ")
    ok(n == 1, f"MAX_PARALLEL=1 dispatched {n} targets, expected 1\n{out[-1200:]}")


# =============================================================================
# GROUP B -- escalation has to reach a human. Found broken FOUR separate times.
# =============================================================================
# `needs-human` is the only state a human must act on, so it is the only state allowed to
# interrupt one. Each route below parked work correctly at some point while telling nobody.

@test("run-workflow's escalate() must park the PR, write the ledger AND notify")
def test_runner_escalation_notifies(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="failed", attempts=2)
    f.clear_signals()
    rc, out = f.run("fix-pr", ".factory/prs/0001-widget.md")
    ok(rc != 0, "hitting the fix cap should not report success")
    has(f.ledger(), "0001-widget", "the needs-human ledger was not written")
    has(f.notifications(), "needs a human", "nobody was notified of the fix-cap stop")


@test("the orchestrator's fix-cap branch reached nobody: an unguarded state write above "
      "the notify meant any failure skipped the ledger AND the notification")
def test_orchestrator_cap_branch_notifies(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="failed", attempts=2)
    f.clear_signals()
    rc, out = f.tick()
    ok(rc == 0, f"the tick died rather than escalating:\n{out[-1000:]}")
    has(f.notifications(), "needs a human", "the fix cap notified nobody")


@test("a CORRECT triage decision of needs-human reached nobody: factory_notify was only "
      "reachable from escalate(), which fires on runner FAULTS, and a correct decision "
      "is not a fault")
def test_triage_needs_human_notifies(f: Factory):
    f.issue("0009-unclear", state="untriaged")
    # The node is called `sort`, not `triage` -- the WORKFLOW is triage, the NODE inside
    # it is sort. Scripting the wrong name means the stub does nothing, the node writes no
    # decision, and the run escalates as a FAULT: needs-human is reached and a notification
    # is sent, so a test asserting only those two things passes while never once
    # exercising the triage decision it claims to cover.
    f.node_action("sort", TRIAGE_NEEDS_HUMAN)
    f.clear_signals()
    rc, out = f.run("triage", "issues/0009-unclear.md")
    ok(f.state_of("issues/0009-unclear.md") == "needs-human",
       f"triage did not park the issue:\n{out[-1000:]}")
    has(f.notifications(), "(triage)",
        "a correct triage stop told nobody -- two correct stops, silence")
    # NOT merely "needs a human": escalate() emits that too, so the weaker assertion is
    # satisfied by any runner FAULT during the run and cannot tell the two apart. That is
    # exactly how this test passed while the triage notification was deleted.
    hasnt(out, "ESCALATE:", "the run FAULTED; this must be a clean triage decision")
    has(out, "TRIAGED", "triage never recorded a decision")


@test("a merge refused on the ORCHESTRATOR route killed the tick silently: reached from "
      "gate.sh it is `|| fail` and notifies, reached from `next` it notified nobody")
def test_orchestrator_merge_failure_notifies(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="passed", branch="factory/does-not-exist")
    f.clear_signals()
    rc, out = f.tick()
    ok(rc == 0, f"a refused merge killed the whole tick (rc={rc}):\n{out[-1200:]}")
    has(out, "MERGE_FAILED", "the refusal was not named")
    ok(f.state_of(".factory/prs/0001-widget.md") == "needs-human", "the PR was not parked")
    has(f.notifications(), "merge refused", "a refused merge notified nobody")


@test("the stalled-validation sweep must notify, not just relabel")
def test_stalled_sweep_notifies(f: Factory):
    f.pr("0001-widget", state="validating")
    f.issue("0001-widget", state="in-progress")
    f.clear_signals()
    rc, out = f.tick()
    has(f.notifications(), "a validation died", "the stall sweep notified nobody")


@test("a clean tick must stay SILENT -- an escalation channel that fires on nothing is "
      "one a human learns to ignore")
def test_clean_tick_is_silent(f: Factory):
    f.clear_signals()
    rc, out = f.tick()
    ok(f.notifications() == "", f"a clean tick notified: {f.notifications()!r}")
    ok(f.ledger() == "", f"a clean tick wrote the ledger: {f.ledger()!r}")


# =============================================================================
# GROUP C -- the silent-death class. `set -e` kills the script before the escalate.
# =============================================================================
# Found and fixed FOUR times as individual instances before anyone looked for the shape.
# The tell is always the same: exit 1, no message, no needs-human, no notification, and
# the work still dispatchable -- so the next tick runs the same doomed workflow again.

@test("an issue with no `title:` line killed implement-issue at the grep that read it, "
      "BEFORE the issue moved to in-progress, so the dispatcher re-ran a doomed workflow "
      "every tick forever")
def test_untitled_issue_does_not_kill_the_runner(f: Factory):
    f.issue("0007-untitled", state="accepted", title=None)
    f.node_action("implement", NODE_WRITES_A_FILE)
    rc, out = f.run("implement-issue", "issues/0007-untitled.md")
    has(out, "PREFLIGHT_OK", "never got as far as the pre-flight")
    ok("NODE prime" in out or "NODE plan" in out or "NODE implement" in out,
       f"the run died before reaching any build node -- the title grep is still fatal:\n{out[-1500:]}")


@test("an unguarded command failing under `set -e` produced exit 1 and NOTHING else: no "
      "state change, no ledger, no notification, and the orchestrator discarded the "
      "runner's exit status so nothing downstream noticed either")
def test_unguarded_failure_escalates_loudly(f: Factory):
    f.issue("0001-widget", state="accepted")
    # Inject a failing command at top level, after the ERR trap is installed.
    p = f.root / "factory" / "run-workflow.sh"
    s = p.read_text(encoding="utf-8")
    needle = 'log "PREFLIGHT_OK'
    ok(needle in s, "run-workflow.sh no longer logs PREFLIGHT_OK; the probe needs updating")
    s = s.replace(needle, 'grep -q "NO_SUCH_TOKEN_IN_THIS_FILE" factory/config.sh\n' + needle, 1)
    p.write_text(s, encoding="utf-8", newline="\n")

    f.clear_signals()
    rc, out = f.run("implement-issue", "issues/0001-widget.md")
    has(out, "RUNNER_FAULT", "an unguarded death said nothing about itself")
    has(out, "NO_SUCH_TOKEN_IN_THIS_FILE", "the fault did not name the failing command")
    ok(f.state_of("issues/0001-widget.md") == "needs-human",
       "an unguarded death left the work dispatchable -- it will be re-run every tick")
    has(f.notifications(), "needs a human", "an unguarded death notified nobody")


@test("the orchestrator dispatches the runner into a background subshell and never read "
      "its exit status, so a runner fault left no trace the dispatcher could see")
def test_orchestrator_records_runner_faults(f: Factory):
    f.issue("0001-widget", state="accepted")
    p = f.root / "factory" / "run-workflow.sh"
    s = p.read_text(encoding="utf-8")
    # Die BEFORE the ERR trap is installed, so only the dispatcher's backstop can catch it.
    s = s.replace("set -euo pipefail",
                  "set -euo pipefail\ngrep -q NO_SUCH_TOKEN_EARLY factory/config.sh", 1)
    p.write_text(s, encoding="utf-8", newline="\n")

    rc, out = f.tick()
    # `dispatch` backgrounds the runner (`&`), so the tick returns before the subshell
    # has written anything. Waiting for the log is part of testing a dispatcher at all.
    log = f.await_log("factory-implement-issue-issues-0001-widget-md.log", "RUNNER_FAULT")
    has(log, "RUNNER_FAULT",
        "the dispatcher lost a runner fault entirely -- nothing downstream can see it")
    has(log, "WILL be dispatched again",
        "the fault did not say the work is still dispatchable, which is the whole risk")


@test("the ORCHESTRATOR is the scheduled entry point and nothing supervises it: an "
      "unguarded failure there loses the whole tick -- the reaper, the sweep and every "
      "dispatch after it -- and no exit code goes anywhere anyone looks")
def test_dispatcher_fault_is_loud(f: Factory):
    p = f.root / "factory" / "orchestrator.sh"
    s = p.read_text(encoding="utf-8")
    needle = "# 1. THE STOP BUTTON"
    ok(needle in s, "orchestrator.sh changed shape; this probe needs updating")
    s = s.replace(needle, 'grep -q "NO_SUCH_DISPATCHER_TOKEN" factory/config.sh\n' + needle, 1)
    p.write_text(s, encoding="utf-8", newline="\n")

    f.clear_signals()
    rc, out = f.tick()
    has(out, "DISPATCHER_FAULT", "the dispatcher died without saying anything about it")
    has(out, "NO_SUCH_DISPATCHER_TOKEN", "the fault did not name the failing command")
    has(f.notifications(), "the dispatcher itself failed",
        "a dead dispatcher notified nobody -- the one failure nothing else can report")


# =============================================================================
# GROUP D -- the gate. "Empty is not pass."
# =============================================================================
# The gate is one of the two places a decision is made by code a model cannot talk past.
# Every check must be a POSITIVE assertion with a count. A check that never ran produces
# no failures, and "did anything fail?" reads that as success.

GOOD_LOG = ("STATIC_OK\nPROTECTED_OK\nUNIT_PASSED tests=9\nAPP_STARTED driver=library\n"
            "E2E_PASSED steps=5\nHOLDOUT_PASSED scenarios=2 assertions=6\n"
            "MUTATIONS_TOTAL=4\nMUTATIONS_CAUGHT=4\nGATE_OK mode=full\n")


def gate(f: Factory, log: str, verdict: str, pr_state="validating", ident="0001-widget",
         branch=True):
    """Run the real gate against a synthesised run.

    THE BRANCH IS CREATED FOR REAL, and that is not a detail. Without it every gate run
    ends the same way -- the gate decides, then `merge.sh` refuses a branch that does not
    exist, and the script exits non-zero with `GATE_FAIL: merge failed`. A refusal test
    asserting only `rc != 0` and `GATE_FAIL` is then satisfied by the MISSING BRANCH rather
    than by the thing it claims to test.

    That is not hypothetical: `--mutate` disabled the required-marker check entirely and
    `test_gate_requires_positive_markers` stayed green, because the gate passed the markers
    exactly as the mutation intended and then died on the absent branch. The test had never
    tested markers at all. Every refusal test below now also asserts the SPECIFIC reason,
    for the same reason the gate itself demands positive markers: "something failed" is not
    evidence that the right thing failed.
    """
    # THE BRANCH IS MADE FIRST, AND STAGES ONLY THE CODE FILE. `issues/*.md` and
    # `.factory/prs/*.md` are TRACKED state on the file backend, so a `git add -A` on the
    # branch commits them there and `git checkout main` then deletes the PR record from the
    # working tree -- every later `state.py get` fails on a missing file. Writing the
    # records after the branch exists, and staging only `widget.py`, keeps the state where
    # the gate expects to find it.
    if branch:
        f.sh(f"git checkout -q -b factory/{ident} && "
             f"printf 'def gad():\\n    return 1\\n' > widget.py && "
             f"git add widget.py && git commit -q -m 'factory: work' && "
             f"git checkout -q main")
    f.issue(ident, state="in-progress")
    f.pr(ident, state=pr_state)
    rd = ".factory/runs/t"
    f.gate_log(rd, log)
    f.verdict(rd, verdict)
    f.clear_signals()
    rc, out = f.sh(f"bash factory/gate.sh .factory/prs/{ident}.md "
                   f"{rd}/gate.log {rd}/verdict.json")
    return rc, out


def refused_for(out: str, reason: str, what: str):
    """A refusal must name ITS OWN cause, not merely be a refusal."""
    has(out, "GATE_FAIL", f"{what}: the gate did not refuse at all")
    if reason not in out:
        raise Failed(f"{what}: the gate refused, but for the wrong reason. "
                     f"Expected {reason!r}.\n--- got ---\n{out[-1200:]}")


@test("empty is not pass: a required marker missing from the run log must BLOCK, because "
      "a check that did not report that it ran is not a check that passed")
def test_gate_requires_positive_markers(f: Factory):
    # PROTECTED_OK and not E2E_PASSED: dropping E2E_PASSED also drops `steps=5`, so the
    # run fails the e2e FLOOR and the marker check is never reached. This test passed for
    # the wrong reason until `--mutate` disabled the marker check and it stayed green.
    log = GOOD_LOG.replace("PROTECTED_OK\n", "")
    rc, out = gate(f, log, '{"verdict":"approve"}')
    ok(rc != 0, f"the gate passed a run with a required marker absent:\n{out[-900:]}")
    refused_for(out, "required marker(s) absent", "a missing marker")
    ok(f.state_of(".factory/prs/0001-widget.md") == "needs-human", "the PR was not parked")


@test("the RAW LOG beats the verdict: a judge approving a run whose log says GATE_FAILED "
      "must not merge -- a model summarising its own run is exactly what cannot be "
      "trusted at this step")
def test_gate_log_beats_an_approving_judge(f: Factory):
    rc, out = gate(f, GOOD_LOG + "GATE_FAILED: unit\n", '{"verdict":"approve"}')
    ok(rc != 0, f"an approving verdict overrode a failed log:\n{out[-900:]}")
    refused_for(out, "the suite stopped at the 'unit' step", "a failed step in the log")


@test("a malformed verdict must FAIL CLOSED -- not JSON, no verdict key, wrong type, "
      "empty file: 14 shapes were tried and every one has to refuse")
def test_gate_fails_closed_on_malformed_verdicts(f: Factory):
    shapes = ['not json at all', '{}', '{"verdict":null}', '{"verdict":123}',
              '{"verdict":["approve"]}', '{"verdict":{"x":1}}', '',
              '   ', '{"verdict":"APPROVE",}', 'prose {"verdict":"approve"}']
    for i, v in enumerate(shapes):
        g = fresh(TMP_FOR_SUBCASES, unique(f"verdict-{i}"))
        try:
            rc, out = gate(g, GOOD_LOG, v)
            ok(rc != 0, f"verdict {v!r} did not fail closed (rc={rc}):\n{out[-500:]}")
            # It must fail on the VERDICT, not somewhere downstream. Three distinct and
            # all-correct branches reach that: an empty file, an unparseable one, and a
            # parseable one carrying a verdict nothing recognises (`{"verdict": null}` is
            # valid JSON with the field present, so it lands on the last of the three).
            ok(any(k in out for k in ("verdict file is", "not parseable", "unknown verdict")),
               f"verdict {v!r} was refused for the wrong reason:\n{out[-700:]}")
            ok(g.state_of(".factory/prs/0001-widget.md") == "needs-human",
               f"verdict {v!r} left the PR unparked")
        finally:
            shutil.rmtree(g.root, ignore_errors=True)


@test("the e2e floor is a ratchet: a run asserting fewer steps than the recorded floor "
      "must block, because skipped is not passed")
def test_gate_enforces_the_e2e_floor(f: Factory):
    log = GOOD_LOG.replace("E2E_PASSED steps=5", "E2E_PASSED steps=1")
    rc, out = gate(f, log, '{"verdict":"approve"}')
    ok(rc != 0, f"the gate accepted a run below the e2e floor:\n{out[-900:]}")
    refused_for(out, "asserted only 1 of 3 steps", "a run below the e2e floor")


@test("mutation score is a gate, not a report: a run that caught fewer defects than it "
      "injected must block")
def test_gate_enforces_the_mutation_score(f: Factory):
    log = GOOD_LOG.replace("MUTATIONS_CAUGHT=4", "MUTATIONS_CAUGHT=1")
    rc, out = gate(f, log, '{"verdict":"approve"}')
    ok(rc != 0, f"the gate accepted a run that missed injected defects:\n{out[-900:]}")
    refused_for(out, "caught 1 of 4 deliberate defects", "a missed mutation")


@test("a recorded ASSUMPTION holds the auto-merge without stopping the work -- the "
      "mechanism that lets the factory decide product values and still ask a human")
def test_recorded_assumption_holds_the_merge(f: Factory):
    f.write(".factory/assumptions/0001-widget.txt",
            "AWAY_WEEK_CAP=3 - derived from the issue text; CHANGE IF a household "
            "reports needing four.\n")
    rc, out = gate(f, GOOD_LOG, '{"verdict":"approve"}')
    has(out, "auto-merge", "the assumption did not appear in the gate's reasoning")
    ok(f.state_of(".factory/prs/0001-widget.md") != "merged",
       "a change resting on an unreviewed assumption was auto-merged")


@test("a green gate with a clean judge and no assumptions must actually PASS AND MERGE "
      "-- a gate that refuses everything is not a gate, and every refusal test above "
      "would pass against one")
def test_gate_passes_and_merges_a_clean_run(f: Factory):
    rc, out = gate(f, GOOD_LOG, '{"verdict":"approve"}')
    has(out, "GATE_PASS", "a clean run did not pass the gate")
    hasnt(out, "GATE_FAIL", f"a clean run was refused:\n{out[-900:]}")
    ok(f.state_of(".factory/prs/0001-widget.md") == "merged",
       f"a clean run passed the gate but never merged:\n{out[-900:]}")
    ok(f.state_of("issues/0001-widget.md") == "done",
       "the issue behind a merged PR was not closed out")


# =============================================================================
# GROUP E -- the safety properties. Each is claimed in writing somewhere.
# =============================================================================

@test("the stop button must halt the dispatcher before anything is dispatched")
def test_stop_file_halts_the_dispatcher(f: Factory):
    f.write(".factory/STOP", "")
    rc, out = f.tick()
    hasnt(out, "DISPATCH ", "work was dispatched with the stop file present")
    has(out, "STOP", "the halt was not announced")


@test("autonomy 0 is how you pause a factory: nothing may dispatch")
def test_autonomy_zero_dispatches_nothing(f: Factory):
    rc, out = f.tick(env={"FACTORY_AUTONOMY": "0"})
    hasnt(out, "DISPATCH ", "work was dispatched at autonomy 0")


@test("autonomy 2 means a human still merges: a passed PR must be HELD, not merged")
def test_autonomy_two_holds_the_merge(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="passed")
    rc, out = f.tick(env={"FACTORY_AUTONOMY": "2"})
    has(out, "HOLD merge", "a passed PR was not held at autonomy 2")
    ok(f.state_of(".factory/prs/0001-widget.md") == "passed",
       "the PR moved past `passed` at autonomy 2")


@test("the protected-path guard runs from the BASE checkout, so a branch cannot supply "
      "the guard that judges it")
def test_guard_blocks_a_branch_touching_factory(f: Factory):
    f.sh("git checkout -q -b factory/evil && "
         "printf '# weakened\\n' >> factory/guard.py && "
         "git add -A && git commit -q -m 'weaken the guard' && git checkout -q main")
    rc, out = f.sh("python factory/guard.py --base main --head factory/evil")
    ok(rc != 0, f"the guard allowed a branch to edit factory/**:\n{out[-800:]}")


@test("the guard must not be blind inside a NEW directory -- `git status --porcelain` "
      "collapses an untracked directory to one entry and hides what is in it")
def test_guard_sees_inside_new_directories(f: Factory):
    f.sh("git checkout -q -b factory/sneaky && mkdir -p factory/nested && "
         "printf 'x\\n' > factory/nested/thing.py && "
         "git add -A && git commit -q -m 'nested' && git checkout -q main")
    rc, out = f.sh("python factory/guard.py --base main --head factory/sneaky")
    ok(rc != 0, f"the guard missed a file inside a new protected directory:\n{out[-800:]}")


@test("a factory still asserting the template's sample product is an unedited scaffold "
      "and must not be treated as configured")
def test_doctor_detects_an_unedited_scaffold(f: Factory):
    rc, out = f.sh(f'python "{(SKILL / "scripts" / "factory_doctor.py").as_posix()}" '
                   f'--repo "{f.root.as_posix()}"')
    ok("FAIL" in out or "WARN" in out or rc != 0,
       "factory_doctor reported a bare fixture as fully configured")


# =============================================================================
# GROUP F -- locks. A wedged dispatcher reports "at capacity" forever.
# =============================================================================

@test("two orchestrators must not both dispatch the same target: `[ -e ]` then `>` is "
      "TOCTOU, and both dispatched validate-pr on the same PR")
def test_concurrent_orchestrators_dispatch_once(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="open")
    rc, out = f.sh("for i in 1 2 3 4 5 6; do bash factory/orchestrator.sh & done; wait")
    n = out.count("DISPATCH validate-pr")
    ok(n == 1, f"{n} orchestrators dispatched the same target, expected 1\n{out[-1200:]}")


@test("a lock outlives its process on any kill -- reboot, sleep, closed terminal. It was "
      "counted toward capacity FOREVER: `at capacity (1/1)` on every later tick")
def test_stale_lock_is_reaped(f: Factory):
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="open")
    # A lock naming a PID that cannot be running, well past the grace window.
    f.stale_lock("validate-pr--factory-prs-0001-widget-md.lock")
    rc, out = f.tick()
    has(out, "LOCK_REAPED", f"a dead lock was not reaped:\n{out[-1200:]}")


@test("the reaper must sit ABOVE the autonomy gate: at dial 0 -- how you pause a factory "
      "-- nothing was ever reaped, so pausing it guaranteed it stayed wedged")
def test_stale_lock_is_reaped_even_at_autonomy_zero(f: Factory):
    f.stale_lock("validate-pr--factory-prs-0001-widget-md.lock")
    rc, out = f.tick(env={"FACTORY_AUTONOMY": "0"})
    has(out, "LOCK_REAPED", "no lock is reaped while the factory is paused")


@test("a LIVE lock must be left alone -- a reaper that cannot tell a running validation "
      "from a dead one is worse than no reaper")
def test_live_lock_is_not_reaped(f: Factory):
    import os as _os
    f.issue("0001-widget", state="in-progress")
    f.pr("0001-widget", state="open")
    f.write(".factory/locks-runtime/validate-pr--factory-prs-0001-widget-md.lock",
            f"{_os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    rc, out = f.tick()
    hasnt(out, "LOCK_REAPED", "a live lock was reaped out from under its run")


@test("a hand-driven run-workflow.sh took NO lock, while Phase 7 tells you to run laps "
      "by hand: a cron tick raced a hand-run of the same target by 17 seconds")
def test_hand_run_takes_its_own_lock(f: Factory):
    f.issue("0001-widget", state="accepted")
    f.write(".factory/locks-runtime/implement-issue-issues-0001-widget-md.lock",
            f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    rc, out = f.run("implement-issue", "issues/0001-widget.md")
    ok(rc != 0, "a hand-run ignored a lock already held on its target")
    has(out, "already in flight", "the refusal did not explain itself")



# =============================================================================
# GROUP G -- the GitHub backend, in process.
# =============================================================================
# The GitHub backend is the DEFAULT: `state.py` selects it wherever an `origin` remote
# exists. It was also the only half of the state layer with no test of any kind, because
# the fixture above runs on the file backend.
#
# Tested by importing the module and replacing `gh()` with a recorder, rather than by
# faking a `gh` binary: on Windows `subprocess` resolves a bare name through CreateProcess,
# which appends only `.exe` and ignores PATHEXT -- the same fact behind the `npm` shim
# defect -- so a shell script called `gh` would never be found. Replacing the one function
# that shells out tests the DECISIONS, which is where every defect here has been.

def load_gh(f: Factory):
    """Import the fixture's own copy of gh_backend, with `gh` replaced by a recorder.

    Returns (module, calls) where `calls` is the list of argument tuples the module tried
    to run. `module.RESPONSES` maps a call prefix to canned JSON.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"ghb_{f.root.name}", f.root / "factory" / "gh_backend.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    calls: list[tuple] = []
    responses: dict = {}
    failures: dict = {}

    def fake_gh(*args: str) -> str:
        calls.append(tuple(args))
        for prefix, err in failures.items():
            if tuple(args[:len(prefix)]) == prefix:
                raise m.GhError(err)
        for prefix, body in responses.items():
            if tuple(args[:len(prefix)]) == prefix:
                return body
        return ""

    m.gh = fake_gh
    m.gh_json = lambda *a: __import__("json").loads(fake_gh(*a) or "null")
    m._REPO = "acme/widget"
    return m, calls, responses, failures


def _issue(number=1, state="OPEN", labels=(), title="an issue", reason=None):
    return {"number": number, "title": title, "body": "b", "state": state,
            "stateReason": reason, "createdAt": "2026-01-01T00:00:00Z",
            "author": {"login": "cole"},
            "labels": [{"name": n} for n in labels]}


@test("GitHub label -> state mapping: the labels ARE the state on this backend, so a "
      "misread label is a misread state machine")
def test_gh_issue_state_reads_labels(f: Factory):
    m, _, _, _ = load_gh(f)
    ok(m.issue_state(_issue(labels=["factory:accepted"])) == "accepted", "accepted misread")
    ok(m.issue_state(_issue(labels=["factory:in-progress"])) == "in-progress",
       "in-progress misread")
    ok(m.issue_state(_issue(labels=[])) == "untriaged",
       "an unlabelled open issue is untriaged")
    # `done` is `factory:approved`, NOT `factory:done`. Several states deliberately share
    # a label (done/passed/merged are all `factory:approved`), so the mapping is worth
    # asserting rather than assuming -- reading it off the state name is wrong.
    ok(m.issue_state(_issue(state="CLOSED", labels=["factory:approved"])) == "done",
       "a closed issue with a disposition label must read as that disposition")


@test("a closed issue with NO disposition label must NOT be guessed: guessing is how a "
      "deferred roadmap item becomes a permanent rejection")
def test_gh_closed_without_disposition_is_not_guessed(f: Factory):
    m, _, _, _ = load_gh(f)
    st = m.issue_state(_issue(state="CLOSED", labels=[]))
    ok(st == "closed-unlabelled",
       f"a closed issue with no disposition read as {st!r} -- a guess the code refuses to make")


@test("a merge cannot be un-labelled: the native GitHub state must beat any label, or a "
      "stale label makes the factory try to re-merge something already on main")
def test_gh_merged_beats_labels(f: Factory):
    m, _, _, _ = load_gh(f)
    pr = {"number": 4, "title": "p", "body": "", "state": "OPEN",
          "mergedAt": "2026-01-02T00:00:00Z",
          "labels": [{"name": "factory:validating"}]}
    ok(m.pr_state(pr) == "merged", "a merged PR was read from its label, not from GitHub")


@test("`gh edit --add-label X --remove-label Y` is NOT atomic: when the add fails the "
      "remove still lands, leaving the item with NO state label, read back as `untriaged` "
      "-- a state it was never in. Proven on a live repo.")
def test_gh_relabel_adds_before_removing(f: Factory):
    m, calls, _, _ = load_gh(f)
    m._relabel("issue", 3, ["factory:accepted"], ["factory:in-progress"],
               ["factory:accepted"])
    edits = [c for c in calls if len(c) > 1 and c[1] == "edit"]
    ok(len(edits) == 2,
       f"expected TWO calls (add, then remove); got {len(edits)}: {edits}")
    ok("--add-label" in edits[0], f"the first call must ADD: {edits[0]}")
    ok("--remove-label" in edits[1], f"the second call must REMOVE: {edits[1]}")
    ok("--remove-label" not in edits[0],
       f"add and remove in one call is the non-atomic form: {edits[0]}")


@test("when the ADD fails, NOTHING may be removed -- the item keeps its old state and the "
      "caller sees the error, instead of silently losing its place in the pipeline")
def test_gh_failed_add_removes_nothing(f: Factory):
    m, calls, _, failures = load_gh(f)
    failures[("issue", "edit")] = "label 'factory:in-progress' not found"
    try:
        m._relabel("issue", 3, ["factory:accepted"], ["factory:in-progress"],
                   ["factory:accepted"])
    except Exception:
        pass
    removes = [c for c in calls if "--remove-label" in c]
    ok(not removes,
       f"the add failed and a remove still went out, orphaning the item: {removes}")


@test("the remote stop button must FAIL CLOSED: an unreadable stop state is a STOP, "
      "because a stop button that works only while the network does is not a stop button")
def test_gh_stop_fails_closed(f: Factory):
    m, _, _, failures = load_gh(f)
    failures[("issue", "list")] = "HTTP 401: Bad credentials"
    stopped, why = m.stop_requested()
    ok(stopped is True, "an unreadable stop state was treated as 'not stopped'")
    has(why, "cannot read the stop state", "the halt did not explain itself")


@test("a malformed target must be refused rather than coerced -- `gh:issue:3` is the only "
      "shape, and guessing at anything else addresses the wrong item")
def test_gh_target_parsing_is_strict(f: Factory):
    m, _, _, _ = load_gh(f)
    ok(m.parse_target("gh:issue:3") == ("issue", 3), "the valid shape was rejected")
    for bad in ("gh:issue:", "gh:thing:3", "issues/0001.md", "gh:issue:3x", "", "gh:pr:-1"):
        try:
            m.parse_target(bad)
            raise Failed(f"{bad!r} was accepted as a GitHub target")
        except ValueError:
            pass


@test("every state the factory can write must have a label, or the first write of that "
      "state fails against a live repo -- `factory:approved` was missing exactly this way")
def test_gh_every_state_has_a_label(f: Factory):
    m, _, _, _ = load_gh(f)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"st_{f.root.name}", f.root / "factory" / "state.py")
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    # `untriaged` and `closed-unlabelled` are the ABSENCE of a label, by design: an issue
    # with no state label is untriaged, and one closed with no disposition is exactly the
    # thing the code refuses to guess about. Every other state must be writable.
    absence = {"untriaged", "closed-unlabelled"}
    missing = sorted(set(st.TRANSITIONS) - set(m.LABEL_FOR_STATE) - absence)
    ok(not missing,
       f"states with no GitHub label: {missing} -- writing one fails on a live repo")
    for st_name in absence:
        ok(st_name not in m.LABEL_FOR_STATE,
           f"{st_name} must stay label-less; it means the absence of one")


# =============================================================================
# GROUP H -- the validation harness scaffold.
# =============================================================================
# `templates/harness/` is the SECOND thing copied into every repo, and it decides whether
# a gate is green because everything passed or green because nothing ran. Its historical
# defects are all that one shape: a holdout that did not exist, a mutation set that never
# executed, an e2e rung that hung forever with no timeout, a unit suite that discovered
# zero tests and exited 0 looking perfect.
#
# The fixture installs the REAL harness over the stub, with a `library` driver: no ports,
# nothing to bind, nothing to pop a window while somebody is recording.

HARNESS_SRC = TEMPLATES / "harness"

E2E_TRIVIAL = '''STEPS = 0


def run_e2e(app):
    """A journey with no scaffold marker in it, so the doctor's check is not the subject."""
    global STEPS
    STEPS = 3
    return STEPS
'''

E2E_HANGS = '''import time


def run_e2e(app):
    time.sleep(600)          # the shape of a browser CLI blocking on a pipe forever
    return 1
'''

E2E_FAILS = '''def run_e2e(app):
    return None              # a journey that could not be completed
'''


def install_harness(f: Factory, e2e: str = E2E_TRIVIAL, unit_tests: int = 9,
                    **config):
    """Put the REAL harness in the fixture, with a library driver and a chosen e2e."""
    dest = f.root / "harness"
    for name in ("ci.py", "appproc.py", "harness.config.json"):
        shutil.copy(HARNESS_SRC / name, dest / name)
    (dest / "e2e.py").write_text(e2e, encoding="utf-8", newline="\n")

    import json
    cfg = json.loads((HARNESS_SRC / "harness.config.json").read_text(encoding="utf-8"))
    cfg["driver"] = "library"
    cfg["library"] = {"import_check": "python -c \"import app\""}
    cfg["static"] = "python harness/_static.py"
    cfg["unit"] = "python harness/_unit.py"
    cfg["unit_count_pattern"] = r"Ran (\d+) test"
    cfg.update(config)
    (dest / "harness.config.json").write_text(json.dumps(cfg, indent=2),
                                              encoding="utf-8", newline="\n")
    # Tiny real scripts rather than `python -c "..."`: a one-liner has to survive JSON
    # escaping, shlex.split and the shell, and every layer of that is a way for a test to
    # fail for a reason that has nothing to do with what it is testing.
    (dest / "_static.py").write_text("pass\n", encoding="utf-8", newline="\n")
    (dest / "_unit.py").write_text(
        f"print('Ran {unit_tests} tests')\n", encoding="utf-8", newline="\n")


def ci(f: Factory, *args, env=None, timeout=120):
    return f.sh(f'"{sys.executable}" harness/ci.py {" ".join(args)}',
                env=env, timeout=timeout)


@test("a gate with NO holdout must say so: without one, nothing above the independence "
      "line ran and every check is one the builder could read and iterate against")
def test_harness_reports_an_absent_holdout(f: Factory):
    install_harness(f)
    rc, out = ci(f)
    has(out, "HOLDOUT_ABSENT",
        "a gate with no holdout reported nothing about it -- green because nothing ran")


@test("a gate with NO mutation set must say so: a gate that has never been shown to fail "
      "is a gate nobody has tested")
def test_harness_reports_an_absent_mutation_set(f: Factory):
    install_harness(f)
    rc, out = ci(f)
    has(out, "MUTATIONS_ABSENT", "a gate with no mutation set claimed nothing about it")


@test("ZERO TESTS IS NOT A PASS: a suite that discovered nothing exits 0 and looks "
      "perfect. Both independent builds of this file added this guard unprompted.")
def test_harness_refuses_a_zero_test_suite(f: Factory):
    install_harness(f, unit_tests=0)
    rc, out = ci(f)
    ok(rc != 0, f"a suite that ran 0 tests was accepted:\n{out[-700:]}")
    has(out, "UNIT_ERROR", "the refusal did not name itself")
    hasnt(out, "GATE_OK", "a zero-test run reached GATE_OK")


@test("an unconfigured rung must be skipped LOUDLY -- a silent skip is indistinguishable "
      "from a pass, which is the whole failure this harness exists to prevent")
def test_harness_skips_loudly(f: Factory):
    install_harness(f, static="")
    rc, out = ci(f)
    has(out, "STATIC_SKIPPED", "an unconfigured rung passed in silence")


@test("a failing rung must be NAMED: the last line of output is usually several rungs "
      "downstream of the cause, and misnaming your own failure is most of the cost")
def test_harness_names_the_failing_rung(f: Factory):
    install_harness(f, static="python harness/_boom.py")
    (f.root / "harness" / "_boom.py").write_text("raise SystemExit(1)\n",
                                                 encoding="utf-8", newline="\n")
    rc, out = ci(f)
    ok(rc != 0, "a failing rung did not fail the gate")
    has(out, "GATE_FAILED: static", "the gate did not name which rung stopped it")


@test("the e2e rung is called IN PROCESS, so nothing upstream can interrupt it. It was "
      "the rung most likely to hang and the only one with no timeout: the gate printed "
      "APP_STARTED and then nothing, all night, holding its dispatch lock.")
def test_harness_watchdog_kills_a_hanging_e2e(f: Factory):
    install_harness(f, e2e=E2E_HANGS, e2e_timeout_s=3)
    t0 = time.time()
    rc, out = ci(f, timeout=90)
    elapsed = time.time() - t0
    ok(rc != 0, "a hanging e2e rung did not fail the gate")
    has(out, "E2E_TIMEOUT", "the hang was not named")
    ok(elapsed < 60, f"the watchdog took {elapsed:.0f}s to fire on a 3s timeout")


@test("the watchdog must stay silent on a normal run -- a deadline that fires on healthy "
      "runs is one somebody raises until it never fires at all")
def test_harness_watchdog_is_silent_when_healthy(f: Factory):
    install_harness(f, e2e_timeout_s=60)
    rc, out = ci(f)
    hasnt(out, "E2E_TIMEOUT", "the watchdog fired on a healthy run")
    has(out, "E2E_PASSED", "a healthy e2e did not report passing")


@test("an e2e that returns no completed journey must FAIL, not report zero steps and "
      "carry on")
def test_harness_fails_on_an_incomplete_journey(f: Factory):
    install_harness(f, e2e=E2E_FAILS)
    rc, out = ci(f)
    ok(rc != 0, "an e2e that completed no journey was accepted")
    has(out, "GATE_FAILED: e2e", "the failure was not attributed to the e2e rung")


@test("the mutation runner copies harness/ into each throwaway build, so without a "
      "recursion guard the inner gate re-runs everything: 6 defects becomes 36 gate runs "
      "and the score is misattributed")
def test_harness_does_not_recurse_into_mutations(f: Factory):
    install_harness(f)
    rc, out = ci(f, env={"FACTORY_IN_MUTATION": "1"})
    has(out, "MUTATIONS_SKIPPED", "a mutation build re-ran the mutation rung")


@test("--quick is a STRICT subset the builder runs on itself: it must stop before the "
      "independent rungs, because nothing downstream trusts it and the full gate re-runs "
      "everything anyway")
def test_harness_quick_is_a_strict_subset(f: Factory):
    install_harness(f)
    rc, out = ci(f, "--quick")
    ok(rc == 0, f"the quick gate failed on a healthy repo:\n{out[-600:]}")
    has(out, "GATE_OK mode=quick", "quick mode did not report itself")
    for absent in ("E2E_PASSED", "HOLDOUT", "MUTATIONS"):
        hasnt(out, absent, f"quick mode ran {absent}, so it is not a subset")


@test("a command whose interpreter path is QUOTED must still run. `shlex.split(posix="
      "False)` keeps backslashes in Windows paths -- correctly -- but it also keeps the "
      "QUOTES attached to the token, so `shutil.which` never matched and the rung died "
      "with the exact [WinError 2] that resolve() exists to prevent. Quoting is not "
      "optional for a path containing a space, and Program Files is where Windows puts "
      "things.")
def test_harness_runs_a_quoted_interpreter_path(f: Factory):
    install_harness(f, static=f'"{sys.executable}" harness/_static.py')
    rc, out = ci(f)
    hasnt(out, "could not run",
          f"a quoted interpreter path was unrunnable:\n{out[-700:]}")
    has(out, "STATIC_OK", "the rung with a quoted interpreter path did not pass")


@test("a full healthy run must reach GATE_OK and emit every marker the gate requires by "
      "default -- if it cannot, FACTORY_REQUIRED_MARKERS blocks every PR out of the box")
def test_harness_healthy_run_emits_the_required_markers(f: Factory):
    install_harness(f)
    rc, out = ci(f)
    ok(rc == 0, f"a healthy repo did not pass its own gate:\n{out[-800:]}")
    # The shipped default of FACTORY_REQUIRED_MARKERS.
    for marker in ("APP_STARTED", "E2E_PASSED", "GATE_OK"):
        has(out, marker, f"the default required marker {marker} was never emitted")

# =============================================================================
# the runner
# =============================================================================
def run_suite(only: str | None, keep: bool, tmp: Path, quiet=False) -> tuple[int, int, list]:
    passed = failed = 0
    failures = []
    width = max(len(n) for n, _, _ in TESTS) + 2
    for name, defect, fn in TESTS:
        if only and only not in name and only not in defect:
            continue
        f = fresh(tmp, name)
        t0 = time.time()
        try:
            fn(f)
            passed += 1
            if not quiet:
                print(f"  PASS  {name:<{width}} {time.time()-t0:5.1f}s")
        except Exception as e:                      # noqa: BLE001 - a crash IS a failure
            failed += 1
            failures.append((name, defect, e))
            if not quiet:
                print(f"  FAIL  {name:<{width}} {time.time()-t0:5.1f}s")
                print(f"        locks: {defect}")
                for line in str(e).splitlines()[:14]:
                    print(f"        | {line}")
        finally:
            if not keep:
                shutil.rmtree(f.root, ignore_errors=True)
    return passed, failed, failures


# =============================================================================
# --mutate: does the suite actually CATCH anything?
# =============================================================================
# The same argument this skill makes about mutation-testing your product, turned on the
# suite itself. A green suite is evidence of nothing until you have watched it go red.
#
# Each mutation is a REAL defect that shipped. `expect` names a test that must fail when
# the defect is restored. If everything stays green, that test is decoration and this says
# so by name -- which is the only way a regression suite stays honest as it grows.

class Mutation:
    """A real defect that shipped, and the test that must go red when it comes back.

    `scope` says WHICH tree to mutate. "factory" is the runner, copied into the fixture
    when it is built. "harness" is the validation scaffold, which `install_harness` copies
    from the template at TEST time -- so mutating the fixture's copy would be overwritten a
    moment later. Harness mutations patch a copy of the template and repoint HARNESS_SRC
    at it instead, which is the only way the copy the test actually runs is the mutated one.
    """

    def __init__(self, ident, path, find, replace, why, expect, scope="factory"):
        self.id, self.path, self.find, self.replace = ident, path, find, replace
        self.why, self.expect, self.scope = why, expect, scope


MUTATIONS = [
    Mutation(
        "failed-cannot-reopen", "factory/state.py",
        '"failed": {"open", "rejected", "needs-human"},',
        '"failed": {"validating", "rejected", "needs-human"},',
        "the original fix-loop wedge: fix-pr committed, then died on an illegal "
        "transition before any escalate, and `next` answered idle forever",
        "test_failed_can_return_to_open"),
    Mutation(
        "passed-cannot-requeue", "factory/state.py",
        '"passed": {"merged", "open", "needs-human"},',
        '"passed": {"merged", "needs-human"},',
        "any commit landing on main during a lap parked the PR permanently, because the "
        "documented remedy was the one move the table forbade",
        "test_passed_can_requeue_to_open"),
    Mutation(
        "needs-human-escapable", "factory/state.py",
        '"needs-human": set(),',
        '"needs-human": {"open", "accepted"},',
        "a node able to leave needs-human can un-escalate its own escalation",
        "test_needs_human_is_terminal_for_nodes"),
    Mutation(
        "title-grep-is-fatal", "factory/run-workflow.sh",
        "sed 's/^ *//' || true)",
        "sed 's/^ *//')",
        "an issue with no title: line killed the runner before the issue moved to "
        "in-progress, so it was re-dispatched every tick forever",
        "test_untitled_issue_does_not_kill_the_runner"),
    Mutation(
        "no-err-trap", "factory/run-workflow.sh",
        "trap 'on_unguarded_error \"$?\" \"$LINENO\" \"$BASH_COMMAND\"' ERR",
        "# ERR trap removed by mutation",
        "without it every unguarded death is exit 1 and nothing else",
        "test_unguarded_failure_escalates_loudly"),
    Mutation(
        "no-dispatcher-err-trap", "factory/orchestrator.sh",
        "trap 'on_dispatcher_fault \"$?\" \"$LINENO\" \"$BASH_COMMAND\"' ERR",
        "# dispatcher ERR trap removed by mutation",
        "the scheduled entry point dies mid-tick with no message and no notification; "
        "the reaper and the stalled sweep never run and nobody is told",
        "test_dispatcher_fault_is_loud"),
    Mutation(
        "cap-branch-does-not-park-issue", "factory/orchestrator.sh",
        'python factory/state.py set "$CAP_ISSUE" state=needs-human >/dev/null 2>&1 || true',
        ': # issue parking removed by mutation',
        "the PR parks and its issue keeps reading in-progress, so `next` walks past the "
        "escalation to unrelated work",
        "test_escalation_parks_the_issue_too"),
    Mutation(
        "merge-failure-kills-the-tick", "factory/orchestrator.sh",
        'log "$(factory_notify "$TARGET" "merge refused for a PR that passed every gate")"',
        ': # notification removed by mutation',
        "a merge refused on the orchestrator route told nobody",
        "test_orchestrator_merge_failure_notifies"),
    Mutation(
        "triage-stop-is-silent", "factory/run-workflow.sh",
        'log "$(factory_notify "$TARGET" "(triage) $TRIAGE_WHY")"',
        ': # triage notification removed by mutation',
        "a correct triage needs-human decision reached nobody",
        "test_triage_needs_human_notifies"),
    Mutation(
        "max-parallel-inert", "factory/orchestrator.sh",
        'NEXT="$(python factory/state.py next --exclude "$EXCLUDE")"',
        'NEXT="$(python factory/state.py next)"',
        "without --exclude the dispatcher asks the same question and gets the same "
        "answer, so FACTORY_MAX_PARALLEL silently does nothing",
        "test_max_parallel_dispatches_more_than_one"),
    # --- the validation harness. Every one of these is the same shape: the gate goes
    # --- green because a check did not run, rather than because it passed.
    Mutation(
        "holdout-absence-is-silent", "ci.py",
        'print("HOLDOUT_ABSENT no .factory/holdout/run.py - NOTHING above the "',
        'print("" or ("holdout absent" and "") or "", end="") or print("QUIET_ABSENT "',
        "a gate with no holdout said nothing about it, so every check in it was one the "
        "builder could read and iterate against -- and it read as fully green",
        "test_harness_reports_an_absent_holdout", "harness"),
    Mutation(
        "zero-tests-is-a-pass", "ci.py",
        "if ran == 0:",
        "if False:",
        "a unit suite that discovered nothing exits 0 and looks perfect",
        "test_harness_refuses_a_zero_test_suite", "harness"),
    Mutation(
        "no-e2e-watchdog", "ci.py",
        'wd = watchdog(int(CONFIG.get("e2e_timeout_s", 300)), "e2e", app)',
        "wd = type('N', (), {'cancel': lambda self: None})()",
        "the e2e rung is called in process, so nothing upstream can interrupt it: the "
        "gate printed APP_STARTED and then nothing at all, all night, holding its lock",
        "test_harness_watchdog_kills_a_hanging_e2e", "harness"),
    Mutation(
        "mutation-recursion", "ci.py",
        'if os.environ.get("FACTORY_IN_MUTATION") == "1":',
        "if False:",
        "the mutation runner copies harness/ into each throwaway build, so the inner gate "
        "re-runs everything and misattributes which rung caught the defect",
        "test_harness_does_not_recurse_into_mutations", "harness"),
    Mutation(
        "quoted-path-unresolved", "ci.py",
        # Anchored on the de-quoting line rather than the `if` that guards it. The guard
        # contains both quote characters AND a backslash, and the version of this string
        # that went through several layers of escaping silently lost the backslash and
        # matched nothing -- reported as SKIP, which is why SKIP is loud and is never
        # counted as a pass. This line does the same job and contains no quotes at all.
        "        head = head[1:-1]",
        "        pass  # de-quoting removed by mutation",
        "shlex.split(posix=False) leaves the QUOTES on the token, so a correct command "
        "whose interpreter path contains a space died with the exact [WinError 2] that "
        "resolve() exists to prevent",
        "test_harness_runs_a_quoted_interpreter_path", "harness"),
    Mutation(
        "gate-passes-on-absence", "factory/gate.sh",
        'grep -q "$MARKER" "$LOG" || MISSING="$MISSING $MARKER"',
        'true  # marker check removed by mutation',
        "empty is not pass: a gate that checks for the absence of an error marker rather "
        "than the presence of a success marker green-lights a run that printed nothing",
        "test_gate_requires_positive_markers"),
]


def run_mutations(tmp: Path, only: str | None) -> int:
    print()
    print("=" * 78)
    print("MUTATION CHECK -- restore each historical defect, the suite must go RED")
    print("=" * 78)
    print("A test whose defect can be put back while everything stays green is")
    print("decoration. This is the only thing that keeps the suite honest as it grows.")
    print()

    global PRISTINE
    clean = PRISTINE
    survived = []
    for m in MUTATIONS:
        if only and only not in m.id:
            continue
        global HARNESS_SRC
        clean_harness = HARNESS_SRC
        mutant = tmp / f"mutant-{m.id}"
        if m.scope == "harness":
            # Mutate a copy of the TEMPLATE harness and point install_harness at it.
            shutil.copytree(clean, mutant, symlinks=True)
            hmut = tmp / f"harness-{m.id}"
            shutil.copytree(clean_harness, hmut)
            target = hmut / m.path
        else:
            shutil.copytree(clean, mutant, symlinks=True)
            target = mutant / m.path
        s = target.read_text(encoding="utf-8")
        if m.find not in s:
            print(f"  SKIP  {m.id:<34} the code it mutates no longer exists -- "
                  f"the mutation needs updating, NOT deleting")
            print(f"        looked for: {m.find[:88]}")
            survived.append((m, "STALE"))
            HARNESS_SRC = clean_harness
            shutil.rmtree(mutant, ignore_errors=True)
            continue
        target.write_text(s.replace(m.find, m.replace, 1), encoding="utf-8", newline="\n")

        if m.scope == "harness":
            HARNESS_SRC = hmut
        PRISTINE = mutant
        sub = tmp / f"run-{m.id}"
        sub.mkdir(parents=True, exist_ok=True)
        _, _, failures = run_suite(None, False, sub, quiet=True)
        PRISTINE = clean
        HARNESS_SRC = clean_harness
        shutil.rmtree(mutant, ignore_errors=True)
        shutil.rmtree(sub, ignore_errors=True)

        caught = {n for n, _, _ in failures}
        if m.expect in caught:
            print(f"  CAUGHT {m.id:<34} by {m.expect}")
        elif caught:
            print(f"  WRONG  {m.id:<34} went red, but in {sorted(caught)}")
            print(f"         NOT {m.expect}, which is the test that claims to lock it.")
            print(f"         Something is detected; what claims to detect it does not. "
                  f"That is not coverage.")
            survived.append((m, "WRONG-TEST"))
        else:
            print(f"  SURVIVED {m.id:<32} NOTHING went red")
            print(f"         defect: {m.why}")
            print(f"         {m.expect} does not actually test this")
            survived.append((m, "SURVIVED"))

    print()
    if survived:
        print(f"{len(survived)} mutation(s) survived or went stale. Every one is a test "
              f"that does not do its job.")
        return 1
    print("Every restored defect was caught. The suite is load-bearing.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="substring filter on the test name or the defect")
    ap.add_argument("--keep", action="store_true", help="leave fixtures on disk")
    ap.add_argument("--mutate", action="store_true",
                    help="restore each historical defect; the suite must go red")
    ap.add_argument("--list", action="store_true", help="names only")
    ap.add_argument("--repo", help="test a factory somebody BUILT, not the template. "
                                   "The runner is copied into a repo and never linked, so "
                                   "this is the only way to know whether a factory that "
                                   "has been running for months still holds.")
    args = ap.parse_args()

    global FACTORY_SRC
    if args.repo:
        FACTORY_SRC = Path(args.repo).resolve() / "factory"
        if not (FACTORY_SRC / "run-workflow.sh").exists():
            print(f"no factory/run-workflow.sh under {args.repo}", file=sys.stderr)
            return 2

    if args.list:
        for name, defect, _ in TESTS:
            print(f"{name}\n    {defect}\n")
        print(f"{len(TESTS)} tests, {len(MUTATIONS)} mutations")
        return 0

    if not FACTORY_SRC and not (RUNNER_SRC / "factory" / "run-workflow.sh").exists():
        print(f"cannot find the runner template at {RUNNER_SRC}", file=sys.stderr)
        return 2

    root = Path(tempfile.mkdtemp(prefix="factory-suite-"))
    global PRISTINE, TMP_FOR_SUBCASES
    TMP_FOR_SUBCASES = root
    try:
        t0 = time.time()
        PRISTINE = build_pristine(root / "_pristine")
        print(f"under test: {FACTORY_SRC or (RUNNER_SRC / 'factory')}")
        print(f"fixture built in {time.time()-t0:.1f}s -> {PRISTINE}")
        print()
        passed, failed, _ = run_suite(args.only, args.keep, root)
        print()
        print(f"PASSED={passed}  FAILED={failed}  TESTS={passed+failed}/{len(TESTS)}")

        rc = 1 if failed else 0
        if args.mutate and FACTORY_SRC:
            print("\n--mutate targets the TEMPLATE's source text; against a built factory "
                  "it reports STALE for anything that has drifted, which is a fact about "
                  "the drift rather than about the tests. Running it anyway.")
        if args.mutate:
            if failed:
                print("\nrefusing to mutation-check a suite that is already red -- fix "
                      "the failures first, or the results mean nothing")
                return 1
            rc = run_mutations(root, args.only)
        return rc
    finally:
        if args.keep:
            print(f"\nfixtures kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
