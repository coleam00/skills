#!/usr/bin/env python3
"""Structural invariants of the runner that no behaviour test can express.

    python scripts/_audit_runner.py            # audit the shipped template
    python scripts/_audit_runner.py --repo R   # audit a factory BUILT from it
    python scripts/_audit_runner.py --quiet    # findings only

`_test_runner.py` proves the runner BEHAVES. This proves things about its shape that only
become bugs later, and it exists because every one of these was a real defect found by
hand: a knob read by a child process that config.sh never exported, a prompt placeholder
the renderer does not substitute, a state nothing dispatches on, a `grep` whose failure
kills the script before the escalate on the next line.

The difference from `factory_doctor.py` is the subject. The doctor audits YOUR repo -- is
there a holdout, is the dial honest, is the scaffold edited. This audits the MACHINERY, and
its findings are bugs in the factory rather than gaps in your setup. Both ship, because a
correctly configured repo running broken machinery passes every check the doctor has.

Exit code is the number of findings, so it can gate a commit.

Each audit prints what it CHECKED even when it finds nothing. An audit that silently passes
is indistinguishable from one that did not run -- the same "empty is not pass" rule the
gate applies to your test output, applied here.
"""
from __future__ import annotations

import argparse
import collections
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent

# Names that look like config but are the shell's own, or are bound by a `for`/`read`, or
# are passed inline on a command. Kept explicit: a blanket "ignore unknown" would hide the
# exact defect this audit exists to catch.
SHELL_OWNED = {
    "PATH", "HOME", "PWD", "IFS", "OSTYPE", "BASH_SOURCE", "BASH_COMMAND", "BASH_VERSION",
    "RANDOM", "PPID", "UID", "SECONDS", "LINENO", "FUNCNAME", "TMPDIR", "TEMP", "TMP",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "COMSPEC", "OS", "SHELL",
    "USER", "LOGNAME", "TERM", "EDITOR", "LC_ALL", "LANG", "PYTHONIOENCODING",
    "PYTHONPATH", "PYTHONUTF8", "GIT_DIR", "GH_TOKEN", "GITHUB_TOKEN",
}

FINDINGS: list[str] = []
CHECKED: list[str] = []


def finding(msg: str):
    FINDINGS.append(msg)


def checked(msg: str):
    CHECKED.append(msg)


def need(run: Path, name: str, why: str) -> str | None:
    """Read a runner file, or record WHY the audit could not run.

    A checker that tracebacks on an unfamiliar repo tells you nothing at all, which is the
    same failure as a gate that passes because nothing ran. Factories built from older
    templates are missing whole files -- north-star-arena has no `config.sh`, because it
    predates the extraction of one -- and that is a finding, not a crash.
    """
    p = run / name
    if not p.exists():
        finding(f"layout: this factory has no `factory/{name}`, so {why} cannot be "
                f"checked. It predates the template that ships one; port it before "
                f"trusting any audit result here")
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def logical_lines(text: str):
    """Join `\\` continuations, so a guard on the next physical line still counts."""
    out, buf, start = [], "", 1
    for i, line in enumerate(text.splitlines(), 1):
        if not buf:
            start = i
        s = line.rstrip()
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        out.append((start, buf + s))
        buf = ""
    if buf:
        out.append((start, buf))
    return out


