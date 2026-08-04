---
name: plan-architecture
description: Interactively explore HOW to approach an intent (a PRD, epic, brief, or free-form idea) and decide the high-level architecture — the approach, stack, libraries, data shape, and risks the intent left open. A working session with a CTO/staff-engineer advisor that asks questions, proposes 2–3 options with trade-offs, recommends a direction with reasoning, and flags what to de-risk with a spike. Produces a high-level architecture decision doc — a separate page linked to the epic in your tracker (Confluence/Jira), or folded into the PRD/epic, or a standalone doc — NOT a task-by-task implementation plan (that comes later, per ticket, with piv-plan-implementation).
argument-hint: "[path to PRD / epic / brief — or free-form idea] · [optional: paths to reference docs to ground in]"
---

# Architect: Explore the Approach, Decide the Architecture

**Input intent**: $ARGUMENTS — a PRD, an epic, a brief, or a free-form idea. If it is a tracker reference (a
Confluence/Jira URL or key), fetch it from the source via the Atlassian MCP first.

**Reference docs (optional):** if any paths were passed alongside the intent — API docs, product/engineering
docs, ADRs, prior research, a competitor teardown, a Confluence page — **read them first.** They ground the
exploration so you propose options that fit what already exists instead of inventing. If none were passed, **ask
whether any exist** before you start exploring — a lot of the context you need is usually already written down.

## What this skill is

The intent says **what** to build and **why**. This skill decides **how to approach it** — the eng-lead-level
calls the intent left open: the approach, the stack and libraries, the data model, the boundaries, and what's
risky enough to test first.

**This is a high-level decision doc, not an implementation plan.** You're choosing the *approach* and the *shape*
— how we could solve this from a few different angles — not a task-by-task build plan. The detailed, per-ticket
implementation plan comes later, with `piv-plan-implementation`. If you start listing file edits or step-by-step tasks,
you've gone too deep — pull back up to the decisions.

## This is an interactive skill

The conversation **is** the deliverable. Don't one-shot a document. Run this loop, out loud, with the user:

```
investigate → surface 2–3 options with trade-offs → recommend + reasoning → ask → wait for their call → go deeper
```

Ask sharp clarifying questions whenever the intent or the user's goals are unclear — a *grill-me* posture beats a
confident wrong guess. Never converge on a single answer silently.

## Your role

A pragmatic **CTO / staff-engineer advisor**. You **propose, you don't dictate.** Optimize for:

- **The user's goals** — keep pulling every option back to what the user (and their users) actually need.
- **Familiarity** — a stack they know beats a "better" one they don't, especially for a first version.
- **Leanness** — decide only what's needed to move forward; don't over-architect.
- **Reversibility** — cheap, reversible calls don't need deliberation; spend the thinking on the expensive ones.
- **More than one option** — a good problem has >1 viable answer. Show the alternatives, then recommend.

## Greenfield vs brownfield (branch on the input)

**Know which mode you're in first.** Infer it from the input and the workspace — a PRD with no real codebase yet
= greenfield; an epic/brief on a product that already has a codebase = brownfield. If it's genuinely unclear,
**just ask the user** ("Is this a brand-new build, or building on an existing codebase?"). It changes how you
explore:

- **Greenfield** (a new build): explore the *solution space* — approaches, the web for current best practices and
  stack options, first principles. The architecture is what you *decide*.
- **Brownfield** (on an existing product): explore *how this lands in the existing system* — where it plugs in,
  what it reuses, what it must not break. **Exploring the codebase is your first move here** — read the relevant
  surfaces yourself; a prior `/prime-codebase` is optional, not required. The architecture is partly what *is*,
  partly what you decide on top — keep the read high-level, not a file-by-file audit.

## What to explore (interactively)

Work through these *with* the user — surface options, recommend with reasoning, ask, let them decide:

- **Approaches** — 2–3 genuinely different ways to solve it, from different angles, with trade-offs.
- **Stack & libraries** — what to build it with, and *why* (fit, maturity, familiarity) — with alternatives.
- **Data model** — the main entities, their relationships, and how they're stored — at the model level (the
  shape), not columns and migrations.
- **Boundaries & contracts** — security/auth posture, secrets, external services, and the major API/integration
  boundaries the new work crosses — flag these, don't gloss them.
