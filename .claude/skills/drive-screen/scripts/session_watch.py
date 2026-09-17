#!/usr/bin/env python3
"""Observe Claude Code JSONL transcripts; never infer approval or completion from silence.

This parser is Claude Code-only, for its internal ~/.claude/projects layout.
Unknown formats (including Codex events), empty files, and quiet transcripts are
not completion evidence. `wait` pins one transcript at startup and requires a new
Claude turn_duration record after a recognizable prompt, with no newer prompt or
unanswered tool call. Missing markers require separate verification.

Exit codes: 0 success/observed completion; 1 missing/unreadable/replaced input
or timeout; 2 quiet but completion unverified. Exit 2 does not prove a permission
prompt, a running tool, or a dead process. Inspect the current UI before action.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

FILE_TOOLS = ("Read", "Grep", "Glob", "Edit", "Write", "NotebookEdit")
CMD_TOOLS = ("Bash", "PowerShell")


def mangle(repo: str) -> str:
    r"""C:\Users\me\my project  ->  C--Users-me-my-project

    The documented rule is EVERY non-alphanumeric character becomes a hyphen, not
    just the path separators. A folder with a space, a dot or a parenthesis in it
    is common enough that getting this wrong means the directory is simply never
    found, with a "the session never started" message pointing at the wrong cause.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(repo).resolve()))


def session_dir(repo: str) -> Path:
    """Resolve the project directory, tolerating drive-letter case on Windows.

    Claude Code has been observed writing this folder with an upper-case drive
    letter while looking it up with a lower-case one. Deriving the name and
    trusting it therefore fails intermittently on Windows for no visible reason,
    so the derived name is only a candidate: what is actually on disk wins.
    """
    want = mangle(repo)
    exact = PROJECTS / want
    if exact.is_dir():
        return exact
    if PROJECTS.is_dir():
        for d in PROJECTS.iterdir():
            if d.is_dir() and d.name.lower() == want.lower():
                return d
    print(f"NO_SESSION_DIR: {exact}")
    print("The driven session has not started, or it started in a different cwd.")
    print("Check the terminal's working directory before assuming anything else.")
    sys.exit(1)


PIN: str | None = None  # set from --session; pins one session out of many


def transcripts(repo: str) -> list[Path]:
    """The selected parent transcript and only that session's subagents.

    A driven session that dispatches subagents writes their turns to
    <sessionId>/subagents/agent-<id>.jsonl, not inline in the parent file. Reading
    only the parent misses everything a subagent did, which for an audit question
    ("what files did it actually touch") is exactly the part you wanted.
    """
    d = session_dir(repo)
    parent = latest(repo)
    return [parent] + sorted((d / parent.stem / "subagents").glob("*.jsonl"))


def _session_matches(d: Path, prefix: str) -> list[Path]:
    """Return exactly matching parent transcripts; reject ambiguous prefixes."""
    return sorted(p for p in d.glob("*.jsonl") if p.stem.startswith(prefix))


def latest(repo: str) -> Path:
    # With several sessions open in one repo, "newest by mtime" is whichever wrote
    # last, not necessarily the one being driven. Pin it with --session.
    d = session_dir(repo)
    if PIN:
        hits = _session_matches(d, PIN)
        if not hits:
            print(f"NO_SUCH_SESSION: {PIN} in {d}")
            sys.exit(1)
        if len(hits) > 1:
            print(f"AMBIGUOUS_SESSION: {PIN} matches {len(hits)} transcripts in {d}")
            print("Use a longer --session prefix.")
            sys.exit(1)
        return hits[0]
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"NO_TRANSCRIPTS in {d}")
        sys.exit(1)
    return files[-1]


def records(p: Path) -> list[dict]:
    out = []
    # errors="replace" plus a per-line try: the file is appended to while we read,
    # so the last line is routinely a half-written fragment.
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"UNREADABLE_TRANSCRIPT: {p}: {exc}") from exc
    # Preserve an incomplete tail as unknown state. Dropping a partial next user
    # prompt could make an earlier completion marker look like the final event.
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n"):
            out.append({"type": "_incomplete_record"})
            continue
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            value = {"type": "_unrecognized_record"}
        out.append(value if isinstance(value, dict) else {"type": "_unrecognized_record"})
    return out


def turn_ends(recs: list[dict]) -> list[int]:
    return [i for i, d in enumerate(recs)
            if d.get("type") == "system" and d.get("subtype") == "turn_duration"]


def _content(d: dict) -> list:
    message = d.get("message") if isinstance(d, dict) else None
    c = message.get("content") if isinstance(message, dict) else None
    return c if isinstance(c, list) else []


