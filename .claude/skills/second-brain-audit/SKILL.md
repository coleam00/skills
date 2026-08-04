---
name: second-brain-audit
description: Audit any second brain, notes folder, or agent memory for facts that have quietly stopped being true, then fix the worst one so it stops recurring. Works on a wiki, a single notes file, daily notes, or a non-markdown tool, and adapts the fix to whichever it finds. Checks every current-sounding claim in whatever the agent loads each session against the freshest evidence, and separates contradicted claims from unsupported ones. Use when an assistant gives an outdated answer, when notes or memory files may be stale, when a vault needs checking for contradictions, or when someone asks how to stop a second brain from rotting, mentions memory rot, or asks about state versus event.
---

# Second Brain Audit

Notes rot in a specific way. Nothing is corrupted and nothing goes missing: a fact
simply stops being true, the note keeps saying it, and nothing raises a hand.

The cause is almost always the same. **The write path can only append.** New
information arrives and becomes a new line under the old line, which is correct for
some facts and ruinous for others.

## The one idea

Every stored fact is one of two kinds.

| | Meaning | Correct update |
|---|---|---|
| **State** | one current value, and it **changes** | **replace** it |
| **Event** | a timestamped thing that **happened** | **append** it |

A price, a status, an owner, a deadline: state. A payment, a signature, a decision,
a lesson learned: event.

The update rules are **opposites**. Replacing an event destroys history. Appending a
state creates two answers to one question with nothing marking which is current, and
the stale copy usually sits higher in the file, so it gets read first.

**Structure carries this rule, not an instruction.** Asking a model, or a person, to
remember to update the old entry fails quietly and constantly. Give the page two
sections and the rule follows from where a fact lands.

## Phase 1: establish the shape

**Do not assume a wiki, a vault, or pages.** Most people have none of those. Look at
what actually exists before anything else, because it changes both what the audit can
see and what the fix should be.

| Shape | Looks like | Where state should live |
|---|---|---|
| **Page per subject** | `clients/acme.md`, `projects/x.md` | two sections on each page |
| **One big file** | a single `notes.md` or `CLAUDE.md` | a `## Current State` block at the top |
| **Daily notes only** | `2026-06-01.md`, and nothing else | **nothing to convert.** A state layer is missing entirely |
| **Not markdown** | Notion, Apple Notes, a chat assistant's memory | the idea still applies; the tooling does not |

Then establish two things:

1. **Where the notes live.** A folder of markdown, for the scan.
2. **What the agent reads on every session.** `CLAUDE.md`, a `MEMORY.md`, a system
   prompt file, whatever loads automatically. This matters more than anything else:
   a stale fact in an archive is harmless, the same fact in the always-loaded file is
   the bug. If the user does not know, say so and run without it.

Daily-notes-only is the case most worth naming out loud. Dated notes are an **event
log**, and events are supposed to accumulate; nothing about them is broken. What is
missing is any place that says what is true *now*. Telling someone to restructure
their journal would be actively wrong.

## Phase 2: audit the always-loaded surface

**This is the part that works on every second brain**, in any tool, in any domain,
with or without the script. Run it always, even when the scan found plenty.

Whatever the agent reads on every session is small: that is what makes it always
loadable. So it can be read in full and checked claim by claim.

1. **Read that surface completely.** The always-loaded file, or the top of the one
   big file, or the pinned page. All of it.
2. **Extract every state-shaped claim.** Anything phrased as a current fact: a
   status, an owner, a rate, a version, a deadline, a "currently", a "we use", a
   "lives at". Ignore anything phrased as an event, since events stay true.
3. **For each claim, go and find the freshest evidence anywhere in the notes.**
   Grep the subject. Read the newest file that mentions it.
4. **Sort each claim into three piles:**
   - **Confirmed.** The detail agrees.
   - **Contradicted.** Something newer disagrees. This is rot, and it is the
     headline.
   - **Unsupported.** Nothing anywhere backs it up. Often the claim was true once
     and the evidence was never written, which is worth saying out loud.

Ten to thirty claims is normal, and it is a few minutes of reading. A research vault
with no money in it, a personal wiki, a Notion workspace: all auditable this way, and
none of them by the script.

Report the contradicted pile first, then the unsupported pile. Both are findings.

## Phase 3: run the scan, if the notes suit it

An accelerator, not the audit. It applies to markdown folders where facts carry
monetary values, and it finds cross-file disagreements far faster than reading can.
Skip it otherwise; phase 2 already did the work.

```bash
python <skill>/scripts/audit.py <notes-dir> \
    --always-loaded MEMORY.md --always-loaded CLAUDE.md
```

Pass `--subject "Acme Corp"` to track named subjects by name, and `--json` for
structured output. The script only reads; it never writes.

**A zero is not a clean bill of health.** Values are the only thing it can compare
without guessing, so notes with no money in them are largely invisible to it. It
prints a COVERAGE WARNING when it knows it was blind. Read that warning out rather
than reporting "no problems found".

