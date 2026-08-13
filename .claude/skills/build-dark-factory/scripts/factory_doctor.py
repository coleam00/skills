#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""factory_doctor - a deterministic audit of a dark factory repository.

Answers the questions a human keeps meaning to check and never does:

  - Do the governance files exist, and are they actually protected?
  - Can a secret-bearing config file still reach a commit?
  - Does anything treat "no failures" as "passed"?
  - Is the merge decision made by code, or by a model?
  - Does the validator read things the holdout forbids?
  - Is the deploy hanging off a trigger that silently never fires?
  - What autonomy level is this repo honestly at?

Everything here is a grep or a filesystem check. No model, no network, no opinions
that cannot be traced to a line number. Read the output, not the source.

Usage:
    python factory_doctor.py --repo /path/to/repo
    python factory_doctor.py --repo /path/to/repo --audit   # full, stricter
    python factory_doctor.py --repo /path/to/repo --json

Exit codes: 0 clean (warnings allowed) · 1 one or more FAILs · 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- model

FAIL, WARN, OK, INFO = "FAIL", "WARN", "OK", "INFO"
_ORDER = {FAIL: 0, WARN: 1, OK: 2, INFO: 3}


@dataclass
class Finding:
    level: str
    check: str
    message: str
    fix: str = ""
    evidence: list[str] = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, level, check, message, fix="", evidence=None) -> None:
        self.findings.append(Finding(level, check, message, fix, evidence or []))

    @property
    def failed(self) -> bool:
        return any(f.level == FAIL for f in self.findings)


# --------------------------------------------------------------------------- helpers

# Directories that are never the user's own factory code.
#
# `.worktrees` is on this list for a reason that is not tidiness. A linked worktree
# holds ANOTHER COMMIT's copy of the factory, and a stale one left behind by a crashed
# run can satisfy a check the current tree fails - the doctor cited
# `.worktrees/v15/factory/merge.sh` as proof that `gate-is-code` held. That is the same
# failure as running the protected-path guard from inside the worktree under review:
# the enforcement code came from the branch instead of from the base. An audit must
# read the tree it was pointed at and nothing else.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "target", "vendor", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".idea", ".vscode",
    ".worktrees", "worktrees",
}

# Per-run artifact directories: rendered prompts, plans, node stdout. They are OUTPUT,
# not the factory's definition, and reading them as definition is how a run that once
# printed the word "plan.md" becomes a permanent holdout finding.
SKIP_PATH_PREFIXES = (
    (".factory", "runs"),
    ("artifacts",),
)

# Files that plausibly drive the factory: workflows, commands, scripts, CI.
AUTOMATION_SUFFIXES = {".sh", ".bash", ".yaml", ".yml", ".py", ".ts", ".js", ".mjs"}

GOVERNANCE_CANDIDATES = [
    ("mission", ["MISSION.md"]),
    ("factory rules", ["FACTORY_RULES.md", "FACTORY-RULES.md"]),
    ("conventions", ["CLAUDE.md", "AGENTS.md", ".cursorrules", ".clinerules"]),
]

# Config files that commonly carry a live token and commonly are not ignored.
SECRET_CANDIDATES = [
    ".env", ".env.local", ".env.production",
    ".archon/config.yaml", ".archon/.env",
    ".claude/settings.local.json",
    "config/secrets.yml", "credentials.json", "service-account.json",
]


def _is_skill_payload(p: Path) -> bool:
    """This skill's own files, when it has been vendored into the repo it audits.

    Without this the doctor reads its own templates and its own source as evidence
    about the repo, and reports `gate-is-code` satisfied by `validate-gate.sh` that
    nobody wired up. Found end-to-end: a real audit cited factory_doctor.py itself
    as proof the repo merges in code.
    """
    parts = p.parts
    return any(parts[i] == ".claude" and i + 1 < len(parts) and parts[i + 1] == "skills"
               for i in range(len(parts)))


def _is_run_artifact(p: Path, root: Path) -> bool:
    try:
        parts = p.relative_to(root).parts
    except ValueError:
        return False
    return any(parts[: len(pre)] == pre for pre in SKIP_PATH_PREFIXES)


# The tree is walked ONCE and the result reused.
#
# Measured on a real application repo: one walk over ~9,800 files costs 4 seconds, and
# the checks below want ten of them - so the doctor took 49 seconds on a repo somebody is
# meant to audit habitually. An audit that slow is one people stop running, which costs
# more than any single check it performs is worth.
_WALK_CACHE: dict[str, list[Path]] = {}


def _all_files(root: Path) -> list[Path]:
    key = str(root)
    if key not in _WALK_CACHE:
        out = []
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if _is_skill_payload(p) or _is_run_artifact(p, root):
                continue
            out.append(p)
        _WALK_CACHE[key] = out
    return _WALK_CACHE[key]


def walk(root: Path, suffixes: set[str] | None = None):
    for p in _all_files(root):
        if suffixes and p.suffix.lower() not in suffixes:
            continue
        yield p


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p)


_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_RE = re.compile(r"`[^`\n]*`")


def strip_code(body: str) -> str:
    """Remove fenced blocks and inline spans.

    Angle brackets inside code are almost always real syntax - generics, shell
    placeholders, HTML - and flagging them as unfilled template slots is how a
    linter earns the right to be ignored.
    """
    return _INLINE_RE.sub(" ", _FENCE_RE.sub(" ", body))


# Every template in this skill carries this sentence. The placeholder check only
# applies to files actually derived from those templates; a hand-written CLAUDE.md
# that happens to mention <HTMLInputElement> is not an unfilled template.
TEMPLATE_SENTINEL = re.compile(r"Replace every <angle-bracket> placeholder", re.I)

# Words that turn a nearby match into a prohibition rather than a read.
NEGATION_RE = re.compile(
    r"\b(never|not|no|must not|cannot|forbidden|prohibit|exclude|excluding|"
    r"without|deny|denied|blocked|violation|tripwire|leak)\b", re.I)

# Shapes that indicate something is actually being READ.
READ_RE = re.compile(
    r"(\bcat\b|\bless\b|\bhead\b|\btail\b|\bsource\b|\bopen\(|readFile|read_text|"
    r"git\s+show|--json[^\n]*comments|\bRead\b\s*\(|\$\(<|<\s*\"?\$)", re.I)

# A judge is usually a PROMPT, and a prompt does not say `cat plan.md`. It says "read the
# implementation plan before judging". READ_RE only recognises code, so scanning prompt
# markdown without this finds nothing: a planted leak audited clean, and the one real leak
# in a production factory was caught only because its line happened to use shell `head`.
# Applied to markdown only, and only to validator-named files, so prose never reaches the
# code paths. Prohibitions are still filtered by NEGATION_RE first.
PROSE_READ_RE = re.compile(
    r"\b(re-?read|read|review|inspect|consult|refer\s+to|look\s+at|examine|"
    r"open|load|check)\b", re.I)


