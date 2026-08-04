#!/usr/bin/env python3
"""Find stale and contradictory facts in a folder of markdown notes.

The counting lives here, in code, rather than in the skill's prompt. That is the
whole point of the technique this audits: if something has to be right every time,
an instruction is the wrong mechanism for it. A model asked to count 600 bullets
will produce a confident wrong number, and a different one tomorrow.

Nothing here is written. This script only reads and reports.

    python audit.py <notes-dir>
    python audit.py <notes-dir> --always-loaded MEMORY.md --always-loaded CLAUDE.md
    python audit.py <notes-dir> --subject "Acme Corp"
    python audit.py <notes-dir> --json

WHAT COUNTS AS A CONTRADICTION
------------------------------
Only a disagreement that spans **more than one file**. A single page listing
"$2,800 in May, $3,200 in June" is history, and history is supposed to look like
that. The failure worth finding is the same subject answered differently in two
places, with nothing saying which one is current.

Values are also only compared **like with like**: a one-time fee and a monthly
rate are different facts about the same client, not two versions of one fact.
Both rules exist because a checker that cries wolf trains you to ignore it.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MONEY = re.compile(r"\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?\s*k?(?:\s*/\s*(?:mo|month|yr|year|hr|hour))?",
                   re.I)
RECURRING = re.compile(r"/\s*(?:mo|month|yr|year|hr|hour)", re.I)


def money_value(raw: str) -> tuple[float, bool] | None:
    """Canonical (amount, is_recurring). '$22k' and '$22,000' are one value.

    Without this the audit reports a contradiction between two spellings of the
    same number, which is the fastest way to teach someone to ignore it.
    """
    m = re.match(r"\$\s?([\d,]*\d)(\.\d+)?\s*(k?)", raw, re.I)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "") + (m.group(2) or ""))
    if m.group(3).lower() == "k":
        amount *= 1000
    return amount, bool(RECURRING.search(raw))


def fmt_money(amount: float, recurring: bool) -> str:
    s = f"${amount:,.0f}" if amount == int(amount) else f"${amount:,.2f}"
    return s + ("/mo" if recurring else "")
STATUS = re.compile(
    r"\b(active|paused|cancell?ed|churned|shipped|launched|live|signed|closed|"
    r"won|lost|on hold|in progress|completed?|delivered|paid|pending|blocked)\b", re.I)
CONFLICTING_STATUS = {"active", "paused", "cancelled", "canceled", "churned",
                      "completed", "complete", "closed", "lost", "on hold", "live"}

FINISHED = re.compile(r"\b(done|shipped|paid|complete[d]?|delivered|signed|"
                      r"cancell?ed|closed|launched)\b", re.I)
OPEN_HEADING = re.compile(r"^#{1,4}\s+.*\b(active|open|current|todo|to do|in progress|"
                          r"now|doing|pending|backlog)\b", re.I)

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
                  r"Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b")
LOG_HEADING = re.compile(r"^##+\s+(Log|History|Timeline|Archive)\b", re.I)
DATE_NAMED = re.compile(r"^\d{4}[-_]\d{2}([-_]\d{2})?$")

KEY = re.compile(r"^-\s*(?:\(?[^)]{0,24}\)?\s*)?\*\*(.+?)\*\*")
BULLET = re.compile(r"^\s*-\s+\S")
FENCE = re.compile(r"^\s*```")
SCHEMA_STATE = re.compile(r"^##\s+Current State\b", re.M | re.I)
SCHEMA_LOG = re.compile(r"^##\s+Log\b", re.M | re.I)

# Pages that are indexes or config, not per-subject pages.
NOT_A_SUBJECT = {"index", "readme", "memory", "claude", "soul", "user", "schema",
                 "heartbeat", "repositories", "core-memories", "todo", "inbox"}


def norm(s: str) -> str:
    s = MONEY.sub(" ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def page_subject(stem: str) -> str | None:
    """A per-subject page lends its name to every value on it.

    Without this, a line like "- Retainer is **$6,000/mo** as of March" is
    unattributable: the bolded key is the value itself and the client is never
    named, because the filename already says it.
    """
    s = stem.lower()
    # Notion and similar exporters append a 32-char hex id to every filename.
    # Left in place it makes the subject "acme corp 1a2b3c..." which matches
    # nothing in the prose, so the whole vault becomes unattributable.
    s = re.sub(r"[\s_-]+[0-9a-f]{8,32}$", "", s)
    if DATE_NAMED.match(s) or s in NOT_A_SUBJECT or len(s) < 3:
        return None
    return norm(s.replace("-", " ").replace("_", " "))


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_lines(text: str):
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield i, line


def scan(root: Path, extra: list[str]):
    files = sorted(p for p in root.rglob("*.md") if ".git" not in p.parts)

    # Pass 1: the subject vocabulary, taken from the names of per-subject pages.
    vocab: dict[str, str] = {}
    for p in files:
        subj = page_subject(p.stem)
        if subj and len(subj) >= 4:
            vocab[subj] = p.stem
    for t in extra:
        vocab[norm(t)] = t

    subjects: dict[str, list] = defaultdict(list)
    money_seen = 0
    journal_files = 0
    bullets = dated = 0
    durable_bullets = durable_dated = 0
    finished_open: list[tuple[str, int, str]] = []
    schema_pages: list[str] = []
    words = 0

    for p in files:
        text = read(p)
        words += len(text.split())
        rel = str(p.relative_to(root)).replace("\\", "/")
        own = page_subject(p.stem)
        # A daily/journal file carries its date in its name; its bullets do not
        # each need one, so they are excluded from the dating metric.
        is_journal = bool(DATE_NAMED.match(p.stem.lower()))
        journal_files += is_journal
        if SCHEMA_STATE.search(text) and SCHEMA_LOG.search(text):
            schema_pages.append(rel)

        # A page that dates nearly every bullet is a chronological record. Its
        # values are history laid out in order, not rival claims about now, so
        # it is read for dating stats but never used as a current answer.
        page_bullets = [l for _, l in iter_lines(text) if BULLET.match(l)]
        n_dated = sum(1 for l in page_bullets if DATE.search(l))
        is_chronological = len(page_bullets) >= 5 and n_dated / len(page_bullets) >= 0.7

        under_open = under_log = False
        for lineno, line in iter_lines(text):
            if line.startswith("#"):
                under_open = bool(OPEN_HEADING.match(line))
                under_log = bool(LOG_HEADING.match(line))
                continue
            if not BULLET.match(line):
                continue
            bullets += 1
            has_date = bool(DATE.search(line))
            dated += has_date
            if not is_journal:
                durable_bullets += 1
                durable_dated += has_date
            if under_open and FINISHED.search(line):
                finished_open.append((rel, lineno, line.strip()[:110]))

            # A `## Log` section is history by declaration. Respecting that is
            # what makes a page stop being flagged once it has been fixed.
            if under_log or is_chronological:
                continue

            money = MONEY.findall(line)
            money_seen += len(money)
            status = [s.lower() for s in STATUS.findall(line)]
            if not (money or status):
                continue

            keys = set()
            m = KEY.match(line.strip())
            if m:
                k = norm(m.group(1))
                if len(k) >= 4:
                    keys.add(k)
            if own:
                keys.add(own)
            low = " " + norm(line) + " "
            for v in vocab:
                if f" {v} " in low:
                    keys.add(v)

            for k in keys:
                subjects[k].append(
                    {"file": rel, "line": lineno, "money": money, "status": status,
                     "text": line.strip()[:108]})

    return (files, subjects, bullets, dated, durable_bullets, durable_dated,
            finished_open, schema_pages, words, vocab, money_seen, journal_files)


def contradictions(subjects: dict, min_files: int = 2) -> list[dict]:
    """min_files is normally 2: a disagreement inside one page is usually history.

    A vault that IS one or two files has no cross-file option, so that rule would
    silently make it unauditable. There, one file is enough.
    """
    out = []
    for subj, hits in subjects.items():
        seen = set()
        uniq = []
        for h in hits:
            k = (h["file"], h["line"])
            if k not in seen:
                seen.add(k)
                uniq.append(h)
        if len(uniq) < 2:
            continue

        # Compare like with like: recurring rates and one-time amounts are
        # different facts, not two versions of the same one.
        for bucket in (True, False):          # recurring rates, then one-time sums
            vals: dict[str, list] = {}
            for h in uniq:
                for v in h["money"]:
                    mv = money_value(v)
                    if mv is None or mv[1] != bucket:
                        continue
                    vals.setdefault(fmt_money(*mv), []).append(h)
            files = {h["file"] for g in vals.values() for h in g}
            if len(vals) >= 2 and len(files) >= min_files:
                out.append({"subject": subj,
                            "kind": "recurring" if bucket else "onetime",
                            "values": sorted(vals),
                            "hits": [h for g in vals.values() for h in g]})
                break
        # Status words are deliberately NOT used to claim a contradiction.
        # Tried it; "migration COMPLETE" and "20 active deals" on one topic page
        # read as a conflict to a regex and as obviously unrelated to a human.
        # Lifecycle conflicts ("page says launching, log says cancelled") need
        # judgment, so the skill hands that to the model instead. This script
        # only reports what it can count without being wrong.
    out.sort(key=lambda c: (-len({h["file"] for h in c["hits"]}), -len(c["hits"])))
    return out


def near_misses(subjects: dict, vocab: dict) -> list[tuple[str, str]]:
    """Keys that may be the same subject. REPORTED, never merged: a duplicate
    key is a cheap mistake, a wrong merge destroys information.

    Restricted to subjects that own a page. Arbitrary bolded leads produce pairs
    like '10 active drafts' ~ '17 active drafts', which is noise."""
    keys = sorted(k for k in subjects if len(subjects[k]) > 1 and k in vocab)
    pairs = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if abs(len(a) - len(b)) > 12:
                continue
            if 0.86 <= difflib.SequenceMatcher(None, a, b).ratio() < 1.0:
                pairs.append((a, b))
    return pairs[:10]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("notes", type=Path)
    ap.add_argument("--always-loaded", action="append", default=[], metavar="PATH",
                    help="a file your agent reads every session (repeatable)")
    ap.add_argument("--subject", action="append", default=[], metavar="TERM")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = a.notes.expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 2

    (files, subjects, bullets, dated, dur_b, dur_d,
     fin_open, schema, words, vocab, money_seen, journals) = scan(root, a.subject)
    conts = contradictions(subjects, min_files=1 if len(files) <= 2 else 2)
    always = [s.replace("\\", "/").lower() for s in a.always_loaded]

    def in_always(h):
        return any(h["file"].lower().endswith(al) for al in always)

    hot = [c for c in conts if any(in_always(h) for h in c["hits"])]
    pct = round(100 * dur_d / dur_b) if dur_b else 0

    if a.json:
        print(json.dumps({
            "files": len(files), "words": words, "durable_bullets": dur_b,
            "dated_pct": pct, "contradicted_subjects": len(conts),
            "contradictions_in_always_loaded": len(hot),
            "finished_but_open": len(fin_open), "schema_pages": len(schema),
            "detail": [{k: c[k] for k in ("subject", "kind", "values")} | {
                "files": sorted({h["file"] for h in c["hits"]})} for c in conts[:25]],
        }, indent=1))
        return 0

    W = 76
    print("=" * W)
    print(f"SECOND BRAIN AUDIT  ·  {root}")
    print("=" * W)
    print(f"  {len(files):,} files · {words:,} words · {dur_b:,} bullets on durable pages")
    if schema:
        print(f"  {len(schema)} page(s) already use Current State / Log")

    print(f"\n{'-' * W}\n1. ONE SUBJECT, TWO PLACES, DIFFERENT ANSWERS\n{'-' * W}")
    if not conts:
        print("  None found.")
    for c in conts[:6]:
        star = "  ***" if any(in_always(h) for h in c["hits"]) else ""
        print(f"\n  {c['subject']}  ->  {len(c['values'])} answers: "
              f"{', '.join(c['values'][:6])}{star}")
        for h in sorted(c["hits"], key=lambda x: x["file"])[:5]:
            flag = "   <-- ALWAYS LOADED" if in_always(h) else ""
            print(f"      {h['file']}:{h['line']}{flag}")
            print(f"        {h['text']}")
    if len(conts) > 6:
        print(f"\n  ... and {len(conts) - 6} more.")

    print(f"\n{'-' * W}\n2. CAN YOU RESOLVE A CONFLICT BY DATE?\n{'-' * W}")
    print(f"  {dur_d:,} of {dur_b:,} bullets on durable pages carry a date  ({pct}%)")
    if pct < 60:
        print("  Under ~60%, \"just use the newest one\" is not available to you or")
        print("  to your agent, because most entries never say when they were written.")

    print(f"\n{'-' * W}\n3. FINISHED, BUT STILL IN AN OPEN LIST\n{'-' * W}")
    if not fin_open:
        print("  None found.")
    for f, ln, txt in fin_open[:6]:
        print(f"  {f}:{ln}\n    {txt}")
    if len(fin_open) > 6:
        print(f"  ... and {len(fin_open) - 6} more.")

    nm = near_misses(subjects, vocab)
    if nm:
        print(f"\n{'-' * W}\n4. POSSIBLY THE SAME SUBJECT  (reported, never merged)\n{'-' * W}")
        for x, y in nm:
            print(f"  {x!r}  ~  {y!r}")

    print(f"\n{'=' * W}\nVERDICT\n{'=' * W}")
    print(f"  {len(conts)} subject(s) answered differently in more than one file.")
    if always:
        print(f"  {len(hot)} of those touch a file your agent loads every session. ***")
    else:
        print("  Re-run with --always-loaded <file> to find which of these your")
        print("  agent reads on every session. Those are the ones that bite.")
    print(f"  {len(fin_open)} finished item(s) still sitting in an open list.")
    print(f"  {pct}% of durable bullets are dated.")

    # A zero here means one of two very different things, and saying "clean" when
    # the scan simply could not see is the worst failure this tool has available.
    blind = []
    if not money_seen:
        blind.append("No monetary values anywhere. Values are the only thing this\n"
                     "    scan can compare without guessing, so it has checked almost\n"
                     "    nothing. Name the facts that matter with --subject, and read\n"
                     "    the notes directly.")
    if journals and journals == len(files):
        blind.append("Every file is a dated journal. That is an event log, and events\n"
                     "    are supposed to accumulate. The question is not whether these\n"
                     "    are messy, it is whether any file anywhere holds the CURRENT\n"
                     "    value. If not, the missing piece is a state layer, not a fix.")
    if not vocab:
        blind.append("No per-subject pages found, so values could not be attributed to\n"
                     "    a subject across files. Pass --subject to name them.")
    if blind:
        print(f"\n{'-' * W}\n  COVERAGE WARNING: a low count above may mean 'not visible',\n"
              f"  not 'not present'.\n{'-' * W}")
        for b in blind:
            print(f"  *  {b}")

    print("\n  Nothing was modified. This script only reads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