**Why a script at all:** the count has to be the same twice. A model asked to tally
600 bullets returns a confident number and a different one tomorrow, which is the
class of failure this skill exists to fix. The script counts. The agent judges.

## Phase 4: read what neither can see

Open a few flagged pages and look for what no regex will catch:

- **Lifecycle conflicts.** A page saying "launching next week" while a log entry from
  three months ago records the project being cancelled. No number disagrees, so
  nothing is flagged, and it is completely wrong.
- **Facts never written down at all.** The most common cause of a wrong answer is not
  bad organization; it is that the true value only ever existed in a conversation or
  a daily note. Reorganizing cannot reach it. Say so plainly rather than implying the
  restructure will help.
- **Pages that must not be touched.** Checklists, reference lists, packing lists.
  They are lists on purpose. Converting one destroys what makes it useful, and every
  structural check still passes.

## Phase 5: report

Lead with the single most damaging finding, not a summary of the tool's output:

> Three different answers for what Acme pays, and the oldest one is in the file the
> agent reads every session.

Where an agent already runs over these notes, **demonstrate it**. Ask the question the
notes should answer and read the reply out. Watching an assistant confidently return
a number that stopped being true in March lands harder than any report. Point out the
common case where it is *diligent and still wrong*: it checks a page, warns that
another file looks stale, and still misses the true value because that value was
never promoted anywhere durable.

## Phase 6: fix one place

Never bulk-convert, and never convert a page the user did not agree to. Fix the
single worst *location*, which depends on the shape found in phase 1:

- **Page per subject** → give that one page the two sections below.
- **One big file** → add a `## Current State` block at the top and leave everything
  else beneath it. No new files, no folder structure.
- **Daily notes only** → create **one** file holding current values, and leave every
  journal entry untouched. The journal was already correct.
- **Not markdown** → do not restructure anything. Explain where the current value
  should live in the tool they already use, and stop there.

The shape below is the page-per-subject version; adapt the same two ideas to the
others. What has to be true in every case is only this: **one place says what is true
now, and it gets replaced rather than added to.**

```markdown
## Current State
<!-- One entry per subject. Dated. REPLACED on update, never appended to. -->

- **Retainer** (2026-08-01): $3,200/mo, renewed through February 2027
- **Main contact** (2026-05-02): Curtis Ilo

## Log
<!-- Append-only. Never edit or delete an entry. -->

- (2026-04-30) Delivered and paid, $21,000
- (2026-05-02) Retainer started at $2,800/mo
- (2026-06-15) Added reply drafting, retainer to $3,200/mo
```

Conversion rules, in order of importance:

1. **Lose nothing.** Every existing line lands in one of the two sections, verbatim.
   This is sorting, not rewriting. Improving the prose is how information disappears
   without anyone noticing.
2. **One entry per subject in Current State.** Where two lines describe the same
   current value, the newer wins and the older moves to the Log. Where the order is
   unclear, ask. Never guess.
3. **Date every Current State entry.** Ask for a missing date or take it from file
   history. An undated current value is barely better than a stale one.
4. **Never merge two subjects that merely look similar.** "Acme (May)" and "Acme Corp
   renewal" may be genuinely different things. A duplicate entry is a cheap mistake;
   a wrong merge destroys information. Report near-misses and let the user decide.
5. **Show a diff and get approval** before writing.

Re-ask the earlier question afterwards so the correct answer is visible. Same notes,
same agent, one page restructured.

## Phase 7: change the write path

This phase decides whether the audit was worth anything. Converting pages fixes
today; changing how facts get written is what stops the recurrence.

Add to whatever file instructs the agent (`CLAUDE.md`, `AGENTS.md`, a system prompt):

```markdown
## Writing to these notes

Every fact is state or event.

- **State** (one current value that changes: price, status, owner, date):
  find the matching line in `## Current State` and REPLACE it. Always date it.
  Never add a second line for the same subject.
- **Event** (a thing that happened): append to `## Log`. Never edit or delete
  an existing Log entry.

If unsure, append to the Log and say so. A missing state update is recoverable;
a rewritten history is not.
```

Then state the honest part: this instruction gets followed most of the time, not all
of the time. Anything that must happen every time needs a mechanism. Two cheap ones
worth more than the instruction:

- Re-run this audit on a schedule and watch whether the count climbs.
- Stamp dates with a script after the fact instead of asking for them.

## Set expectations honestly

Restructuring alone often moves the number less than people expect. When it does not
move, the reason is usually that the correct fact was never captured, and no amount
of reorganizing reaches a fact nobody wrote down. Say that when it applies. The
audit's real value is identifying *which* of the two problems is in play.

## Resources

- `scripts/audit.py`: run it for the deterministic scan; `--help` lists all flags,
  `--json` returns structured findings. Never read it into context; only its output.