def git(root: Path, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=20)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


# --------------------------------------------------------------------------- checks

def check_governance(root: Path, rep: Report) -> dict[str, Path]:
    """The three files exist, and none still carry template placeholders."""
    found: dict[str, Path] = {}
    for label, names in GOVERNANCE_CANDIDATES:
        hit = next((root / n for n in names if (root / n).is_file()), None)
        if hit:
            found[label] = hit
        else:
            rep.add(FAIL, "guidance-layer", f"no {label} file found",
                    f"create one of: {', '.join(names)}")

    for label, path in found.items():
        body = read(path)
        placeholders: list[str] = []
        if TEMPLATE_SENTINEL.search(body):
            placeholders = [m for m in re.findall(r"<[A-Za-z][^>\n]{2,60}>",
                                                  strip_code(body))
                            if not m.startswith("</")]
        if placeholders:
            rep.add(FAIL, "guidance-layer",
                    f"{rel(path, root)} still contains {len(placeholders)} unfilled "
                    f"template placeholder(s) - the factory would be reading "
                    f"instructions that were never written",
                    "fill every <angle-bracket> placeholder, then delete the "
                    "instruction comment at the top of the file",
                    sorted(set(placeholders))[:8])
        elif len(body.strip()) < 400:
            rep.add(WARN, "guidance-layer",
                    f"{rel(path, root)} is very short ({len(body.strip())} chars)",
                    "an unsupervised agent needs more than a paragraph to stay in scope")
        else:
            rep.add(OK, "guidance-layer", f"{rel(path, root)} present and filled in")

    return found


def check_out_of_scope(root: Path, gov: dict[str, Path], rep: Report) -> None:
    """The out-of-scope list is the section people skip, and it does the most work."""
    mission = gov.get("mission")
    if not mission:
        return
    body = read(mission)
    m = re.search(r"^#{1,3}\s*out of scope.*$", body, re.I | re.M)
    if not m:
        rep.add(FAIL, "out-of-scope",
                "MISSION has no 'Out of scope' section",
                "without it every plausible feature request is arguably in scope, "
                "and the agent has no way to recognise drift as drift")
        return
    tail = body[m.end():]
    nxt = re.search(r"^#{1,3}\s", tail, re.M)
    section = tail[: nxt.start()] if nxt else tail
    # Bullets AND bold sub-headings. Counting only bullets reported "0 items" against a
    # MISSION whose out-of-scope section was eight bold headings with prose under each -
    # a false negative on the single most load-bearing list in the build, and one that
    # tells a user their governance is empty when it is fine. Found on a real build.
    items = re.findall(r"^\s*[-*]\s+\S", section, re.M)
    items += re.findall(r"^\s*\*\*[^*\n]+\*\*\s*$", section, re.M)
    if len(items) < 5:
        rep.add(WARN, "out-of-scope",
                f"the out-of-scope list has only {len(items)} item(s)",
                "name at least five things you would reject even if a user asked "
                "nicely and the code would be easy")
    else:
        rep.add(OK, "out-of-scope", f"{len(items)} out-of-scope items declared")


def check_prd_provenance(root: Path, gov: dict[str, Path], rep: Report) -> None:
    """MISSION should name the PRD it was compressed from.

    Advisory on purpose. A missing pointer is not a broken factory, it is a factory
    that will silently keep building last quarter's scope once the product moves and
    nobody can tell which document is now wrong.
    """
    mission = gov.get("mission")
    if not mission:
        return
    body = read(mission)
    # THE COLON IS OPTIONAL, and requiring it was a false positive on a MISSION that said
    # exactly what the check asks for. "Derived from `docs/shortlink.prd.md`." - no colon,
    # perfectly clear provenance, reported as "MISSION does not name the PRD it came
    # from". A checker that fails on the thing it just asked for is worse than no checker:
    # it teaches people that its warnings are noise, and they are right.
    #
    # Without the colon the marker alone is too weak (the word "prd" appears in prose), so
    # a colon-less line must also carry something path-shaped - a backticked span, a
    # markdown link, or a token ending in .md. That is the difference between a provenance
    # line and a sentence mentioning the PRD.
    m = re.search(r"^\s*\*{0,2}(derived from|source|prd)\*{0,2}\s*:\s*(.+)$",
                  body, re.I | re.M)
    if not m:
        m2 = re.search(r"^\s*\*{0,2}(derived from|source|prd)\*{0,2}\s+"
                       r"(.*(?:`[^`\n]+`|\]\([^)\s]+\)|\S+\.md).*)$",
                       body, re.I | re.M)
        if m2:
            m = m2
    if not m:
        rep.add(WARN, "prd", "MISSION does not name the PRD it came from",
                "add a 'Derived from:' line so the next person can tell whether the "
                "mission or the product drifted")
        return
    tail = m.group(2).strip()
    # A real provenance line is prose, not a bare path: "`docs/x.prd.md` - the PRD,
    # vendored on ...". Take the first backticked span, else the first whitespace
    # token, else the whole tail. Taking the whole tail was reported end-to-end as a
    # dangling pointer against a PRD that was sitting right there.
    backticked = re.search(r"`([^`\n]+)`", tail)
    if backticked:
        target = backticked.group(1)
    else:
        link = re.search(r"\]\(([^)\s]+)\)", tail)
        target = link.group(1) if link else tail.split()[0]
    target = target.strip().strip("`<>*,;")
    if target.startswith(("http://", "https://")):
        rep.add(OK, "prd", "MISSION cites its source PRD")
        return
    # A relative path is only useful if it still resolves.
    cand = (root / target).resolve()
    if cand.exists() or (mission.parent / target).exists():
        rep.add(OK, "prd", "MISSION cites its source PRD")
    else:
        rep.add(WARN, "prd", f"MISSION cites a PRD that is not there: {target}",
                "either fix the path or move the PRD into the repo; a dangling "
                "pointer is worse than none because it reads as provenance")


def check_protected(root: Path, gov: dict[str, Path], rep: Report) -> None:
    """Governance files must appear on their own protected list."""
    rules = gov.get("factory rules")
    if not rules:
        return
    body = read(rules)
    missing = [rel(p, root) for p in gov.values() if Path(rel(p, root)).name not in body]
    if missing:
        rep.add(FAIL, "protected-list",
                "governance file(s) are not named in the protected list",
                "the agent must not be able to amend the rules it is judged by",
                missing)
    else:
        rep.add(OK, "protected-list", "all governance files are on the protected list")


