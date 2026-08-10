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
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "target", "vendor", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".idea", ".vscode",
}

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


def walk(root: Path, suffixes: set[str] | None = None):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if _is_skill_payload(p):
            continue
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
    items = re.findall(r"^\s*[-*]\s+\S", section, re.M)
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
    m = re.search(r"^\s*\*{0,2}(derived from|source|prd)\*{0,2}\s*:\s*(.+)$",
                  body, re.I | re.M)
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

    exposed, checked = [], 0
    for name in SECRET_CANDIDATES:
        p = root / name
        if not p.exists():
            continue
        checked += 1
        rc, _ = git(root, "check-ignore", "-q", name)
        if rc != 0:                       # non-zero == not ignored
            exposed.append(name)

    tracked_rc, tracked = git(root, "ls-files", "--", "*.env", ".env*", "*secret*",
                              "*credential*")
    tracked_hits = [ln for ln in tracked.splitlines() if ln.strip()] if tracked_rc == 0 else []

    if exposed:
        rep.add(FAIL, "secrets",
                f"{len(exposed)} config file(s) exist and are NOT git-ignored",
                "a workflow that runs `git add -A` will commit these. On a public "
                "repo that is publication, and rotating afterwards is cleanup, not a fix",
                exposed)
    elif checked:
        rep.add(OK, "secrets", f"{checked} candidate config file(s) all git-ignored")

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

    negatives, positives = [], []
    for p in walk(root, AUTOMATION_SUFFIXES):
        body = read(p)
        for m in negative_re.finditer(body):
            line_no = body[: m.start()].count("\n") + 1
            negatives.append(f"{rel(p, root)}:{line_no}  {m.group(0).strip()}")
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


def check_holdout(root: Path, rep: Report) -> None:
    """The validator must not be handed the builder's reasoning."""
    validator_re = re.compile(r"valid|review|verdict|judge|qa", re.I)
    leak_re = re.compile(
        r"(plan\.md|plan[-_]context|implementation\.md|investigation\.md|design[-_]notes|"
        r"--comments|\.comments|scratch|rationale)", re.I)
    # NOTE on precision, learned auditing a real factory: `validator_re` matches on the
    # FILE NAME, so a builder-side step called "validate" (run the suite, fix failures)
    # is indistinguishable from the independent validator. Read the finding before acting
    # on it. This check narrows where to look; it does not decide.
    base_fetch_re = re.compile(
        r"git\s+show\s+origin/|git\s+fetch\s+origin|--ref\s+origin/|origin/main:", re.I)

    # Markdown is included here and nowhere else. The judge is usually a PROMPT, and
    # prompts are markdown -- `.archon/commands/*.md`, `factory/prompts/judge.md`. With
    # only AUTOMATION_SUFFIXES this check never looked at the single most likely place
    # for a leak, and a judge prompt saying "read the implementation plan before judging"
    # audited clean. The `validator_re` name filter keeps MISSION.md and FACTORY_RULES.md
    # out, which is what stops the documents that *describe* the holdout rule tripping it.
    validators = [p for p in walk(root, AUTOMATION_SUFFIXES | {".md"})
                  if validator_re.search(p.name)]
    leaks, base_ok = [], False

    for p in validators:
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
            leaks.append(f"{rel(p, root)}:{idx + 1}  {line.strip()[:90]}")
        if base_fetch_re.search(body):
            base_ok = True

    if not validators:
        rep.add(WARN, "holdout", "no validator-shaped file found to inspect",
                "expected something named validate/review/verdict")
        return

    if leaks:
        rep.add(FAIL, "holdout",
                "the validator appears to read builder artifacts",
                "a validator that sees the plan is grading the story, not the code. "
                "It gets the issue, the diff, and the output of checks it ran itself",
                leaks[:8])
    else:
        rep.add(OK, "holdout",
                f"no builder-artifact reads found in {len(validators)} validator file(s)")

    if base_ok:
        rep.add(OK, "holdout", "governance appears to be read from the base branch")
    else:
        rep.add(WARN, "holdout",
                "governance does not appear to be fetched from the base branch",
                "fetch MISSION / FACTORY_RULES from origin before checking out the PR, "
                "or a PR can weaken the rulebook it is judged against")


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
    leash_re = re.compile(r"git\s+diff\s+--name-only", re.I)
    hits = [rel(p, root) for p in walk(root, AUTOMATION_SUFFIXES) if leash_re.search(read(p))]
    if hits:
        rep.add(OK, "scope-leash", "editing scope is derived from the diff somewhere")
    else:
        rep.add(WARN, "scope-leash",
                "no node appears to be leashed to `git diff --name-only <base>...HEAD`",
                "an editing node with no file scope will grow the PR and introduce a "
                "bug on the way through")


def assess_level(root: Path, rep: Report) -> None:
    """An honest read of what is actually automated here."""
    blob = "\n".join(read(p) for p in walk(root, AUTOMATION_SUFFIXES))
    has_workflows = bool(re.search(r"implement|fix-issue|plan", blob, re.I))
    has_validator = bool(re.search(r"valid|verdict", blob, re.I))
    has_merge = bool(re.search(r"gh\s+pr\s+merge", blob, re.I))
    has_cron = bool(re.search(r"schedule:|cron|\*/\d+\s+\*", blob))
    has_triage = bool(re.search(r"triage", blob, re.I))
    has_selftest = bool(re.search(r"comprehensive|scheduled[-_]test|weekly", blob, re.I))

    level = 0
    if has_workflows:
        level = 1
    if has_workflows and has_validator:
        level = 2
    if level >= 2 and has_merge and has_cron:
        level = 3
    if level >= 3 and has_triage and has_selftest:
        level = 4

    rep.add(INFO, "autonomy-level",
            f"this repo looks like autonomy level {level}",
            "raise the dial one notch at a time, and watch a full cycle at each",
            [f"workflows={has_workflows}", f"validator={has_validator}",
             f"code-merge={has_merge}", f"trigger={has_cron}",
             f"triage={has_triage}", f"self-test={has_selftest}"])

    if level >= 3 and rep.failed:
        rep.add(FAIL, "autonomy-level",
                "this repo merges code unattended AND has failing checks above",
                "drop to level 2 (no auto-merge) until every FAIL is resolved")


# --------------------------------------------------------------------------- output

def render(rep: Report, repo: Path) -> str:
    order = sorted(rep.findings, key=lambda f: (_ORDER[f.level], f.check))
    out = [f"factory_doctor  {repo}", "=" * 72, ""]
    counts = {lv: sum(1 for f in rep.findings if f.level == lv) for lv in (FAIL, WARN, OK, INFO)}
    out.append(f"{counts[FAIL]} FAIL · {counts[WARN]} WARN · {counts[OK]} OK · {counts[INFO]} INFO")
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
