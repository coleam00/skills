---
name: build-signal-engine
description: Build a personal signal engine from scratch - a system that reads every source someone cares about each day (changelogs and release notes, communities, feeds, videos, papers), makes a quick decision on every item, lets an LLM read only what survives, and delivers one short digest. Interviews the user first to pin down what they need to keep up with, the sources where it actually shows up, and the one question that decides what is worth their time, then builds it one stage at a time into their own repo, proving each stage on real data. Agnostic about the coding agent, the decision model and where the data comes from. Use when the user wants to keep up with AI or their field without doomscrolling, build an AI news digest, a daily briefing, a content engine, a research or competitor monitor, a changelog watcher, or "something that reads everything and tells me what matters"; and when they mention signal vs noise, an information diet, or falling behind.
argument-hint: "[optional: path/to/repo]"
arguments: [repo]
---

# Build a signal engine

**What the user typed:** $ARGUMENTS

> If a path was given, it is the repo to build in; confirm it in one sentence. If not, ask
> whether to start a new folder or use the current one. Then go straight to Round 1.

A signal engine reads everything so its owner doesn't have to. Every morning it pulls
from the places things actually happen, decides on every single item, hands an LLM only
the few worth reading, and delivers one digest.

**Keeping up is a filtering problem, not a reading problem.** Reading more makes people
feel more behind. The engine encodes the user's own filter and runs it on everything.

**Build it into the user's repo. Do not hand them a plan.** Every stage below ends with
code committed and output from a real run they can look at.

---

## Output discipline

The interview and the build are long. What you say is not.

| Moment | Budget |
|---|---|
| Between questions | Nothing. Ask the next one. |
| Finishing a stage | Two lines: what now exists, with the real number from the run, and the next step. |
| A file you wrote | One line: its path. |
| Command output | Never paste it. The verdict and the number. |

Never announce a plan before doing it, restate an answer as a paragraph, or explain why the
skill works this way unless asked. The reasoning lives in `references/`, for you.

---

## The shape

```
sources -> store (dedupe, stable ids) -> code filters (dates, numbers) -> decide on every item
        -> the LLM reads what survives -> digest -> delivered on a schedule
```

Two splits carry the whole design. Say each once, early, in one sentence:

- **Numbers in code, judgment in the decision pass, reading in the LLM.** Dates, upvotes,
  view counts and "have I seen this" are code. "Is this new, is it for me" is a typed
  decision. Summarising and connecting is the LLM. Mixing them up is the most common bug.
- **The question is the policy.** What the engine keeps is decided by the words of one or
  two questions written from the user's own examples. Changing the question changes the
  engine. There is no model setting that fixes a vague question.

---

## Construction order

| Stage | What exists at the end | Proof before moving on |
|---|---|---|
| 0 | The interview, written down | `PROFILE.md` the user agreed to |
| 1 | One source, end to end into the store | a real run: N items, all with stable ids |
| 2 | Every source | each source's real count, and a re-run that adds ~0 |
| 3 | Code filters | how many each filter dropped |
| 4 | The decision pass | their own keep/drop examples scored, misses listed |
| 5 | The reading pass + digest | a digest from today's real data |
| 6 | Delivery + schedule | it ran once on its own |
| 7 | A week in shadow | the user's marked-up misses, and the question revised |

**One source first, end to end, before adding the rest.** A pipeline built source-wide but
never run end to end fails at the join between stages, and finding that after twelve
sources is twelve times the work.

**Anything that bills per row is capped on every run** and only runs on the daily schedule,
never on a frequent scan.

---

## Stage 0. Interview

Read `references/interview.md` and work through it. Three rounds:

1. **Three questions, one at a time,** that decide the project: what they need to keep up
   with and what they would do differently if they knew on the day; something they missed
   or found out late, and where it first appeared; where the digest gets read and what they
   do with an item.
2. **Questions only they can answer, about things that already happened**: the tools they
   use daily, where people using those tools talk, three items from last week they would
   have wanted and three they never want again, what is too old or too small to matter, and
   whether their sources come through one data platform or get picked per source.
3. **One message of defaults** to confirm: schedule, stack, storage, caps, models,
   digest length, delivery.

**Every question goes through the question tool** (`AskUserQuestion` in Claude Code, or
the equivalent), with two to four options drafted from what they have already said, one
marked `(Recommended)` and first. It always carries free text, so nothing is lost. Never
ask the user to design an artifact; they tell you what happened, you turn it into sources,
filters and questions.

Write `PROFILE.md` from `templates/PROFILE.md`: the focus, the sources, the filters, the
decision question(s) with their keep/drop examples, the digest format and delivery. Read it
back as a proposal and get a yes before Stage 1.

