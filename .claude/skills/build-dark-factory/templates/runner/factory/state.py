"""The state machine. FACTORY_RULES.md 1.

TWO BACKENDS, ONE TABLE.

  github  (default wherever an `origin` remote exists) -- GitHub issues and PRs, and
          `factory:*` labels are the state. `factory/gh_backend.py`.
  files   -- `issues/<id>.md` and `.factory/prs/<id>.md` front matter is the state. This
          is what the factory ran on before the move and it still works on a clone with
          no remote, which is what you want when you are debugging the machinery itself
          rather than the work.

Select explicitly with FACTORY_BACKEND=github|files.

`TRANSITIONS` below is shared by both. Two copies of a legality table is two tables that
drift, and the entire value of the table is that a node cannot invent a transition.

    python factory/state.py list issues --state accepted
    python factory/state.py get gh:issue:3          # or issues/0007.md
    python factory/state.py set gh:issue:3 state=accepted priority=high
    python factory/state.py body gh:issue:3         # the issue, as a file a node can read
    python factory/state.py bump-attempt gh:pr:4    # the fix cap, FACTORY_RULES.md 8
    python factory/state.py next                    # what the dispatcher should run

`set` refuses illegal transitions. That refusal is the reason this is a script rather
than three lines of sed in the orchestrator: a node that wants a transition the table
does not allow has misunderstood something, and inventing the transition buries the
misunderstanding instead of surfacing it.

Deliberately no YAML dependency. The front matter this reads is flat key: value, and a
parser that cannot express anything clever cannot be talked into expressing something
clever.
"""
from __future__ import annotations
import glob
import json
import os
import subprocess
import sys

# UTF-8 on every stream, unconditionally. Windows defaults stdio to the ANSI codepage,
# so a note piped in through `comment` arrived with every non-ASCII character replaced --
# the first triage on the GitHub backend posted a correct rejection full of U+FFFD. The
# file backend never showed this because it wrote to an explicitly utf-8 file handle and
# never went near a pipe. Anything that crosses a process boundary needs the encoding
# stated, and on this path everything now does.
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# So `import gh_backend` works however this file was invoked.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ISSUE_STATES = ["untriaged", "accepted", "deferred", "rejected",
                "needs-human", "in-progress", "done"]
PR_STATES = ["open", "validating", "passed", "failed", "merged", "rejected"]

# FACTORY_RULES.md 1. Anything not on this table is refused.
TRANSITIONS = {
    "untriaged": {"accepted", "deferred", "rejected", "needs-human"},
    "accepted": {"in-progress", "needs-human", "rejected"},
    "in-progress": {"done", "accepted", "needs-human"},
    "deferred": {"needs-human"},
    "rejected": {"needs-human"},
    "done": {"needs-human"},
    "needs-human": set(),      # only a human, by editing the file
    # GITHUB MOVES STATE TOO, and the file backend had no actor that could. A PR body
    # saying `Closes #N` makes GitHub close the issue the moment the PR merges -- a
    # transition this table never authorised, performed by something that has never read
    # it. The resulting issue is closed with no disposition label, which is genuinely
    # "closed, reason not recorded", and the factory's job is then to record the reason.
    # Treated like `untriaged`: a state you arrive in from outside, from which any honest
    # disposition is reachable. It is NOT a state any node may leave in place.
    "closed-unlabelled": {"done", "deferred", "rejected", "needs-human"},
    "open": {"validating", "needs-human"},
    "validating": {"passed", "failed", "rejected", "needs-human"},
    # `failed -> open`, and the arrow used to point at `validating` instead. That one
    # entry made the entire fix loop unreachable, and it failed in the quietest way this
    # system has:
    #
    #   fix-pr committed the fix, bumped `attempts`, then ran
    #     state.py set <pr> state=validating   (legal)
    #     state.py set <pr> state=open         (ILLEGAL - validating cannot reach open)
    #
    # the second call returned 1, `set -e` killed the workflow THERE, and no escalate()
    # ran: no needs-human, no notification, nothing in the log but one line. The PR was
    # left in `validating`, which `next` did not look at, so the dispatcher answered
    # `idle` -- forever. A factory wedged like that is indistinguishable from a factory
    # with nothing to do, which is the exact failure the dispatcher's own comments warn
    # about, reached from the one workflow nobody had ever executed.
    #
    # The right arrow is the simple one. A fixed PR is a PR waiting to be validated, and
    # `open` is what "waiting to be validated" is called; the dispatcher then picks it up
    # and validate-pr sets `validating` itself, after the tripwire, exactly as it does the
    # first time round. `validating` is deliberately NOT reachable from here: it is owned
    # by a running validation and nothing else may hand it out.
    "failed": {"open", "rejected", "needs-human"},
    # `passed -> open` is the same deadlock as `failed -> open` above, one state further
    # along, and it survived the fix to that one. Found by a full greenfield build.
    #
    #   the gate holds the merge on ratchet slack
    #     -> it tells you to raise the floor
    #       -> raising the floor is a human commit on main
    #         -> merge.sh correctly refuses a branch that is now behind base
    #           -> `passed` reached only {merged, needs-human}
    #             -> the documented remedy - rebase and re-validate - is the one move the
    #                table forbids, so the PR parks and every later tick prints the same
    #                refusal forever, which reads exactly like an idle factory.
    #
    # Any commit landing on main during a lap does it; on a repo with velocity that is not
    # an edge case. `open` is the right target: validate-pr rebases before it validates, so
    # a requeued PR is judged on the tree that will actually merge.
    "passed": {"merged", "open", "needs-human"},
    "merged": set(),
}