def check_ignored_secrets(root: Path, rep: Report) -> None:
    """The scar: `git add -A` inside a PR step publishes whatever was not ignored."""
    code, _ = git(root, "rev-parse", "--git-dir")
    if code != 0:
        rep.add(WARN, "secrets", "not a git repository - skipping ignore checks")
        return

    # Checked whether or not the file EXISTS, and that is the whole point.
    #
    # This used to skip any candidate that was not on disk, which reads as sensible and
    # is backwards: the file that hurts you is the one that appears for the first time
    # in three weeks, inside a `git add -A` in a step nobody is watching. A repo with no
    # `.env` today and no rule against one audited perfectly clean, and the runner's own
    # pre-flight - which does NOT skip missing files - would refuse to start on it.
    # The auditor and the thing it audits disagreeing is worse than either being wrong.
    # Two severities, calibrated to agree with the runner rather than to be loud.
    #
    # BLOCKING: the three paths `run-workflow.sh`'s pre-flight asserts. Not ignoring one
    # of these is not advice - the factory refuses to start. Plus anything actually on
    # disk, because that is a live exposure rather than a hypothetical.
    #
    # ADVISORY: tool configs that commonly hold a token but that this repo may simply not
    # use. Failing a repo for not ignoring an Archon config when it does not use Archon is
    # the kind of finding that teaches people to skim the report, and a skimmed report is
    # worth nothing on the day it is right.
    blocking_names = {".env", ".env.local", ".env.production",
                      "secrets.json", "credentials.json"}
    exposed, advisory, checked = [], [], 0
    for name in SECRET_CANDIDATES:
        checked += 1
        rc, _ = git(root, "check-ignore", "-q", name)
        if rc == 0:
            continue
        on_disk = (root / name).exists()
        label = name if on_disk else name + " (not present yet)"
        if on_disk or name in blocking_names:
            exposed.append(label)
        else:
            advisory.append(label)

    tracked_rc, tracked = git(root, "ls-files", "--", "*.env", ".env*", "*secret*",
                              "*credential*")
    tracked_hits = [ln for ln in tracked.splitlines() if ln.strip()] if tracked_rc == 0 else []

    if exposed:
        rep.add(FAIL, "secrets",
                f"{len(exposed)} credential-shaped path(s) are NOT git-ignored",
                "a workflow that runs `git add -A` will commit these the moment one "
                "appears. On a public repo that is publication, and rotating afterwards "
                "is cleanup, not a fix. The runner's own pre-flight refuses to start "
                "until this is fixed - copy templates/runner/.gitignore",
                exposed)
    elif checked:
        rep.add(OK, "secrets", f"{checked} credential-shaped path(s) all git-ignored")

    if advisory:
        rep.add(WARN, "secrets",
                f"{len(advisory)} tool-config path(s) that commonly hold a token are not "
                f"ignored",
                "harmless if you do not use that tool. Add the ones you do use - the file "
                "that hurts you is the one that appears for the first time inside a "
                "`git add -A` nobody is watching",
                advisory)

    # The factory's own artifacts. Committing `.factory/runs/` puts the implementer's
    # PLAN on the branch, where the validator can read it - which destroys the holdout
    # property the entire auto-merge argument rests on, silently, via a tidy-looking diff.
    if (root / "factory").is_dir():
        # Queried as a path INSIDE the directory, not as the directory itself. A
        # dir-only pattern (`foo/`) does not match a bare `foo` that does not exist on
        # disk yet, so checking the directory name reports "not ignored" for a rule that
        # is present and correct - and the first run, which creates it, would be the
        # thing that proved otherwise. Ask the question the way git can answer it.
        leaky = [p for p in (".factory/runs", ".factory/locks-runtime")
                 if git(root, "check-ignore", "-q", p + "/probe")[0] != 0]
        if leaky:
            rep.add(WARN, "secrets",
                    "the factory's own run artifacts are not git-ignored",
                    "`.factory/runs/` holds rendered prompts, plans and node output. "
                    "Committed, the builder's plan reaches the validator and the holdout "
                    "is gone. Copy templates/runner/.gitignore",
                    leaky)

    if tracked_hits:
        rep.add(FAIL, "secrets",
                "secret-shaped files are already TRACKED in git",
                "remove from the index and rotate whatever they contained",
                tracked_hits[:8])


def check_empty_is_not_pass(root: Path, rep: Report) -> None:
    """Positive markers, not the absence of the word 'error'."""
    negative_re = re.compile(
        r"(grep\s+-[a-zA-Z]*\s*-?v[a-zA-Z]*\s+[\"']?(error|fail)|"
        r"!\s*grep\s+-q\s+[\"']?(error|fail)|"
        r"if\s+\[\s+-z\s+\"?\$\{?(ERRORS?|FAILURES?)|"
        # -z on a command substitution that greps: `[ -z "$(echo "$OUT" | grep ERROR)" ]`.
        # The named-variable form above missed this entirely, and it is the more common
        # shape in the wild because it does the grep inline.
        r"-z\s+\"?\$\((?=[^)]*grep))", re.I)
    positive_re = re.compile(r"(APP_STARTED|E2E_PASSED|_PASSED|_RAN|steps=)", re.I)

    # What the branch DOES decides whether this is the bug or the fix for it.
    #
    # Testing for emptiness is not the defect. Testing for emptiness and then carrying on
    # with a green default is. A script that says `if [ -z "$FAILURES_JSON" ]; then exit 1`
    # is doing exactly what this check exists to demand, and flagging it taught the reader
    # that the finding is noise - which is how a real one later gets skimmed past.
    handled_re = re.compile(
        r"(exit\s+[1-9]|\bfail\b|\bescalate\b|>&2|\bdie\b|return\s+[1-9]|"
        r"GATE_FAIL|_UNPARSEABLE|INFRA_FAILURE)", re.I)

    negatives, positives = [], []
    for p in walk(root, AUTOMATION_SUFFIXES):
        body = read(p)
        lines = body.splitlines()
        for m in negative_re.finditer(body):
            idx = body[: m.start()].count("\n")
            # The branch body: from the match to the closing `fi`, capped so a match near
            # the end of a long file does not swallow the rest of it.
            window = "\n".join(lines[idx: idx + 12])
            cut = re.search(r"^\s*(fi|\})\s*$", window, re.M)
            if cut:
                window = window[: cut.start()]
            if handled_re.search(window):
                continue
            negatives.append(f"{rel(p, root)}:{idx + 1}  {m.group(0).strip()}")
        if positive_re.search(body):
            positives.append(rel(p, root))

    if negatives:
        # WARN, not FAIL: a negative grep is often legitimate output filtering.
        # The finding that actually blocks is the missing positive marker below.
        rep.add(WARN, "empty-is-not-pass",
                f"{len(negatives)} place(s) appear to judge success by the ABSENCE "
                f"of an error string - check whether any of them gates a decision",
                "a check that never ran produces no errors, so this reads a skipped "
                "check as a passed one. Where it gates, assert a positive marker and "
                "a count instead",
                negatives[:8])
    if not positives:
        rep.add(FAIL, "empty-is-not-pass",
                "no positive success marker found anywhere (APP_STARTED, E2E_PASSED, "
                "steps=...)",
                "emit an explicit marker on success and have the gate grep for its "
                "presence")
    else:
        rep.add(OK, "empty-is-not-pass",
                f"positive success markers present in {len(set(positives))} file(s)")