**When to refuse or shrink:**

- **No focus** ("everything in AI"): ask for the action instead. "What would you do
  differently if you knew?" If nothing changes what they do, they need fewer sources, not
  an engine.
- **Two or three sources:** an RSS reader or email alerts beat a build. Say so.
- **A source whose terms forbid automated access** and that has no API or permitted
  provider: leave it out and say why.

---

## Stages 1-3. Sources, store, code filters

Read `references/sources.md`. It is a playbook per source type: what to use for each,
what it returns, and the failure each one is known for.

**Where the data comes from is the user's call (R2.6).** If they chose one data platform,
that is the plan: every source it covers goes through it, with one client, one credential
and a spending cap on every run. Do not argue them back to per-source APIs. If they named
the exact tool for a source, use that tool and never test an alternative against it. If they
asked you to pick, choose per source from `references/sources.md` and say which method each got.

**If the platform has an MCP server, connect it for the build.** Search for and test-run
the right tool for each source through MCP, then have the engine call those same tools on
its schedule through the platform's API. MCP while you build, the API while it runs.

Changelogs and release notes, however they are fetched: split the page into dated entries
and give each a stable id.

Every source maps to one item shape (`templates/item_schema.md`): id, source, title, url,
body, published_at, engagement. Dedupe on the id before anything costs money. Store in
SQLite unless they already run something else.

Code filters run on stored items and drop by fact: age, engagement floor, language, length,
already seen. Report how many each one dropped. Pull smarter before filtering harder: a
filter does not refund a row the provider already billed.

---

## Stage 4. The decision pass

Read `references/decisions.md`. Every item that survived the code filters gets the
question(s) from `PROFILE.md` in one call, all items in parallel. Use a decision model with
typed, probability-scored answers if one is available to the user (TypeSafe's Jev via
OpenRouter is the reference here), otherwise a small, fast LLM with structured output.

Code routes each item:

- **sure drop** (clearly off-topic, clearly nothing new): stored as filtered, never read
- **sure keep**: goes to the reading pass
- **unsure**: goes to the reading pass, where the LLM decides

**Never drop on taste.** "Is this a toy project", "would I like this" and "is it good" are
for ranking and for the LLM, never for a hard drop. They cut real finds.

**Prove it on their examples before trusting it.** Score the keep/drop examples from the
interview, plus a sample of today's real items you label with them. Print what was kept,
what was dropped, and every miss. Tune the words of the question, not the thresholds,
first.

---

## Stage 5. The reading pass and the digest

Read `references/digest.md`. The LLM reads only what the decision pass let through, groups
related items, and writes the digest in the format from `PROFILE.md` with every link kept.
Start from `templates/digest_prompt.md`.

Cap the digest (default ten items). A digest nobody finishes is a feed.

## Stage 6. Delivery and schedule

Deliver where they already read (a markdown file in their notes, email, chat). Schedule the
full run once a day. If they want a weekly roll-up, it reads the week's stored items, not
seven digests.

Ask before registering the schedule (cron, Task Scheduler, launchd). Once it is registered,
every paid source bills every day without anyone watching. Show the one command, and run the
engine once by hand if they would rather register it themselves.

## Stage 7. A week in shadow

For a week the user reads the digest and marks two things: what was missing and what was
noise. Fix misses by adding a source or rewording a question; fix noise with a code filter
or a sharper question. Then it runs on its own.

---

## Operating facts

- Keys live in the repo's gitignored env file and the engine loads them from there. Never
  print that file or a key, not even to check it: check that a key is set by its name. If
  one is missing, ask the user to add it themselves rather than pasting it into the chat.
- Test every run against a throwaway database, never the one that will go live.
- On Windows, force UTF-8 output from the start (`PYTHONIOENCODING=utf-8` or reconfigure
  stdout). Titles from communities carry emoji and non-English text that crash the console.
- Measure the decision pass by running the same rows with and without it: rows the LLM
  read, tokens, wall time, and which rows it would have kept that the pass dropped.
- LLMs vary between runs too. A row that passed once and not the next time is not proof
  the decision pass is wrong.
- Per-row data costs can exceed the whole LLM bill. The decision pass saves on reading,
  not on fetching.

## Resources

- `references/interview.md` - every question, what it becomes, and the vague answers to push on
- `references/sources.md` - per source type: method, item mapping, known failures
- `references/decisions.md` - writing the question, routing, evaluating on their examples
- `references/digest.md` - the reading prompt, format, delivery, scheduling, the weekly roll-up
- `templates/PROFILE.md` - the file the interview produces and every stage reads
- `templates/item_schema.md` - the one item shape every source maps to
- `templates/digest_prompt.md` - the starting reading prompt