def assistant_texts(recs: list[dict]) -> list[str]:
    out = []
    for d in recs:
        if d.get("type") != "assistant":
            continue
        for c in _content(d):
            if (isinstance(c, dict) and c.get("type") == "text"
                    and isinstance(c.get("text"), str) and c["text"].strip()):
                out.append(c["text"])
    return out


def prompt_indices(recs: list[dict]) -> list[int]:
    """Recognizable user prompts; tool-result-only user records do not count."""
    out = []
    for i, d in enumerate(recs):
        if d.get("type") != "user" or not isinstance(d.get("message"), dict):
            continue
        content = d["message"].get("content")
        if ((isinstance(content, str) and content.strip())
                or any(isinstance(c, dict) and (
                    (c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].strip())
                    or (c.get("type") == "image" and isinstance(c.get("source"), dict)))
                       for c in _content(d))):
            out.append(i)
    return out


def completed_turn(recs: list[dict], baseline: int = 0) -> bool:
    """Require a newly observed marker for the latest identifiable prompt."""
    prompts = prompt_indices(recs)
    ends = turn_ends(recs)
    if not prompts or not ends or ends[-1] < max(baseline, prompts[-1]):
        return False
    if pending_tool_calls(recs[prompts[-1]:]):
        return False
    known = {"user", "assistant", "system", "progress", "file-history-snapshot", "queue-operation"}
    if any(d.get("type") not in known for d in recs[prompts[-1]:ends[-1]]):
        return False
    # A later meaningful record may belong to the next turn or an unsupported
    # format. Only known bookkeeping records can trail the completion marker.
    bookkeeping = {"file-history-snapshot", "queue-operation"}
    return all(d.get("type") in bookkeeping for d in recs[ends[-1] + 1:])


def turn_in_flight(recs: list[dict]) -> bool:
    """Conservative compatibility helper: unknown input is not a closed turn."""
    return not completed_turn(recs)


def pending_tool_calls(recs: list[dict]) -> list[str]:
    """Unanswered recorded tool calls; their UI/execution state is unknown."""
    issued: dict[str, str] = {}
    answered: set[str] = set()
    for d in recs:
        for c in _content(d):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and isinstance(c.get("id"), str) and c["id"]:
                issued[c["id"]] = c.get("name", "?")
            elif c.get("type") == "tool_result" and isinstance(c.get("tool_use_id"), str):
                answered.add(c["tool_use_id"])
    return [name for tid, name in issued.items() if tid not in answered]


def pending_tool_details(recs: list[dict]) -> list[tuple[str, str]]:
    """Unanswered tool details are transcript hints, never approval requests."""
    issued: dict[str, tuple[str, str]] = {}
    answered: set[str] = set()
    for d in recs:
        for c in _content(d):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and isinstance(c.get("id"), str) and c["id"]:
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                detail = (inp.get("command") or inp.get("file_path")
                          or inp.get("path") or inp.get("pattern")
                          or inp.get("url") or "")
                issued[c["id"]] = (c.get("name", "?"), str(detail))
            elif c.get("type") == "tool_result" and isinstance(c.get("tool_use_id"), str):
                answered.add(c["tool_use_id"])
    return [v for k, v in issued.items() if k not in answered]


def tool_reads(recs: list[dict], start: int) -> list[tuple[str, str]]:
    hits = []
    for d in recs[start:]:
        for c in _content(d):
            if not isinstance(c, dict) or c.get("type") != "tool_use":
                continue
            name = c.get("name", "")
            inp = c.get("input") if isinstance(c.get("input"), dict) else {}
            path = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
            if name in FILE_TOOLS and path:
                hits.append((name, str(path)))
            elif name in CMD_TOOLS and (cmd := str(inp.get("command", ""))):
                hits.append((name, cmd[:200]))
    return hits


def _print_final(recs: list[dict], how: str) -> None:
    print(f"TURN_COMPLETE ({how})")
    print(f"RECORDS: {len(recs)}")
    if texts := assistant_texts(recs):
        print("\n--- final assistant message ---")
        print(texts[-1][:4000])