def check_gate_is_code(root: Path, rep: Report) -> None:
    """The merge must be performed by a script reading a verdict, not by a model."""
    merge_re = re.compile(r"gh\s+pr\s+merge|--squash|merge_pull_request", re.I)
    prompt_suffixes = {".md", ".txt"}

    in_code, in_prompt = [], []
    for p in walk(root):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in AUTOMATION_SUFFIXES:
            if merge_re.search(read(p)):
                in_code.append(rel(p, root))
        elif p.suffix.lower() in prompt_suffixes and "FACTORY" not in p.name.upper():
            body = read(p)
            if merge_re.search(body) and re.search(r"\byou (should|must|can)\b", body, re.I):
                in_prompt.append(rel(p, root))

    if not in_code:
        rep.add(FAIL, "gate-is-code",
                "no script performs the merge",
                "the merge must be a script that reads a verdict file and branches "
                "on it. A model that decides to merge is a suggestion with good manners")
    else:
        rep.add(OK, "gate-is-code",
                f"merge performed in code: {', '.join(sorted(set(in_code))[:3])}")

    if in_prompt:
        rep.add(WARN, "gate-is-code",
                "a prompt file appears to instruct a model to merge",
                "move the merge decision into the script and leave the model to "
                "produce a verdict only",
                sorted(set(in_prompt))[:5])


# Which SIDE of the pipeline a step belongs to, resolved from its name. Used only to
# classify CALLERS; what a callee is gets decided by who calls it.
VALIDATOR_NAME_RE = re.compile(r"valid|review|verdict|judge|\bqa\b", re.I)
BUILDER_NAME_RE = re.compile(
    r"implement|fix[-_]?(issue|pr|github)|build|plan|create[-_]pr|scope|triage|prime",
    re.I)


def _caller_side(name: str) -> str:
    """'validator', 'builder', or 'unknown' - for a file that CALLS other steps."""
    v, b = bool(VALIDATOR_NAME_RE.search(name)), bool(BUILDER_NAME_RE.search(name))
    if v and not b:
        return "validator"
    if b and not v:
        return "builder"
    return "unknown"


def _validator_files(root: Path) -> tuple[list[Path], list[Path]]:
    """Split validator-NAMED files into (confirmed, unconfirmed) by reference.

    A command or prompt is builder-side if every automation file that references it is
    builder-side - `pr-review-scope` reached only from `fix-github-issue` is the
    builder reviewing its own work, and it is entitled to read the plan it just wrote.
    Those are dropped from the validator set entirely.

    Everything else stays confirmed, deliberately. The bug being fixed is a false
    POSITIVE, and a fix that trades it for a false negative on a factory whose pipeline
    lives in one runner script is a worse trade: a missed holdout leak is the failure
    this whole check exists to catch. Only an orphan - a validator-named file nothing
    references, which therefore is not running - lands in `unconfirmed`.
    """
    candidates = [p for p in walk(root, AUTOMATION_SUFFIXES | {".md"})
                  if VALIDATOR_NAME_RE.search(p.name)]
    callers = [p for p in walk(root, AUTOMATION_SUFFIXES)]
    caller_bodies = [(p, read(p)) for p in callers]

    confirmed, unconfirmed = [], []
    for c in candidates:
        # A workflow or script that IS a top-level step counts as its own caller.
        sides = set()
        if c.suffix.lower() in AUTOMATION_SUFFIXES:
            sides.add(_caller_side(c.name))

        stem_re = re.compile(r"(?<![\w-])" + re.escape(c.stem) + r"(?![\w-])")
        for p, body in caller_bodies:
            if p == c:
                continue
            if stem_re.search(body):
                sides.add(_caller_side(p.name))

        if not sides:
            unconfirmed.append(c)          # nothing references it; it is not running
        elif sides == {"builder"}:
            continue                       # builder-side by reference: not a validator
        else:
            confirmed.append(c)
    return confirmed, unconfirmed


def check_holdout(root: Path, rep: Report) -> None:
    """The validator must not be handed the builder's reasoning.

    The hard part of this check is not spotting a read. It is knowing WHOSE file you
    are reading.

    The first version matched on the FILE NAME alone, so any step with "review" in it
    counted as the independent validator - including a builder-side self-review that is
    *supposed* to read the plan it just wrote. On a real factory that produced a FAIL
    against `pr-review-scope`, a command referenced only by the implement workflow, and
    the FAIL then cascaded into a second one and a red bottom line on a repo whose
    holdout was intact. A heuristic that can block on a guess is worse than no check,
    because the person who trusts it stops reading the evidence.

    So the side is now resolved from the reference graph: who CALLS this file. A command
    reached only from `implement`/`fix` is builder-side however it is named, and a leak
    there is not a leak. Where the graph cannot answer, the finding drops to WARN and
    says it could not confirm - a heuristic may report, it may not block.
    """
    leak_re = re.compile(
        r"(plan\.md|plan[-_]context|implementation\.md|investigation\.md|design[-_]notes|"
        r"--comments|\.comments|scratch|rationale)", re.I)

    confirmed, unconfirmed = _validator_files(root)
    validators = confirmed + unconfirmed
    confirmed_set = {p for p in confirmed}

    def scan(paths: list[Path]) -> list[str]:
        out: list[str] = []
        for p in paths:
            body = read(p)
            lines = body.splitlines()
            for m in leak_re.finditer(body):
                idx = body[: m.start()].count("\n")
                line = lines[idx] if idx < len(lines) else ""
                # A prohibition ("NEVER read plan.md") and a tripwire that asserts the
                # artifact is absent both mention the artifact. Neither is a leak.
                if NEGATION_RE.search(line):
                    continue
                # Only flag when the line actually looks like a read. Prompts are prose,
                # so markdown gets the prose pattern as well as the code one.
                reader = READ_RE.search(line) or (
                    p.suffix.lower() == ".md" and PROSE_READ_RE.search(line))
                if not reader:
                    continue
                out.append(f"{rel(p, root)}:{idx + 1}  {line.strip()[:90]}")
        return out

    if not validators:
        rep.add(WARN, "holdout", "no validator-shaped file found to inspect",
                "expected something named validate/review/verdict")
    else:
        hard = scan(confirmed)
        soft = scan(unconfirmed)

        if hard:
            rep.add(FAIL, "holdout",
                    "the independent validator reads builder artifacts",
                    "a validator that sees the plan is grading the story, not the code. "
                    "It gets the issue, the diff, and the output of checks it ran itself",
                    hard[:8])
        if soft:
            rep.add(WARN, "holdout",
                    f"{len(soft)} builder-artifact read(s) in validator-NAMED files whose "
                    f"side could not be confirmed from the reference graph",
                    "check by hand whether these run inside the independent validator or "
                    "inside the builder's own review step. Only the first is a violation",
                    soft[:8])
        if not hard and not soft:
            rep.add(OK, "holdout",
                    f"no builder-artifact reads found in {len(validators)} validator "
                    f"file(s) ({len(confirmed_set)} confirmed by reference)")

    _check_base_governance(root, rep)