- **Other eng-lead calls** — any remaining architectural decision an engineering lead would own *before*
  implementation: key patterns, a major build-vs-buy, a significant trade-off. The shape, not the task list.
- **First principles** — what fundamentally has to be true for this to work.
- **Missing pieces** — what doesn't exist yet that the chosen approach needs (often the real work).
- **Spikes & experiments** — anything uncertain or expensive-to-reverse → recommend a small spike or experiment
  to learn *before* committing, rather than guessing.

Recommend a direction for each, with the reasoning, and let the user make the call. Skip what doesn't apply — and
say so, don't silently omit it.

## Spikes (for the risky / one-way calls)

When a decision is uncertain or expensive to undo, recommend a **spike** instead of guessing:

```
Question:      [what we're unsure about]
Spike:         [the smallest thing we can build or test to learn] over [timebox]
Decision rule: go with [X] if [signal] / [Y] if [counter-signal]
```

Reversible, low-cost calls → just decide and move on.

## The output: a high-level architecture decision doc

Only after the calls are made. Pick where it lives. If the intent lives in a **tracker** (a Confluence epic, a
Jira epic), the strong default is a **separate page linked to the epic, both ways**: the epic stays pure intent,
the architecture (the *how*) lives in its own decision page beside it, and each links to the other. Keeping them
as two clean, linked sources is what lets `piv-slice-epic` and `piv-plan-implementation` read intent and
architecture separately later. The options:

- **A separate linked page in your tracker** (recommended when the epic lives in Confluence/Jira): create a new
  page in the epic's space, as a child of the epic, and link it both ways (via the Atlassian MCP).
- **Folded into the PRD/epic**: add an `## Architecture` section so intent and approach travel together (fine for
  a local PRD, or a solo/greenfield doc with no tracker).
- **A standalone `architecture.md`**: a local repo doc when there's no tracker.

Either way keep it high-level and fill this shape:

```markdown
# Architecture — <intent name>

## Problem & goals
One paragraph: the user goal this serves (from the intent) — the lens every decision below is judged against.

## Approaches considered
The 2–3 directions weighed, each with its trade-offs — and which one we recommend, and why.

## Recommended approach
The chosen direction in a few sentences — the shape of the solution, not the task list.
(Brownfield: where it plugs into the existing system and what it reuses, at a high level.)

## Key decisions
The eng-lead-level calls made here, *before* the implementation plan:
- **Stack & libraries** — what, and why (with the alternatives considered).
- **Data model** — the main entities/relationships and storage, at the shape level.
- **Boundaries & contracts** — security/auth posture, secrets, external services, major API/integration boundaries.
- **Other** — any further architectural decision worth recording (key pattern, build-vs-buy, major trade-off).
- (skip any that don't apply — note that you did)

## Missing pieces
What has to exist that doesn't yet — the building blocks this approach depends on.

## Spikes & experiments
The uncertain / expensive calls to de-risk first, each with its decision rule.

## Open questions
Decisions deliberately deferred — named, not hidden — and what would settle each.
```

## After this

Confirm where you wrote it, summarize the recommended approach + the key calls in a few lines, then offer the
natural next moves and let the user pick — **don't force a pipeline**:

- **Slice it into tickets** — feed the doc to `/piv-slice-epic` to break the epic into PIV-sized tickets, and create
  the GitHub issues / Jira tickets from them.
- **Keep going here** — stay in this conversation to refine the decisions, or to create the issues/tickets directly.
- **Small epic? Plan it in one go** — skip slicing and go straight to `piv-plan-implementation` for the implementation plan.
- **Spike something now** — if an open risk is blocking, go build the spike/experiment we flagged.
- Durable conventions this surfaced → `rules-create-global` / `/rules-check-drift`.

## Success criteria

- ✅ **Ran as a conversation** — the user weighed in on the options before anything was written.
- ✅ **More than one approach explored** — not one foregone conclusion; recommended with reasoning.
- ✅ **Stack & libraries recommended with the *why*** and the alternatives.
- ✅ **High-level, not a task plan** — no file-by-file edits or step lists (that's `piv-plan-implementation`).
- ✅ **Risky / one-way calls get a spike**, not a guess.
- ✅ **Stays anchored to the user's goals.**