def cmd_wait(a) -> int:
    # Resolve once. A concurrent session becoming newer must never redirect a
    # watcher, even if no --session prefix was supplied.
    p = latest(a.repo)
    initial = records(p)
    if initial and initial[-1].get("type") == "_incomplete_record":
        initial = initial[:-1]
    requested_since = getattr(a, "since", None)
    baseline = requested_since if requested_since is not None else len(initial)
    if baseline > len(initial):
        print(f"INVALID_SINCE: {baseline} exceeds {len(initial)} records.")
        return 1
    baseline_records = initial[:baseline]
    last_recs = initial
    last_change = time.monotonic()
    deadline = last_change + a.timeout
    print(f"Watching {p.name}; waiting for a new completion marker.")
    while time.monotonic() < deadline:
        recs = records(p)
        if len(recs) < baseline or recs[:baseline] != baseline_records:
            print("TRANSCRIPT_REPLACED: original baseline changed; reselect deliberately.")
            return 1
        if completed_turn(recs, baseline):
            _print_final(recs, "new Claude turn_duration record")
            return 0
        if recs != last_recs:
            last_recs = recs
            last_change = time.monotonic()
        idle = time.monotonic() - last_change
        if idle >= a.idle:
            print(f"UNVERIFIED: transcript quiet for {int(idle)}s; completion not established.")
            if hints := pending_tool_details(recs):
                for tool, detail in hints:
                    print(f"TRANSCRIPT_HINT: {tool}: {detail[:300]}")
            print("Silence does not establish a permission prompt or execution state.")
            return 2
        time.sleep(min(a.poll, max(0, deadline - time.monotonic())))
    print(f"TIMEOUT after {a.timeout}s; completion not established.")
    return 1


def main() -> int:
    # Windows defaults stdout to cp1252 when redirected, and agent output is full
    # of characters it cannot encode. Without this, piping a transcript to a file
    # dies mid-write and leaves an empty file behind. newline="\n" matters as much:
    # Python emits CRLF on Windows and the stray CR breaks shell comparisons.
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", newline="\n")
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dir", "sessions", "mark", "wait", "last", "reads"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since", type=int, default=None, help="baseline index from `mark` (for wait)")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--idle", type=float, default=45,
                    help="seconds of silence before returning unverified (exit 2)")
    ap.add_argument("--poll", type=float, default=3.0)
    ap.add_argument("--match", default=None, help="only show reads containing this")
    ap.add_argument("--session", default=None, help="pin one session uuid (prefix ok)")
    ap.add_argument("--all", action="store_true",
                    help="for `reads`: include subagent transcripts too")
    a = ap.parse_args()

    if any(not math.isfinite(v) or v <= 0 for v in (a.timeout, a.idle, a.poll)) or (a.since is not None and a.since < 0):
        ap.error("--timeout, --idle, and --poll must be positive; --since must be nonnegative")
    global PIN
    PIN = a.session

    if a.cmd == "sessions":
        for p in sorted(session_dir(a.repo).glob("*.jsonl")):
            print(p.stem)
        return 0

    if a.cmd == "dir":
        print(session_dir(a.repo))
        print(latest(a.repo))
        subs = [p for p in transcripts(a.repo) if "subagents" in p.parts]
        if subs:
            print(f"({len(subs)} subagent transcript(s) also present)")
        return 0

    if a.cmd == "mark":
        p = latest(a.repo)
        recs = records(p)
        print(f"TRANSCRIPT: {p}")
        print(f"MARK: {len(recs)}")
        print(f"TURNS_COMPLETE: {len(turn_ends(recs))}")
        return 0

    if a.cmd == "wait":
        return cmd_wait(a)

    if a.cmd == "last":
        texts = assistant_texts(records(latest(a.repo)))
        if not texts:
            print("NO_ASSISTANT_TEXT")
            return 1
        print(texts[-1])
        return 0

    if a.cmd == "reads":
        parent = latest(a.repo)
        # --all means this parent's subagents, never unrelated parent sessions.
        files = ([parent] + sorted((parent.parent / parent.stem / "subagents").glob("*.jsonl"))
                 if a.all else [parent])
        hits = []
        for f in files:
            sub = "subagents" in f.parts
            tag = "  (subagent)" if sub else ""
            # --since is a record INDEX into the parent transcript. A subagent
            # writes its own file with its own index space, where that number
            # means nothing: applying it there skips most of a short transcript
            # and reports NONE. Measured live, a subagent that had just run a
            # find across the repo audited as having touched nothing, which is
            # the most misleading answer this command can give. A subagent file
            # is one dispatched task, so it is read whole and labelled.
            start = 0 if sub else (a.since or 0)
            hits += [(t, p + tag) for t, p in tool_reads(records(f), start)]
        if a.match:
            hits = [h for h in hits if a.match.lower() in h[1].lower()]
        if not hits:
            print("NONE" + (f" matching {a.match!r}" if a.match else ""))
            return 0
        for tool, path in hits:
            print(f"{tool:8} {path}")
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