def _check_base_governance(root: Path, rep: Report) -> None:
    """Governance must be read from the base branch, not from the PR under review.

    Scanned REPO-WIDE, and this is the correction that matters. The old version only
    looked inside files whose name matched validate/review/verdict, so a factory that
    consolidated its pipeline into one runner script stopped being seen to do the thing
    it was still doing on line 389. Worse, that regression was introduced BY a genuine
    safety fix: deleting a set of drifted workflow YAMLs - which had been claiming a
    holdout deny nothing enforced - removed the only filenames this check would look at.
    Fixing a real hole made the audit lie about it.

    The property is behavioural, so detect the behaviour: a governance file read at a
    ref. `git show "$BASE:MISSION.md"` and `git show origin/main:MISSION.md` are the
    same act. A bare `git fetch origin` is NOT accepted as evidence any more; every
    factory fetches, and fetching is not reading.
    """
    gov_names = r"(?:MISSION|FACTORY[-_]?RULES|CLAUDE|AGENTS)\.md"
    base_read_re = re.compile(
        # git show <ref>:GOVERNANCE.md - the ref may be $BASE, ${BASE}, origin/main, main
        r"git\s+show\s+[\"']?\$?\{?[A-Za-z_][\w./-]*\}?\s*:\s*" + gov_names
        # explicit base-ref plumbing around a governance path
        + r"|--ref[= ]\s*origin/\S*\s+" + gov_names
        + r"|origin/[\w.-]+\s*:\s*" + gov_names,
        re.I)

    hits = [rel(p, root) for p in walk(root, AUTOMATION_SUFFIXES | {".md"})
            if base_read_re.search(read(p))]

    if hits:
        rep.add(OK, "holdout",
                f"governance is read from the base branch in {len(set(hits))} file(s)",
                evidence=sorted(set(hits))[:3])
    else:
        rep.add(WARN, "holdout",
                "governance does not appear to be read from the base branch",
                "read MISSION / FACTORY_RULES from the base ref before checking out the "
                "PR, or a PR can weaken the rulebook it is judged against")


def check_deploy_trigger(root: Path, rep: Report) -> None:
    """The trap: default-token commits do not trigger workflows."""
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        rep.add(INFO, "deploy-trigger", "no .github/workflows - deployment is elsewhere")
        return

    push_triggered, app_auth, scheduled_on_branch = [], False, []
    for p in wf_dir.glob("*.y*ml"):
        body = read(p)
        name = rel(p, root)
        if re.search(r"^\s*on:.*\bpush\b", body, re.M | re.S) or re.search(
                r"^\s{2,}push:", body, re.M):
            if re.search(r"deploy|release|publish|ship", body, re.I):
                push_triggered.append(name)
        if re.search(r"create-github-app-token|app[-_]id|APP_PRIVATE_KEY|"
                     r"secrets\.(PAT|GH_TOKEN|DEPLOY_TOKEN)", body, re.I):
            app_auth = True
        if re.search(r"^\s{2,}schedule:", body, re.M):
            scheduled_on_branch.append(name)

    if push_triggered and not app_auth:
        rep.add(FAIL, "deploy-trigger",
                "a deploy workflow is push-triggered with no App or PAT auth in sight",
                "GitHub does not trigger workflows on commits made with the default "
                "GITHUB_TOKEN. Your agent commits, the deploy never fires, and nothing "
                "errors. Authenticate as a GitHub App, or poll the branch instead",
                push_triggered)
    elif push_triggered:
        rep.add(OK, "deploy-trigger",
                "deploy is push-triggered and non-default auth is configured")

    if scheduled_on_branch:
        rep.add(INFO, "deploy-trigger",
                "scheduled workflows present - they only run from the default branch, "
                "and on a public repo GitHub disables them after 60 days of no "
                "repository activity",
                evidence=scheduled_on_branch)


def check_validate_command(root: Path, rep: Report) -> None:
    """The factory must point at a validation harness that EXISTS.

    Found end-to-end, and it is the doctor's own version of empty-is-not-pass: a repo
    whose `FACTORY_VALIDATE_CMD` pointed at a `harness/ci.py` that had never been written
    audited **Clean, 0 FAIL, 11 OK**. Every other check passed because the guidance layer
    and the runner were both real - and the one component that decides whether any of it
    was worth keeping did not exist at all.

    That is the worst possible moment to print "Clean": Phase 2, to a newcomer, who reads
    it as "done" at exactly the point the hard part has not started.
    """
    cfg = root / "factory" / "config.sh"
    if not cfg.is_file():
        return                                   # not a runner-shaped factory; nothing to check

    m = re.search(r"FACTORY_VALIDATE_CMD=\"?\$\{FACTORY_VALIDATE_CMD:-([^}\"]+)", read(cfg))
    if not m:
        rep.add(WARN, "validate-command",
                "factory/config.sh does not set FACTORY_VALIDATE_CMD",
                "the gate has nothing to run; component 5 is the one that decides "
                "whether the other four produced anything worth keeping")
        return

    cmd = m.group(1).strip()
    # The first token that looks like a path in the repo. Good enough to catch the case
    # that matters - the default was never replaced and points at nothing.
    target = next((tok for tok in cmd.split()
                   if "/" in tok or tok.endswith((".py", ".sh", ".js", ".ts"))), None)
    if target and not (root / target).exists():
        rep.add(FAIL, "validate-command",
                f"FACTORY_VALIDATE_CMD points at something that does not exist: {target}",
                f"`{cmd}` is what the gate runs. Until that file exists there is no "
                f"validation harness, and every other check passing means only that the "
                f"plumbing is sound")
    else:
        rep.add(OK, "validate-command", f"the gate's validate command resolves: {cmd}")