PRIORITIES = ["critical", "high", "medium", "low"]


def backend() -> str:
    """github wherever there is a remote, unless told otherwise.

    Auto-detection rather than a required env var, because the failure mode of forgetting
    it is silent: the file backend on a GitHub repo reports `idle` while three issues sit
    open, and an idle factory looks exactly like a factory with nothing to do.
    """
    explicit = os.environ.get("FACTORY_BACKEND", "").strip()
    if explicit:
        return explicit
    rc = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                        capture_output=True, text=True).returncode
    return "github" if rc == 0 else "files"


def parse(path: str) -> dict:
    """Front matter as a flat dict, plus `_body` and `_path`."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta: dict[str, str] = {"_path": os.path.relpath(path, ROOT).replace("\\", "/")}
    if not text.startswith("---"):
        meta["_body"] = text
        return meta
    _, fm, body = text.split("---", 2)
    for line in fm.strip().splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    meta["_body"] = body.lstrip("\n")
    return meta


def write(path: str, meta: dict) -> None:
    order = ["id", "issue", "title", "state", "priority", "area", "branch",
             "attempts", "filed-by", "opened", "note"]
    keys = [k for k in order if k in meta] + \
           [k for k in meta if not k.startswith("_") and k not in order]
    fm = "\n".join(f"{k}: {meta[k]}" for k in keys)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"---\n{fm}\n---\n\n{meta.get('_body', '')}")


def load(kind: str) -> list[dict]:
    pattern = os.path.join(ROOT, "issues", "*.md") if kind == "issues" \
        else os.path.join(ROOT, ".factory", "prs", "*.md")
    return [parse(p) for p in sorted(glob.glob(pattern))]


def cmd_list(argv: list[str]) -> int:
    kind = argv[0] if argv else "issues"
    want = argv[argv.index("--state") + 1] if "--state" in argv else None
    items = [i for i in load(kind) if want is None or i.get("state") == want]
    if "--priority" in argv:
        p = argv[argv.index("--priority") + 1]
        items = [i for i in items if i.get("priority") == p]
    for i in items:
        print(f"{i['_path']}\t{i.get('state','?')}\t{i.get('priority','-')}\t"
              f"{i.get('title', i.get('issue',''))}")
    return 0


def cmd_get(argv: list[str]) -> int:
    meta = parse(os.path.join(ROOT, argv[0]))
    for k, v in meta.items():
        if not k.startswith("_"):
            print(f"{k}={v}")
    return 0


def _split_pair(pair: str) -> tuple[str, str]:
    """`key=value`, or a NAMED error rather than a traceback.

    Every caller of `set` is a shell line, and a quoting slip there turns into a bare
    argument here. It happened: a line continuation lost its newline, so `state=passed \\`
    became `state=passed` plus a stray `n`, and this raised
    `ValueError: not enough values to unpack` from inside a gate that had already decided
    to merge. The stack trace named a line in this file, which is the one place the
    problem was not.
    """
    if "=" not in pair:
        raise SystemExit(
            f"BAD_ARGUMENT: expected key=value, got {pair!r}. Something upstream passed a "
            f"bare word - usually a broken line continuation or an unquoted variable in "
            f"the shell command that called this.")
    k, v = pair.split("=", 1)
    return k, v


def cmd_set(argv: list[str]) -> int:
    path = os.path.join(ROOT, argv[0])
    meta = parse(path)
    for pair in argv[1:]:
        k, v = _split_pair(pair)
        if k == "state":
            old = meta.get("state")
            if old == v:
                continue
            allowed = TRANSITIONS.get(old, set())
            if v not in allowed:
                print(f"ILLEGAL_TRANSITION: {path} is '{old}'; "
                      f"'{v}' is not in {sorted(allowed) or ['(nothing -- a human must move this)']}",
                      file=sys.stderr)
                if old == "needs-human":
                    print("A node may never move an issue out of needs-human "
                          "(FACTORY_RULES.md 7). Edit the file by hand.", file=sys.stderr)
                return 1
        meta[k] = v
    write(path, meta)
    print(f"OK {os.path.relpath(path, ROOT)} " +
          " ".join(f"{p}" for p in argv[1:]))
    return 0


def _excluded(argv: list[str]) -> set[str]:
    """Targets the dispatcher already holds a lock on.

    `next` names ONE thing, and before this existed a target that was already in flight
    consumed the whole tick: the dispatcher asked, got the head of the queue, found its
    lock taken, and stopped. So `FACTORY_MAX_PARALLEL=3` never ran three of anything --
    the knob was inert, silently, which is worse than not offering it.

    The exclusion is passed IN rather than worked out here, because the locks live with
    the dispatcher and the priority order lives here, and neither should learn the other.
    """
    if "--exclude" not in argv:
        return set()
    raw = argv[argv.index("--exclude") + 1]
    return {t.strip() for t in raw.split(",") if t.strip()}


def cmd_next(argv: list[str]) -> int:
    """The dispatcher's question, answered by data. FACTORY_RULES.md 8.

    Priority order is load-bearing: finish in-flight work before starting new work.
    Reversed, the factory triages forever while its own branches rot.
    """
    skip = _excluded(argv)
    prs = [p for p in load("prs") if p["_path"] not in skip]

    failed = [p for p in prs if p.get("state") == "failed"
              and int(p.get("attempts", 0)) < 2]
    if failed:
        print(f"fix-pr\t{failed[0]['_path']}")
        return 0

    capped = [p for p in prs if p.get("state") == "failed"
              and int(p.get("attempts", 0)) >= 2]
    if capped:
        print(f"escalate\t{capped[0]['_path']}")
        return 0

    open_prs = [p for p in prs if p.get("state") == "open"]
    if open_prs:
        print(f"validate-pr\t{open_prs[0]['_path']}")
        return 0

    passed = [p for p in prs if p.get("state") == "passed"]
    if passed:
        print(f"merge\t{passed[0]['_path']}")
        return 0

    issues = [i for i in load("issues") if i["_path"] not in skip]
    for prio in PRIORITIES:
        ready = [i for i in issues if i.get("state") == "accepted"
                 and i.get("priority") == prio]
        if ready:
            print(f"implement-issue\t{ready[0]['_path']}")
            return 0

    untriaged = [i for i in issues if i.get("state") == "untriaged"]
    if untriaged:
        print(f"triage\t{untriaged[0]['_path']}")
        return 0

    # LAST, and only when there is genuinely nothing else to do. A PR sits in `validating`
    # for as long as a validation is running, which is normal and is not this. What this
    # catches is the run that never came back -- a killed process, a reboot, a crash
    # between the tripwire and the verdict -- because `validating` is the one live state no
    # earlier branch here looks at, so such a PR was reported as `idle` and never mentioned
    # again.
    #
    # It is reported rather than acted on: the orchestrator holds the runtime lock and is
    # the only thing that can tell "still running" from "died". Answering `idle` while a
    # PR is mid-flight is the specific lie this whole file exists to avoid.
    stalled = [p for p in prs if p.get("state") == "validating"]
    if stalled:
        print(f"stalled\t{stalled[0]['_path']}")
        return 0

    # The ISSUE half of the same hole. `implement-issue` moves an issue to `in-progress`
    # before any node runs, so a lap that dies in between leaves it there - and nothing
    # above looks at `in-progress`. Reported only when NO PR record references it: an
    # issue with a live PR is not stranded, it is being worked on, which is what the state
    # means.
    referenced = {p.get("issue") for p in load("prs")}
    orphans = [i for i in issues
               if i.get("state") == "in-progress" and i["_path"] not in referenced]
    if orphans:
        print(f"stalled\t{orphans[0]['_path']}")
        return 0

    print("idle\t-")
    return 0


COMMANDS = {"list": cmd_list, "get": cmd_get, "set": cmd_set, "next": cmd_next}


# --- the GitHub backend, same commands, same transition table ----------------
def gh_set(argv: list[str]) -> int:
    """The legality check lives HERE, not in the backend.

    Both backends route their state writes through this function so that the table above
    is the only definition of a legal move. A backend that owned its own check would be a
    second table, and the second table is always the one that is wrong.
    """
    import gh_backend as B
    target = argv[0]
    for pair in argv[1:]:
        k, v = _split_pair(pair)
        if k == "state":
            old = B.fetch(target)["_state"]
            if old == v:
                # Re-apply anyway. The labels ARE the state, so a state that is already
                # correct but has no label on it is a state a human cannot read. This is
                # the one write that is idempotent on purpose.
                B.set_state(target, v)
                continue
            allowed = TRANSITIONS.get(old, set())
            if v not in allowed:
                print(f"ILLEGAL_TRANSITION: {target} is '{old}'; '{v}' is not in "
                      f"{sorted(allowed) or ['(nothing -- a human must move this)']}",
                      file=sys.stderr)
                if old == "needs-human":
                    print("A node may never move an issue out of needs-human "
                          "(FACTORY_RULES.md 7). Remove the label by hand.", file=sys.stderr)
                return 1
            B.set_state(target, v)
        elif k == "priority":
            B.set_priority(target, v)
        elif k in ("branch", "attempts", "issue", "title"):
            # Native on GitHub (branch, issue link, title) or counted from an append-only
            # marker (attempts). Writing them is a no-op rather than an error so the
            # workflows can stay backend-agnostic -- but it says so, because a write that
            # silently does nothing is how state quietly stops being state.
            print(f"NOT_STORED: '{k}' is derived on the GitHub backend, not written")
        elif k == "area":
            print(f"NOT_STORED: 'area' has no label; record it in the triage comment")
        else:
            print(f"NOT_STORED: unknown key '{k}'", file=sys.stderr)
            return 1
    print(f"OK {target} " + " ".join(argv[1:]))
    return 0


def gh_main(cmd: str, argv: list[str]) -> int:
    import gh_backend as B
    try:
        if cmd == "next":
            return B.cmd_next()
        if cmd == "list":
            return B.cmd_list(argv)
        if cmd == "get":
            return B.cmd_get(argv)
        if cmd == "body":
            return B.cmd_body(argv)
        if cmd == "set":
            return gh_set(argv)
        if cmd == "comment":
            B.comment(argv[0], sys.stdin.read())
            return 0
        if cmd == "edit-comment":
            B.edit_comment(argv[0], sys.stdin.read())
            return 0
        if cmd == "escalate-note":
            B.escalate_note(argv[0], argv[1], argv[2])
            return 0
        if cmd == "triage-note":
            with open(argv[1], encoding="utf-8") as fh:
                B.triage_note(argv[0], json.load(fh))
            return 0
        if cmd == "create-pr":
            # title, base, head on the command line; body on stdin.
            num, url = B.create_pr(argv[0], sys.stdin.read(), argv[1], argv[2])
            print(f"PR_NUMBER={num}")
            print(f"PR_URL={url}")
            return 0
        if cmd == "bump-attempt":
            print(f"ATTEMPTS={B.bump_attempt(argv[0])}")
            return 0
        if cmd == "stop-requested":
            stopped, why = B.stop_requested()
            print(f"STOP={'1' if stopped else '0'} {why}".rstrip())
            return 0 if not stopped else 1
    except B.GhError as e:
        print(f"GH_ERROR: {e}", file=sys.stderr)
        return 4
    print(__doc__)
    return 2


def files_body(argv: list[str]) -> int:
    with open(os.path.join(ROOT, argv[0]), encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return 0


def files_comment(argv: list[str]) -> int:
    """The same verb on both backends: say something durable about this work item.

    On files it appends to the record; on GitHub it posts a comment. Everything that
    wants to write a human-readable note -- gate.sh, triage, the merge -- calls this and
    never learns which backend it is on.
    """
    with open(os.path.join(ROOT, argv[0]), "a", encoding="utf-8") as fh:
        fh.write("\n" + sys.stdin.read().rstrip() + "\n")
    return 0


def files_bump_attempt(argv: list[str]) -> int:
    path = os.path.join(ROOT, argv[0])
    meta = parse(path)
    n = int(meta.get("attempts", 0)) + 1
    meta["attempts"] = str(n)
    write(path, meta)
    print(f"ATTEMPTS={n}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, argv = sys.argv[1], sys.argv[2:]

    # A gh: target is self-describing and overrides the backend choice, so gate.sh and
    # merge.sh work on either kind of target without knowing which they were handed.
    import gh_backend as B
    if backend() == "github" or (argv and B.is_gh_target(argv[0])):
        return gh_main(cmd, argv)

    if cmd == "body":
        return files_body(argv)
    if cmd == "comment":
        return files_comment(argv)
    if cmd == "triage-note":
        with open(os.path.join(ROOT, argv[1]), encoding="utf-8") as fh:
            d = json.load(fh)
        note = ("\n**factory/triage** - `" + str(d.get("state", "?")) + "`\n\n"
                + (d.get("note") or "(no note)").strip() + "\n")
        with open(os.path.join(ROOT, argv[0]), "a", encoding="utf-8") as fh:
            fh.write(note)
        return 0
    if cmd == "bump-attempt":
        return files_bump_attempt(argv)
    if cmd == "stop-requested":
        print("STOP=0 (files backend has no remote stop label)")
        return 0
    if cmd not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[cmd](argv)


if __name__ == "__main__":
    sys.exit(main())
