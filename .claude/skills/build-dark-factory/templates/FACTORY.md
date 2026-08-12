# The factory

<!--
  Maintainer: whoever raises the autonomy dial. Update the level and the date on the
  same commit that changes the level - a stale level here is a lie about what is
  running unattended.
-->

**Current autonomy level: <N>** - <one line: what is automatic at this level>
**Raised to this level on:** <YYYY-MM-DD>
**Stop button:** <the exact mechanism, e.g. `touch .factory-stop` in the repo root>
**Built from PRD:** <path or URL> - `MISSION.md` is its compression. Change one, change both.

## The process this encodes

<The AI coding workflow this factory automates, as the ordered steps it already ran by
hand: e.g. plan from the issue -> implement -> validate -> open PR. Name the skills,
rules files and MCP servers loaded at each step. The factory is this process without
the approvals, and writing it down here is what makes that legible to the next person.>

## The five components, as built here

| # | Component | This repo's version |
|---|-----------|---------------------|
| 1 | Workflow-driven repo | <agent> via <orchestrator> |
| 2 | The trigger | <cron expression> reading <shared state> |
| 3 | Deployment | <strategy>, <push-triggered or polling> |
| 4 | Guidance layer | `MISSION.md` · `FACTORY_RULES.md` · `<conventions file>` |
| 5 | Validation harness | <the E2E driver>, holdout at <location> |

## The gates that are actually code

Everything else is a prompt instruction, which is a suggestion with good manners.
These are the ones a model cannot argue past:

1. `factory/gate.sh` - asserts every marker in `FACTORY_REQUIRED_MARKERS`, checks the
   counts, and refuses the merge when the raw output and the verdict disagree.
2. `factory/guard.py` - the protected list and the scope caps. Fails **closed**.
3. <the third one, if you have it>

## The end-to-end path

The single user journey that gates every merge:

1. <start>
2. <action>
3. <observable result>

Required step count: **<N>** (`E2E_PASSED steps=<N>`).

**Last deliberately broken and confirmed failing:** <YYYY-MM-DD>
An end-to-end check that has never failed is not known to work. Break it on purpose
on a schedule and record the date here.

## The autonomy ladder, and where we stop

| Level | Automatic | Reached |
|---|---|---|
| 1 | labelled issue → PR opens | <date or blank> |
| 2 | validator runs and posts a verdict | <date or blank> |
| 3 | validator auto-merges on green structural gates | <date or blank> |
| 4 | self-triage, and a scheduled test files its own bugs | <date or blank> |
| 5 | writes its own issues from the mission | <date or blank> |

**Before the next notch, these must be true:**

- [ ] <the specific thing>
- [ ] <the specific thing>

## Operating notes

- **Cost.** <what one completed run actually costs, measured not projected>.
  Instrumented on <date>.
- **Model routing.** Planning slot: <model>. Implementation slot: <model>.
- **What reaches a human.** Only `factory:needs-human`. <how it is delivered>
- **Known gotchas for this repo.** <e.g. the deploy polls rather than using a push
  trigger, because commits made with the default GitHub token do not fire workflows>

## Incident log

Append only. Every entry is a rule that now exists because of it.

| Date | What happened | What changed as a result |
|---|---|---|
| <YYYY-MM-DD> | <what broke> | <the rule or gate added> |