def check_prompt_placeholders(root: Path, rep: Report) -> None:
    """Every `{{placeholder}}` a prompt uses must be one the runner actually substitutes.

    THE QUIETEST WAY A NODE CAN FAIL. `fix.md` asked for the validator's findings at
    `.factory/runs/{{prev_run}}/verdict.json`, and the renderer had no `{{prev_run}}` rule.
    So the fix node was handed a literal path containing braces. It did not crash and it
    did not refuse - it opened nothing, worked from the diff, and produced a confident
    commit built on no evidence at all. That is worse than a node that did not run,
    because it looks exactly like one that did.

    The prompts are the file users are told to rewrite, which is precisely why this needs
    a check: a rewrite can invent a placeholder, and nothing else in the system would ever
    mention it. Read from the renderer, not from a hardcoded list, so adding a
    substitution to the runner keeps this honest for free.
    """
    runner = root / "factory" / "run-workflow.sh"
    pdir = root / "factory" / "prompts"
    if not runner.is_file() or not pdir.is_dir():
        return

    known = set(re.findall(r"s\|\{\{([a-z_]+)\}\}\|", read(runner)))
    if not known:
        rep.add(WARN, "prompt-placeholders",
                "factory/run-workflow.sh renders no {{placeholders}} at all",
                "every prompt is then a static file, and {{issue}} reaches the node as "
                "the literal characters")
        return

    bad: list[str] = []
    for p in sorted(pdir.glob("*.md")):
        for name in sorted(set(re.findall(r"\{\{([a-z_]+)\}\}", read(p)))):
            if name not in known:
                bad.append(f"{p.name}: {{{{{name}}}}}")

    if bad:
        rep.add(FAIL, "prompt-placeholders",
                "a prompt uses a placeholder the runner never substitutes: "
                + ", ".join(bad),
                "the node receives the braces verbatim, opens nothing, and reasons from "
                f"no evidence without ever reporting a problem. The runner renders: "
                f"{', '.join('{{' + k + '}}' for k in sorted(known))}")
    else:
        rep.add(OK, "prompt-placeholders",
                f"every placeholder in {len(list(pdir.glob('*.md')))} prompt(s) is one the "
                f"runner substitutes")


