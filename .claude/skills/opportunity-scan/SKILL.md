---
name: opportunity-scan
description: "Scan how you actually work with your coding agent and surface what to encode next. Point it at ONE run's artifacts to find what would have prevented a specific failure (the reactive loop — 'that went wrong, what should change in the AI layer?'), or at a window of session logs to find recurring patterns worth building (the proactive scan). Agent-agnostic. Outputs a shape-only HTML report. Use to evolve your system from real usage."
---

# Opportunity Scan — find what to change, from what actually happened

Reads your agent's own capabilities plus **one target you choose**, and recommends which primitive each finding
should become. **Agent-agnostic** (Claude Code, Codex, PI, …). It maps what it finds to the **full primitive
palette** (rules · skill · hook · subagent · MCP · automation/workflow), and it works for **any** agent because it
learns that agent's capabilities first.

**Two targets, one skill — this is the whole design:**
- **A run → the REACTIVE loop.** Something just went sideways in a loop you ran. Point the scan at that run's
  artifacts and ask *"what in the AI layer would have prevented this?"* You fix the system, not the code.
- **A window of logs → the PROACTIVE scan.** Nothing is broken. Point it at weeks of sessions and ask *"what do I
  keep doing by hand that should be encoded?"*

Same skill, same output shape — you're just changing what it reads.

This is a **discovery** tool — *what to change* — NOT a quality **eval** (*whether a built thing is good*). Keep
the two separate.

## Inputs — ask for any that weren't given

`$ARGUMENTS` may carry some of these; ask for whatever's missing, don't guess.

1. **Where the agent's own docs live** — a URL or path to your agent's capability / extensibility docs, so the scan
   knows what your agent *can become* (its real extension points). Don't assume Claude Code.
2. **What to scan** — exactly one of:
   - **A RUN (reactive)** — the artifacts one loop left behind: the plan, the implementation report, an RCA, the PR
     body, the review output, the commits/diff. Add that run's session log too if you can point at it. *These are
     already scoped to the run, so there's no session-hunting to do.*
   - **A WINDOW OF LOGS (proactive)** — where your agent keeps session logs, plus how far back. Examples: Claude
     Code → `~/.claude/projects/` + `~/.claude/history.jsonl`; Codex → `~/.codex/sessions/`; PI → your extension's
     log dir. Default window: the last 2 weeks.
3. **What you care about** *(optional — ask once, accept "nothing specific")* — where you want leverage right now,
   in your words: the kind of work you want to stop doing by hand, a quality bar you keep enforcing, a part of the
   loop that keeps costing you. This **steers what the scan pays attention to**; without it the proactive scan just
   ranks by frequency, which is not the same as ranking by what matters to you.

## Steps — keep them literal; this is the fragile part (meta-prompting)

1. **Learn your own capabilities.** Read the agent docs from input 1. Write a short internal list of *this* agent's
   extension points (rules, skill, hook, subagent, MCP/tool, automation/workflow, whatever the docs describe). Use
   what the docs say — do not assume a fixed set.
2. **Read the target** — branch on what input 2 was:
   - **A RUN:** read the artifacts **in full** — they're small, and the detail is the point. Reconstruct what
     actually happened: what was asked, what the agent did, where it went wrong, where it had to be corrected, what
     it assumed, what it skipped. Read the diff last, as evidence rather than as the subject.
   - **A WINDOW OF LOGS:** pull out what you actually did — recurring commands, repeated multi-step sequences,
     repeated instructions/corrections, tools reached for, friction/retries. **Aggregate, don't ingest:** logs can
     be huge — prefer the prompt/command-history file over raw transcripts, and reduce with shell tools
     (`jq`/`grep`/`sort | uniq -c`) so only frequencies and representative samples enter your context, never whole
     log files.

   Either way: if you can't locate or parse the target, **ask the user rather than invent.**
3. **Find what to change** — the question differs by target:
   - **RUN (reactive):** for each thing that went wrong or needed correcting, ask **"what in the AI layer would
     have prevented this?"** Name the **smallest durable change** that would have caught it — a line in a rule, a
     step added to a skill, a hook, a tighter tool scope — specific enough to apply today. **Fix the system, not
     the code:** do not propose the code fix, propose the thing that would have made the code fix unnecessary or
     automatic. ⚠️ **Not every failure is a system gap** — if something went wrong that no durable change would
     have prevented, say so plainly instead of inventing a rule for a one-off. One honest "nothing to change here"
     is worth more than five speculative rules.
   - **LOGS (proactive):** for each recurring pattern, ask **"what should this become?"** Rank by roughly (how
     often it occurs × how much encoding it would save).

   **Both targets:** pick the **best-fit primitive** (from step 1's list) and say *why*. If input 3 was given,
   **weight it** — surface what the user said they care about even when it isn't the most frequent pattern, and say
   plainly when a high-frequency pattern is *not* worth encoding. And propose each change **in the house style of
   the artifacts that already exist**: skim a couple of the project's current rules/skills/agents first and shape
   the recommendation to look like them, so what it suggests is something the user would actually build. Examples
   of the mapping:
   - a rule you keep restating → **rules** (CLAUDE.md / AGENTS.md)
   - a repeated multi-step workflow → a **skill**
   - a must-never / must-always you keep enforcing by hand → a **hook**
   - a specialized recurring delegation → a **subagent**
   - a clean end-to-end hand-off you do often → an **automation** (later: an Archon workflow)
4. **Write the report** as a single self-contained HTML file (see the contract below), then tell the user where it
   is.

## Report contract — prescribe HOW to render, never WHAT to include

**Let the analysis drive the report.** Which sections exist, what goes in them, how deep each goes, how many
opportunities, which quotes or numbers are worth pulling out — all of that comes from what you actually found, NOT
from this skill. Do **not** box the report into a fixed set of sections, do **not** seed findings, do **not** tell
it what to conclude. If the data is rich, the report is rich; if a single finding deserves its own deep section,
give it one; if something surprising turns up, surface it.

Only the **rendering** is prescribed:
- One **self-contained `.html`** file (inline CSS), opens in any browser.
- **Visually clean, scannable, and generous** — let the findings breathe; use whatever layout, sections, real
  quotes, stats, or visuals best fit what was actually found.

The rule: this skill governs *how to put it on the page*, never *what goes on the page*.

## Keep it light
Do exactly these four steps, clearly. Don't add scoring frameworks, config, or extra passes it doesn't need. If a
step can't complete (docs or the target not found), stop and ask — never fabricate the analysis.
**Scan one target per run.** If someone wants both the reactive and the proactive view, that's two runs and two
reports — mixing "what broke in this loop" with "what I keep repeating across a month" produces a report that
answers neither question well.