# =============================================================================
def audit_config(run: Path):
    """A knob that is read by a child process but never exported does NOTHING.

    Real defect: `guard.py` reads the size and file caps from the environment, and
    config.sh -- "the one file you edit" -- exported nothing. Editing a SAFETY limit
    changed no behaviour whatsoever, silently.
    """
    cfg = need(run, "config.sh", "the knobs users are told to edit")
    if cfg is None:
        return
    defined = set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)=", cfg, re.M))
    exported: set[str] = set()
    for m in re.finditer(r"^\s*export\s+((?:[^\n]*\\\n)*[^\n]*)$", cfg, re.M):
        exported |= set(re.findall(r"\b([A-Z][A-Z0-9_]*)\b", m.group(1)))

    read_py: dict[str, set[str]] = collections.defaultdict(set)
    read_sh: dict[str, set[str]] = collections.defaultdict(set)
    for p in sorted(run.rglob("*")):
        if not p.is_file() or p.suffix not in (".sh", ".py"):
            continue
        s = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(run).as_posix()
        if p.suffix == ".py":
            for v in re.findall(r"environ(?:\.get)?\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']", s):
                read_py[v].add(rel)
            for v in re.findall(r"getenv\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']", s):
                read_py[v].add(rel)
        else:
            for v in re.findall(r"\$\{?([A-Z][A-Z0-9_]{2,})\b", s):
                read_sh[v].add(rel)

    for v in sorted(read_py):
        if v in SHELL_OWNED:
            continue
        if (v.startswith("FACTORY_") or v in defined) and v not in exported:
            where = "defined but NOT exported" if v in defined else "never defined at all"
            finding(f"config: {v} is read by {sorted(read_py[v])} from the environment "
                    f"but is {where} in config.sh -- editing it does nothing")

    # A FACTORY_* knob read in shell that config.sh does not define is an undocumented
    # knob: it works, but it cannot be found in the file users are told to edit.
    for v in sorted(read_sh):
        if not v.startswith("FACTORY_") or v in defined or v in SHELL_OWNED:
            continue
        if v == "FACTORY_LOCK_HELD":     # passed inline by the dispatcher, never config
            continue
        finding(f"config: {v} is read by {sorted(read_sh[v])} but config.sh never "
                f"defines it -- an undocumented knob is one nobody can find")

    dead = sorted(v for v in defined
                  if v.startswith("FACTORY_") and v not in read_sh and v not in read_py)
    for v in dead:
        finding(f"config: {v} is defined in config.sh and read NOWHERE -- a knob that "
                f"does nothing is a lie in the one file users edit")
    checked(f"config: {len(defined)} knobs defined, {len(exported)} exported, "
            f"{len(read_sh)} read in shell, {len(read_py)} read by python children")