def check_browser_available(root: Path, rep: Report) -> None:
    """If the harness declares a browser, prove it is installed HERE.

    A frontend factory's e2e drives a real browser, and nothing in the scaffold knew that.
    Browser automation appeared nowhere in the config, so there was no way to check for it
    and nothing did - a fresh CI runner or a new VPS discovered the gap at gate time, as a
    hang or an exception three rungs in, on an unattended run nobody was watching.

    Declared and checked at setup instead, where the answer is an install command.
    `install_check` is empty by default: an app with no screen should not be told to
    install a browser.
    """
    cfg = root / "harness" / "harness.config.json"
    if not cfg.is_file():
        return
    try:
        data = json.loads(read(cfg))
    except (ValueError, OSError):
        return
    b = data.get("browser") or {}
    cmd = (b.get("install_check") or "").strip()
    if not cmd:
        return                                   # not a visual app; nothing to check
    argv = shlex.split(cmd, posix=False)
    exe = shutil.which(argv[0]) if argv else None
    if not exe:
        rep.add(FAIL, "browser",
                f"harness.config.json declares a browser check ({cmd}) but {argv[0]!r} "
                f"is not on PATH",
                f"the e2e rung drives a browser and this machine does not have one. "
                f"{b.get('install_hint', 'install it, and on whatever runs the factory too')}")
        return
    try:
        p = subprocess.run([exe, *argv[1:]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        ok = p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if ok:
        rep.add(OK, "browser", f"the declared browser check passes: {cmd}")
    else:
        rep.add(FAIL, "browser",
                f"the declared browser check failed: {cmd}",
                f"it is on PATH but does not run. {b.get('install_hint', '')}".strip())


SCAFFOLD_SENTINEL = "SCAFFOLD_EXAMPLE_DELETE_THIS_LINE_WHEN_YOU_WRITE_YOUR_OWN"
PROMPT_SENTINEL = "THIS PROMPT IS THE INTERVIEW'S OUTPUT"


def check_scaffold_edited(root: Path, rep: Report) -> None:
    """Has the user replaced the worked examples with their own?

    THE FAILURE MODE THE SCAFFOLDS CREATED. Shipping runnable examples removes a day of
    plumbing and introduces a new way to fail: ship the example. A factory whose E2E
    still asserts somebody else's product, whose holdout probes somebody else's domain,
    and whose defect set names files that do not exist here would pass every other check
    in this report and print GATE_OK - and then auto-merge on evidence about software it
    is not.

    That is worse than having no harness, because it is green.

    Each scaffold carries one line the user deletes when the content becomes theirs. The
    same trick as the `<angle-bracket>` sentinel on the governance templates, for the
    same reason: intent is not detectable, but a deliberate deletion is.
    """
    unedited = []
    for p in walk(root, {".py", ".json", ".md", ".ts", ".js"}):
        body = read(p)
        if SCAFFOLD_SENTINEL in body:
            unedited.append(rel(p, root))
    prompts = [rel(p, root) for p in walk(root, {".md"})
               if "prompts" in p.parts and PROMPT_SENTINEL in read(p)]

    declared, _ = _declared_level(root)

    if unedited:
        level = FAIL if (declared is not None and declared >= 2) else WARN
        rep.add(level, "scaffold",
                f"{len(unedited)} harness file(s) still carry the scaffold's example",
                "these assert things about the template's sample product, not yours. "
                "Replace the assertions, then delete the marker line. A gate that is "
                "green about the wrong software is worse than no gate",
                unedited[:6])
    elif (root / "harness").is_dir() or (root / ".factory" / "holdout").is_dir():
        rep.add(OK, "scaffold", "no scaffold examples left in the harness")

    if prompts:
        level = FAIL if (declared is not None and declared >= 2) else WARN
        rep.add(level, "scaffold",
                f"{len(prompts)} node prompt(s) are still the shipped example",
                "the prompts are meant to be YOUR process with the approvals removed - "
                "that is the whole claim of a dark factory. Rewrite them from the "
                "interview's Q3.0 answer and delete the header comment",
                prompts[:6])


def check_independence_line(root: Path, rep: Report) -> None:
    """Is anything running that the builder cannot read?

    The rung that makes auto-merge defensible. Everything below the independence line
    sits inside the agent's optimisation loop - it can read those checks, run them, and
    iterate until they are green, which is exactly what you asked for and exactly why
    passing them proves less than it feels like it does.

    Checked separately from "does a harness exist", because a factory with a large,
    careful, entirely READABLE harness looks identical to one with a holdout from every
    angle except this one.
    """
    holdout_dir = root / ".factory" / "holdout"
    has_holdout = holdout_dir.is_dir() and any(
        p.suffix in {".py", ".js", ".ts", ".sh"} for p in holdout_dir.rglob("*")
        if p.is_file())
    mutations = any((root / c).exists() for c in
                    ("harness/mutations", "harness/mutations/run.py", ".factory/mutations"))
    declared, _ = _declared_level(root)

    # TWO DIFFERENT PROPERTIES, and conflating them makes this check wrong in both
    # directions. A TRIPWIRE proves the builder's artifacts did not leak INTO the
    # validator - real, and worth having. HOLDOUT SCENARIOS are assertions written before
    # the work that the builder cannot read. A factory can have the first and none of the
    # second, and a check that calls that "no independence at all" is flagging a correct
    # configuration as a defect, which is how a report gets skimmed.
    # Scoped to where factory machinery actually lives, NOT the whole tree.
    #
    # The first version walked every .md/.yaml/.py in the repo. On a real application
    # that is 10,900 files and the doctor took over two minutes - and a two-minute audit
    # is one people stop running, which costs more than the check is worth. The factory's
    # own definition is never scattered across the application's source.
    iso_re = re.compile(r"tripwire|holdout[-_]clean|FORBIDDEN_ARTIFACTS|fresh[-_ ]context",
                        re.I)
    iso_roots = [root / d for d in ("factory", ".factory", ".archon", ".github", "harness",
                                    "scripts", "workflows")]
    isolation = []
    for base in iso_roots:
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in (
                    AUTOMATION_SUFFIXES | {".md", ".yaml", ".yml"}):
                continue
            if any(s in p.parts for s in SKIP_DIRS) or _is_run_artifact(p, root):
                continue
            if iso_re.search(read(p)):
                isolation.append(rel(p, root))

    if has_holdout:
        rep.add(OK, "independence-line",
                "holdout scenarios exist outside the builder's reach")
    elif isolation:
        rep.add(WARN, "independence-line",
                "the validator is isolated, but no assertion is hidden from the builder",
                "separation of CONTEXT is not separation of EVIDENCE. A tripwire proves "
                "the plan did not reach the validator; it does not stop the builder "
                "reading, running and iterating against every check that decides the "
                "merge. Add scenarios the builder cannot read - see "
                "templates/harness/holdout/",
                isolation[:3])
    elif declared is not None and declared >= 3:
        rep.add(FAIL, "independence-line",
                f"this repo merges unattended at level {declared} with no independence "
                f"mechanism at all",
                "every check in the gate is one the builder can read and iterate against, "
                "and nothing stops its own artifacts reaching the validator. Given enough "
                "attempts an agent satisfies the checks it can see rather than the thing "
                "you meant, so nothing here distinguishes working software from software "
                f"that learned the tests. Write scenarios into {rel(holdout_dir, root)}/ "
                f"before raising the dial this far")
    else:
        rep.add(WARN, "independence-line",
                "no holdout scenarios - nothing runs above the independence line",
                "legitimate while you are proving laps by hand, and indefensible at "
                "level 3. See templates/harness/holdout/")

    if not mutations:
        rep.add(WARN, "independence-line",
                "no mutation set - this gate has never been shown to fail",
                "a gate that has never failed is a gate nobody has tested. Break the "
                "software on purpose and require the gate to notice: "
                "templates/harness/mutations/")


def check_trigger_armed(root: Path, rep: Report) -> None:
    """Is anything actually going to wake this repository up?

    The gap this closes: a factory can be completely built, audit clean, declare itself at
    level 3 - and have nothing scheduled anywhere, so it never runs. Built and armed look
    identical from inside the repository, and "the factory has been quiet" reads the same
    whether it had no work or no heartbeat.

    Note the model this is checking. **Nothing pushes.** Filing an issue does not trigger
    a run; a scheduler polls and dispatches at most one thing per tick. So the question is
    never "is the webhook wired up", it is "is the timer running".
    """
    name_hint = f"dark-factory-{root.name}"
    armed, how = False, ""

    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and ("orchestrator.sh" in r.stdout or name_hint in r.stdout):
            armed, how = True, "cron"
    except (OSError, subprocess.SubprocessError):
        pass

    if not armed:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", name_hint],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                armed, how = True, "Windows Task Scheduler"
        except (OSError, subprocess.SubprocessError):
            pass

    declared, _ = _declared_level(root)

    if armed:
        rep.add(OK, "trigger", f"a scheduler is armed ({how})")
    elif declared is not None and declared >= 1:
        rep.add(WARN, "trigger",
                f"this repo declares autonomy level {declared} but nothing is scheduled",
                "the dial says it should be running unattended and no timer will ever "
                "wake it. Filing an issue does not trigger a run - the dispatcher polls. "
                "Run `bash factory/install-trigger.sh --install`, or drop the declared "
                "level back to 0 so the file matches reality")
    else:
        rep.add(INFO, "trigger",
                "no scheduler armed - correct while the dial is at 0",
                "arm it with `bash factory/install-trigger.sh --install` once a lap has "
                "been proven by hand. It is the last thing you build")


def check_stop_button(root: Path, rep: Report) -> None:
    kill_re = re.compile(r"(factory-stop|\.stop\b|KILL_FILE|STOP_FILE|--paused)", re.I)
    hits = [rel(p, root) for p in walk(root, AUTOMATION_SUFFIXES) if kill_re.search(read(p))]
    if hits:
        rep.add(OK, "stop-button", f"a stop mechanism is referenced in {len(hits)} file(s)")
    else:
        rep.add(WARN, "stop-button",
                "no stop button found",
                "an unattended system needs an obvious off switch, and it should be "
                "used once on purpose before going unattended")


def check_scope_leash(root: Path, rep: Report) -> None:
    """Is anything stopping an editing node from widening its own diff?

    Two shapes count, and the second was missing here for a while - which meant the
    doctor warned about a property the runner actually had, in its own template. A
    check that reports the correct configuration as a defect trains people to skim it.
    """
    leash_re = re.compile(r"git\s+diff\s+--name-only", re.I)
    cap_re = re.compile(r"FILE_CAP|FACTORY_FILE_CAP|SCOPE_VIOLATION", re.I)

    by_diff = [rel(p, root) for p in walk(root, AUTOMATION_SUFFIXES) if leash_re.search(read(p))]
    by_cap = [rel(p, root) for p in walk(root, AUTOMATION_SUFFIXES) if cap_re.search(read(p))]

    if by_cap:
        rep.add(OK, "scope-leash",
                "editing scope is capped in code (file-count cap)",
                evidence=sorted(set(by_cap))[:2])
    elif by_diff:
        rep.add(OK, "scope-leash", "editing scope is derived from the diff somewhere")
    else:
        rep.add(WARN, "scope-leash",
                "nothing caps how many files an editing node may touch",
                "a refactor node with no scope grows a six-file PR into eleven and "
                "introduces a bug in one of the five nobody asked it to touch - while "
                "staying under any line cap the whole way. Set FACTORY_FILE_CAP, or "
                "leash each editing node to `git diff --name-only <base>...HEAD`")


def _declared_level(root: Path) -> tuple[int | None, str]:
    """The level the repo SAYS it runs at, and where that was read from.

    Capability and setting are different questions and only one of them is about what
    is happening right now. A repo can hold every mechanism for level 3 and dispatch
    nothing because its dial is at 0 - which is exactly the state a careful person is
    in the week before they turn it on, and reporting them as "level 3" tells them
    their own repo is doing something it is not.

    Read, in order of authority: the FACTORY.md field the template defines, then the
    dispatcher's own default for its autonomy variable, then a prose claim.
    """
    fac = root / "FACTORY.md"
    if fac.is_file():
        m = re.search(r"current\s+autonomy\s+level\s*:?\s*\**\s*(\d)", read(fac), re.I)
        if m:
            return int(m.group(1)), "FACTORY.md"

    for p in walk(root, AUTOMATION_SUFFIXES):
        m = re.search(r"(?:FACTORY_)?AUTONOMY[\"']?\s*[:=]?\s*[\"']?\$\{"
                      r"[A-Z_]*AUTONOMY:-(\d)\}", read(p))
        if m:
            return int(m.group(1)), rel(p, root)

    for name in ("FACTORY.md", "README.md", "FACTORY_RULES.md"):
        p = root / name
        if p.is_file():
            m = re.search(r"\b(?:runs\s+at|running\s+at|currently\s+at)\s+\**level\**\s*(\d)",
                          read(p), re.I)
            if m:
                return int(m.group(1)), name
    return None, ""


def assess_level(root: Path, rep: Report) -> None:
    """An honest read of what is automated here, and of what is switched on."""
    blob = "\n".join(read(p) for p in walk(root, AUTOMATION_SUFFIXES))
    has_workflows = bool(re.search(r"implement|fix-issue|plan", blob, re.I))
    has_validator = bool(re.search(r"valid|verdict", blob, re.I))
    has_merge = bool(re.search(r"gh\s+pr\s+merge", blob, re.I))
    has_cron = bool(re.search(r"schedule:|cron|\*/\d+\s+\*", blob))
    has_triage = bool(re.search(r"triage", blob, re.I))
    has_selftest = bool(re.search(r"comprehensive|scheduled[-_]test|weekly", blob, re.I))

    capable = 0
    if has_workflows:
        capable = 1
    if has_workflows and has_validator:
        capable = 2
    if capable >= 2 and has_merge and has_cron:
        capable = 3
    if capable >= 3 and has_triage and has_selftest:
        capable = 4

    declared, source = _declared_level(root)

    if declared is None:
        rep.add(WARN, "autonomy-level",
                f"the repo does not state what level it runs at (it is BUILT for {capable})",
                "put `Current autonomy level: N` in FACTORY.md and change it in the same "
                "commit that changes the level. A stale or absent level is a lie about "
                "what is running unattended")
        running = capable
    else:
        running = declared
        note = ("built for more than it runs - that is the correct direction"
                if declared < capable else
                "declared HIGHER than the mechanisms found, which is the dangerous "
                "direction: check the dial against what is actually wired up"
                if declared > capable else "declared level matches the mechanisms found")
        rep.add(INFO, "autonomy-level",
                f"declared level {declared} (from {source}); built for level {capable} - {note}")

    rep.add(INFO, "autonomy-level",
            f"mechanisms present for level {capable}",
            "raise the dial one notch at a time, and watch a full cycle at each",
            [f"workflows={has_workflows}", f"validator={has_validator}",
             f"code-merge={has_merge}", f"trigger={has_cron}",
             f"triage={has_triage}", f"self-test={has_selftest}"])

    # Gate on what is RUNNING, not on what is installed. A repo dialled to 0 with an
    # open FAIL is a repo doing its homework, and failing it teaches people to ignore
    # the doctor at exactly the moment it is being most useful.
    if running >= 3 and rep.failed:
        rep.add(FAIL, "autonomy-level",
                f"this repo merges code unattended at level {running} AND has failing "
                f"checks above",
                "drop to level 2 (no auto-merge) until every FAIL is resolved")


# --------------------------------------------------------------------------- output

def _sep() -> str:
    """A separator the console can actually print.

    This tool printed `0 FAIL ? 0 WARN ? 11 OK` on Windows, because the middle dot is not
    in the ANSI codepage the console defaults to. `references/setup.md` documents that
    exact failure and prescribes the fix, so the skill's own auditor was falling into the
    trap its own reference warns about - which is funny once and corrosive after that,
    because a tool that cannot render its own output invites you to distrust its content.
    """
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "·".encode(enc)
        return "·"
    except (UnicodeEncodeError, LookupError):
        return "|"


def render(rep: Report, repo: Path) -> str:
    order = sorted(rep.findings, key=lambda f: (_ORDER[f.level], f.check))
    out = [f"factory_doctor  {repo}", "=" * 72, ""]
    counts = {lv: sum(1 for f in rep.findings if f.level == lv) for lv in (FAIL, WARN, OK, INFO)}
    sep = _sep()
    out.append(f"{counts[FAIL]} FAIL {sep} {counts[WARN]} WARN {sep} "
               f"{counts[OK]} OK {sep} {counts[INFO]} INFO")
    out.append("")
    for f in order:
        out.append(f"[{f.level:4}] {f.check}: {f.message}")
        if f.fix:
            out.append(f"        fix: {f.fix}")
        for e in f.evidence:
            out.append(f"          - {e}")
        out.append("")
    if counts[FAIL]:
        out.append("Not ready to run unattended. Resolve every FAIL first.")
    elif counts[WARN]:
        out.append("No blocking failures. Read the warnings before raising the dial.")
    else:
        out.append("Clean.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit a dark factory repository.")
    ap.add_argument("--repo", default=".", help="path to the repository (default: cwd)")
    ap.add_argument("--audit", action="store_true",
                    help="full run including the slower whole-tree scans")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # Say the encoding out loud rather than inheriting the console's. Anything that
    # crosses a process boundary needs this stated; a report is no exception.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2

    rep = Report()
    gov = check_governance(repo, rep)
    check_out_of_scope(repo, gov, rep)
    check_prd_provenance(repo, gov, rep)
    check_protected(repo, gov, rep)
    check_ignored_secrets(repo, rep)
    check_empty_is_not_pass(repo, rep)
    check_gate_is_code(repo, rep)
    check_holdout(repo, rep)
    check_deploy_trigger(repo, rep)
    check_validate_command(repo, rep)
    check_prompt_placeholders(repo, rep)
    check_browser_available(repo, rep)
    check_scaffold_edited(repo, rep)
    check_independence_line(repo, rep)
    check_trigger_armed(repo, rep)
    check_stop_button(repo, rep)
    if args.audit:
        check_scope_leash(repo, rep)
    assess_level(repo, rep)

    if args.json:
        print(json.dumps({"repo": str(repo),
                          "findings": [f.__dict__ for f in rep.findings]}, indent=2))
    else:
        print(render(rep, repo))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