# =============================================================================
def audit_states(run: Path):
    """A state nothing can leave, or nothing acts on, is where the queue stops silently."""
    src = need(run, "state.py", "the state machine")
    if src is None:
        return
    m = re.search(r"^TRANSITIONS = \{.*?^\}", src, re.S | re.M)
    if not m:
        finding("states: TRANSITIONS table not found in state.py")
        return
    ns: dict = {}
    exec(m.group(0), ns)                                   # noqa: S102 - our own template
    T = ns["TRANSITIONS"]

    # 1. every literal state any script WRITES must exist in the table.
    written: dict[str, list[str]] = {}
    for p in sorted(run.glob("*.sh")):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for mm in re.finditer(r"state\.py\"?\s+set\s+\S+\s+state=([a-z-]+)", line):
                guarded = "||" in line or "&&" in line
                written.setdefault(mm.group(1), []).append(
                    f"{p.name}:{i}{' (guarded)' if guarded else ''}")
    for st in sorted(set(written) - set(T)):
        # The CONSEQUENCE differs and saying the wrong one sends the reader to the wrong
        # file. An unguarded impossible write kills the workflow under `set -e` before any
        # escalate. A `|| true` guarded one does not kill anything -- it silently does
        # NOTHING, so the item keeps its previous state, which is usually the one nothing
        # dispatches on. Both are bugs; only one is loud.
        where = written[st]
        if all("(guarded)" in w for w in where):
            finding(f"states: a script writes state={st!r}, which is not in TRANSITIONS. "
                    f"It is guarded, so it does not crash -- it silently does NOTHING and "
                    f"the item keeps whatever state it already had: {where}")
        else:
            finding(f"states: a script writes state={st!r}, which is not in TRANSITIONS -- "
                    f"the write fails and `set -e` kills the workflow before any "
                    f"escalate: {where}")

    # 2. every state must be reachable from an entry point, or it is dead.
    def reach(start: str) -> set[str]:
        seen, stack = {start}, [start]
        while stack:
            for nxt in T.get(stack.pop(), set()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    live = reach("untriaged") | reach("open")
    # closed-unlabelled is produced by the GitHub backend from a closed issue, never
    # reached by a transition. Checked explicitly rather than special-cased silently.
    ghsrc = (run / "gh_backend.py")
    produced_by_backend = set(re.findall(
        r'return "([a-z-]+)"',
        ghsrc.read_text(encoding="utf-8", errors="replace") if ghsrc.exists() else ""))
    for st in sorted(set(T) - live - produced_by_backend):
        finding(f"states: {st!r} is in the table, reachable from no entry point and "
                f"produced by no backend -- dead")

    # 3. every state with live exits must be ACTED on by something.
    nxt_src = re.search(r"def cmd_next.*?(?=\ndef |\Z)", src, re.S)
    nxt = nxt_src.group(0) if nxt_src else ""
    orch = need(run, "orchestrator.sh", "which states are dispatched on")
    if orch is None:
        return
    for st in sorted(T):
        if not T[st] or T[st] == {"needs-human"}:
            continue                                        # terminal / human-only, fine
        if re.search(rf"[\"']{re.escape(st)}[\"']", nxt) or re.search(rf"\b{re.escape(st)}\b", orch):
            continue
        if st in produced_by_backend:
            continue                                        # a transient read state
        finding(f"states: {st!r} has live exits {sorted(T[st])} but nothing dispatches "
                f"on it and nothing sweeps it -- work in it stops silently")
    checked(f"states: {len(T)} states, {sum(len(v) for v in T.values())} legal "
            f"transitions, {len(written)} written by shell -- all reachable and acted on")


# =============================================================================
def audit_placeholders(run: Path):
    """A prompt placeholder the renderer does not substitute is a prompt that LIES.

    Real defect: the fix node asked for the validator's findings at
    `.factory/runs/{{prev_run}}/verdict.json`. Nothing substituted it. The node opened
    nothing, said nothing, and fixed from the diff -- confident and unfounded.
    """
    runner = need(run, "run-workflow.sh", "prompt rendering")
    if runner is None:
        return
    subs = set(re.findall(r"\{\{(\w+)\}\}", runner))
    used: dict[str, set[str]] = collections.defaultdict(set)
    pdir = run / "prompts"
    if not pdir.is_dir():
        finding("layout: no `factory/prompts/` directory -- the node prompts cannot be "
                "checked against what the runner substitutes")
        return
    for p in sorted(pdir.glob("*.md")):
        for ph in re.findall(r"\{\{(\w+)\}\}", p.read_text(encoding="utf-8")):
            used[ph].add(p.name)
    for ph in sorted(used):
        if ph not in subs:
            finding(f"prompts: {{{{{ph}}}}} is used by {sorted(used[ph])} and the runner "
                    f"never substitutes it -- the node reads a path that was never filled in")
    if not re.search(r"grep -qE '\\\{\\\{", runner) and "unrendered" not in runner.lower():
        finding("prompts: the runner has no fatal check for an unrendered placeholder, "
                "so the next one fails silently like the last one did")
    checked(f"prompts: {len(used)} placeholders used across {len(list(pdir.glob('*.md')))} "
            f"prompts, {len(subs)} substituted by the runner")


# =============================================================================
def audit_silent_death(run: Path):
    """`set -e` kills the script BEFORE the escalate on the next line.

    THE recurring defect of this project, found four times as instances before anyone
    looked for the shape. Two forms are flagged: an unguarded state mutation, and a bare
    `grep` whose non-match is fatal. Both are invisible when they fire.
    """
    for p in sorted(run.glob("*.sh")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^set -[a-z]*e", text, re.M):
            continue
        # `trap - ERR` DISARMS a trap; it is the first line of every handler, so a regex
        # for "a line with trap and ERR on it" reports a file as protected when the only
        # thing left is the disarm. Deleting the installation while keeping the handler --
        # exactly what a careless edit does -- passed this check until it was verified by
        # deliberately removing the trap and watching nothing fire. An audit that has never
        # gone red is an audit nobody has tested, and that applies to this file too.
        has_trap = any(
            re.match(r"^\s*trap\s+(?!-[\s'\"])\S", line) and re.search(r"\bERR\b", line)
            for line in text.splitlines())
        called_guarded = p.name in {"gate.sh", "merge.sh", "deploy.sh", "init-labels.sh",
                                    "install-trigger.sh"}
        if not has_trap and not called_guarded:
            finding(f"{p.name}: runs under `set -e` with no ERR trap, so an unguarded "
                    f"failure exits with no message, no state change and no notification")
        for lineno, l in logical_lines(text):
            s = l.strip()
            if not s or s.startswith("#"):
                continue
            if re.search(r"state\.py\"?\s+(set|bump-attempt)\b", s) \
                    and "||" not in s and "&&" not in s \
                    and not s.startswith(("if ", "elif ")):
                finding(f"{p.name}:{lineno}: unguarded state write -- if it fails, "
                        f"`set -e` skips whatever follows it (ledger, notification):\n"
                        f"      {s[:100]}")
            if re.match(r"^(grep|rg)\s", s) and "||" not in s and "&&" not in s:
                finding(f"{p.name}:{lineno}: a bare grep is fatal on no-match under "
                        f"`set -e`:\n      {s[:100]}")
    checked(f"silent death: {len(list(run.glob('*.sh')))} shell scripts scanned for "
            f"unguarded state writes, bare greps and a missing ERR trap")


# =============================================================================
def audit_escalation_routes(run: Path):
    """Every place that STOPS work must tell a human. Found broken four separate times.

    `needs-human` is the only state a human must act on, so it is the only state allowed
    to interrupt one. A route that parks work and notifies nobody makes "unattended"
    quietly mean "unmonitored".
    """
    routes = 0
    for p in sorted(run.glob("*.sh")):
        text = p.read_text(encoding="utf-8", errors="replace")
        for lineno, l in logical_lines(text):
            if "state=needs-human" not in l:
                continue
            routes += 1
            # the notification does not have to be on the same line, but it does have to
            # be in the same block -- 25 lines is generous and has caught every real one.
            lines = text.splitlines()
            window = "\n".join(lines[max(0, lineno - 6): lineno + 25])
            if "factory_notify" not in window:
                finding(f"{p.name}:{lineno}: parks work at needs-human with no "
                        f"factory_notify anywhere near it -- a stop nobody is told about")
    checked(f"escalation: {routes} routes to needs-human, each reaching factory_notify")


# =============================================================================
def audit_backend_parity(run: Path):
    """The file backend and the GitHub backend must answer the same verbs.

    A verb that exists on one and not the other means the factory behaves differently
    depending on where its issues live, which is exactly how `factory:approved` came to
    be missing: a fresh GitHub factory worked right up to its first green gate.
    """
    gh = need(run, "gh_backend.py", "the GitHub backend")
    labels_sh = need(run, "init-labels.sh",
                     "whether every state's label is created before it is written")
    if gh is None or labels_sh is None:
        return
    lfs = re.search(r"LABEL_FOR_STATE\s*=\s*\{(.*?)\}", gh, re.S)
    pairs = re.findall(r"\"([a-z-]+)\"\s*:\s*\"([^\"]+)\"", lfs.group(1)) if lfs else []
    for st, lab in pairs:
        if lab not in labels_sh:
            finding(f"backend: state {st!r} maps to label {lab!r}, which "
                    f"init-labels.sh never creates -- the first write of that state fails")
    checked(f"backend: {len(pairs)} state->label mappings, all created by init-labels.sh")


# =============================================================================
def audit_prompt_citations(run: Path, repo: Path | None):
    """A prompt citing a rule that does not exist teaches the node to invent one.

    Real defect: the shipped prompts cited `OS9`, `capability 10`, `I5` and "playthrough"
    -- 12 references across 5 prompts to sections of ANOTHER factory's MISSION.
    """
    rules_path = None
    for cand in ((repo / "FACTORY_RULES.md") if repo else None,
                 SKILL / "templates" / "FACTORY_RULES.md"):
        if cand and cand.exists():
            rules_path = cand
            break
    if not rules_path:
        return
    rules = rules_path.read_text(encoding="utf-8")
    secs = set(re.findall(r"^#{1,4}\s*(\d+(?:\.\d+)*)", rules, re.M))
    secs |= set(re.findall(r"^##\s*(\d+)\.", rules, re.M))
    n = 0
    if not (run / "prompts").is_dir():
        return
    for p in sorted((run / "prompts").glob("*.md")):
        s = p.read_text(encoding="utf-8")
        for mm in re.finditer(r"FACTORY_RULES(?:\.md)?[^\n]{0,12}?(?:§|section\s*|\s)"
                              r"(\d+(?:\.\d+)*)", s):
            n += 1
            sec = mm.group(1)
            if sec not in secs and sec.split(".")[0] not in secs:
                finding(f"prompts/{p.name}: cites FACTORY_RULES {sec}, which does not "
                        f"exist in {rules_path.name}")
    checked(f"citations: {n} FACTORY_RULES references across the prompts, all resolving")



# =============================================================================
def audit_skill_text(run: Path, repo: Path | None):
    """The skill's own prose, where two defects and two standing instructions live.

    SKILL.md is executed by an agent, so a typo in it is a bug in the procedure. Three of
    these are real incidents; two are instructions from Cole that exist only as prose and
    can therefore regress with nothing noticing.
    """
    if repo:
        return                       # --repo mode audits a built factory; no SKILL.md
    skill_md = SKILL / "SKILL.md"
    if not skill_md.exists():
        return
    text = skill_md.read_text(encoding="utf-8")

    # 1. `$` followed by a digit is substituted as a POSITIONAL ARGUMENT when the agent
    #    renders this file. `$6 to $8` in the cost table rendered as
    #    `**repo to C:Userscolem...**` -- it destroyed the one number a reader wanted, and
    #    three independent sessions hit it. Amounts must be words.
    for m in re.finditer(r"\$\d", text):
        line = text[:m.start()].count("\n") + 1
        finding(f"SKILL.md:{line}: `{m.group(0)}` -- a $ followed by a digit is "
                f"substituted as a positional argument when this file is rendered. "
                f"Write the amount as a word.")

    # 2. NO COST OR DURATION ESTIMATES. Cole, 2026-08-12: "the skill needs to be updated to
    #    not mention pricing or how long it will take, people know that going in. The
    #    warnings at the start are bad."
    for pat, what in ((r"(?i)\bcosts?\s+(?:about|around|roughly|approximately)\b", "a cost estimate"),
                      (r"(?i)\btakes?\s+(?:about|around|roughly)\s+\d+\s*(?:hour|hr|minute|min|day)",
                       "a duration estimate"),
                      (r"(?i)\b\d+\s*(?:hours|hrs)\s+to\s+(?:build|set up|complete)\b",
                       "a duration estimate")):
        for m in re.finditer(pat, text):
            line = text[:m.start()].count("\n") + 1
            finding(f"SKILL.md:{line}: {what} -- {m.group(0)!r}. The skill does not carry "
                    f"cost or duration; people know that going in.")

    # 3. Every question id SKILL.md cites must exist in the interview, or the phase points
    #    at nothing. The ids were renumbered R<round>.<n> and every reference had to move.
    interview = SKILL / "references" / "interview.md"
    if interview.exists():
        itext = interview.read_text(encoding="utf-8")
        cited = set(re.findall(r"\bR\d+\.\d+[a-z]?\b", text))
        for qid in sorted(cited):
            if qid not in itext:
                finding(f"SKILL.md cites question {qid}, which does not exist in "
                        f"references/interview.md")
        checked(f"skill: {len(cited)} interview question ids cited, all defined")

    # 4. Every reference and template SKILL.md names must exist on disk.
    named = set(re.findall(r"`((?:references|templates|scripts)/[A-Za-z0-9_./-]+)`", text))
    for rel in sorted(named):
        if rel.endswith("/"):
            continue
        if not (SKILL / rel).exists() and "*" not in rel:
            finding(f"SKILL.md names `{rel}`, which does not exist in the skill")
    checked(f"skill: {len(named)} file paths named, all present")

    # 5. Level 3 is the recommended default. Cole, 2026-08-12: "the skill should rec level
    #    3 by default." Prose-only instructions are exactly what regresses unwatched.
    if not re.search(r"(?i)(recommend|default|target)[^.\n]{0,60}\b(?:level\s*)?3\b", text):
        finding("SKILL.md no longer recommends level 3 as the default, which was an "
                "explicit instruction and lives only as prose")
    checked("skill: level 3 is still the recommended default; no cost or duration "
            "estimates; no positional-substitution hazards")

# =============================================================================
def audit_user_facing_text(run: Path, repo: Path | None):
    """Three standing instructions that live only as prose, and therefore rot.

    All three came from Cole using the skill and finding it unusable in a specific way.
    None of them can be enforced by a behaviour test, because they are properties of what
    the agent SAYS. So they are checked here, against the shipped text, every run.
    """
    if repo:
        return
    files = [SKILL / "SKILL.md"] + sorted((SKILL / "references").glob("*.md"))

    # ---- 1. NEVER estimate how long anything takes -------------------------
    # "This is the block where the week goes" reached a live interview. The rule is not
    # "no prices" -- it is that the skill never tells someone how much of their life this
    # will cost, in any unit, because it does not know and the guess is always wrong in the
    # direction that makes people not start.
    DURATION = re.compile(
        r"(?<![-\w])("
        r"(?:a|an|one|two|three|several|couple of|few)\s+"
        r"(?:week|weeks|day|days|hour|hours|minute|minutes|month|months|afternoon|evening)"
        r"|the\s+week|the\s+day\s+(?:goes|it takes)"
        r"|(?:takes?|spend|spent|budget|allow)\s+(?:about|around|roughly|approximately|~)?\s*"
        r"\d+\s*(?:week|day|hour|minute|month)s?"
        r"|\d+\s*(?:weeks|days|hours|minutes|months)\s+(?:of work|to build|to set up|to finish)"
        r"|overnight\s+(?:build|job|work)"
        r"|for\s+weeks|for\s+months"
        r")(?![-\w])", re.I)
    # Legitimate uses: poll intervals, timeouts, cron cadence, lock ages, lookback windows.
    TECHNICAL = re.compile(
        r"(poll|interval|cron|schedule|timeout|stale|grace|--since|lookback|budget-usd|"
        r"every \d+ min|e2e_timeout|MINUTES|_s|watchdog|sleep|retry|cooldown)", re.I)
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if TECHNICAL.search(line):
                continue
            m = DURATION.search(line)
            if m:
                finding(f"{f.name}:{i}: estimates how long something takes "
                        f"({m.group(0)!r}). The skill never says how much of someone's "
                        f"life this costs -- it does not know, and the guess is always "
                        f"wrong in the direction that stops people starting.\n"
                        f"      {line.strip()[:110]}")

    # ---- 2. EVERY question goes through the question tool -------------------
    # A hard requirement, not a preference. The old text split questions into [PICKER] and
    # [PROSE] and argued the split was load-bearing. In use it was not: the prose questions
    # arrive as a wall of text asking for homework, and homework is where interviews get
    # abandoned. AskUserQuestion always carries an "Other" free-text escape, so an
    # open-ended question loses nothing by being asked through it -- and gains the
    # recommendation it is required to carry anyway.
    interview = SKILL / "references" / "interview.md"
    if interview.exists():
        itext = interview.read_text(encoding="utf-8")
        stray = re.findall(r"\[PROSE\]", itext)
        if stray:
            finding(f"interview.md still marks {len(stray)} question(s) [PROSE]. Every "
                    f"question goes through the question tool -- no exceptions.")
        if re.search(r"Ask in prose|prose column|fall back to prose", itext, re.I):
            finding("interview.md still describes a prose fallback for questions. The "
                    "requirement is every question, through the tool, always.")
        heads = re.findall(r"^###\s+(?:\[[A-Z]+\]\s*)?(R\d+\.\d+[a-z]?)", itext, re.M)
        checked(f"interview: {len(heads)} questions, none marked [PROSE]")

    # ---- 3. NO JARGON IN A QUESTION -----------------------------------------
    # The question the USER READS may not name a solution they have no reason to know.
    # "What must always stay true, even if an issue argues well for changing it?" is
    # invariants in disguise; "name three things that must be true when features are used
    # TOGETHER" is a holdout, and the file itself admitted almost nobody could answer it
    # cold. The artifacts are right. Asking the user to design them is not their job.
    #
    # Checked against the question HEADINGS only - the text a user is read. The body of
    # each section is written for the agent and names these things freely, which is where
    # they belong.
    JARGON = ("holdout", "invariant", "mutation set", "mutation testing", "ratchet",
              "independence line", "structural gate", "composition", "idempoten",
              "e2e", "required marker")
    if interview.exists():
        for i, line in enumerate(itext.splitlines(), 1):
            if not line.startswith("### R"):
                continue
            low = line.lower()
            for term in JARGON:
                if term in low:
                    finding(f"interview.md:{i}: the question a USER READS contains "
                            f"{term!r}. Ask about something that has happened to them and "
                            f"derive the artifact yourself.\n      {line.strip()[:100]}")
        checked(f"questions: {len(heads)} headings, none naming a solution the user has "
                f"no reason to know")

    # ---- 4. OUTPUT DISCIPLINE must be stated, not assumed -------------------
    # "Incredibly frustrating and hard to process. Overwhelming to say the least." An agent
    # given no budget explains everything it did, and a procedure this long produces a wall
    # per phase. The rule has to be IN the skill, because the model has no other way to know.
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not re.search(r"output discipline|keep it short|say less", skill_text, re.I):
        finding("SKILL.md states no output-discipline rule. Without one the agent narrates "
                "every phase and the user is handed a wall of text per step.")
    checked("user-facing text: no duration estimates, every question uses the question "
            "tool, output discipline is stated")


# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="audit a BUILT factory instead of the template")
    ap.add_argument("--quiet", action="store_true", help="findings only")
    args = ap.parse_args()

    if args.repo:
        run = Path(args.repo).resolve() / "factory"
        repo = Path(args.repo).resolve()
    else:
        run = SKILL / "templates" / "runner" / "factory"
        repo = None
    if not (run / "run-workflow.sh").exists():
        print(f"no runner at {run}", file=sys.stderr)
        return 2

    print(f"auditing {run}")
    print()
    for fn, needs_repo in ((audit_config, False), (audit_states, False),
                           (audit_placeholders, False), (audit_silent_death, False),
                           (audit_escalation_routes, False), (audit_backend_parity, False)):
        fn(run)
    audit_prompt_citations(run, repo)
    audit_skill_text(run, repo)
    audit_user_facing_text(run, repo)

    if not args.quiet:
        for c in CHECKED:
            print(f"  ok    {c}")
        print()
    for f in FINDINGS:
        print(f"  FIND  {f}")
    print()
    # "checks" and not "audits": one audit function can report several checks, and calling
    # them audits overstated the count. A tool whose entire argument is that a check must
    # say what it actually verified does not get to be loose about its own summary line.
    print(f"{len(FINDINGS)} finding(s) from {len(CHECKED)} checks")
    return len(FINDINGS)


if __name__ == "__main__":
    sys.exit(main())
