---
name: skills-create
description: Author a new Claude Code skill the house way, or refactor a fat skill into a lean SKILL.md + references/. Use when you want to "create a skill", "write a new skill", "turn a prompt or command into a skill", "split a skill into references", "trim a SKILL.md", or invoke /skills-create. The meta-skill — a skill that builds skills.
argument-hint: "[create <name> | refactor <path/to/SKILL.md>]  (blank = ask which)"
---

# Skills Create — the meta-skill

A skill that authors and refactors skills. Two jobs:

- **Create** a new skill from scratch (or from an existing prompt/command).
- **Refactor** a fat skill — split detail into `references/`, move output shapes into `templates/`, trim
  `SKILL.md` down to a lean spine of pointers.

**It's built the way it teaches:** a lean body that defers detail to `references/`. That's progressive disclosure
(the V19 lesson) — and this skill is its own worked example. **It's all composable markdown:** a skill is a
`SKILL.md` plus optional files the agent loads only when it reaches for them.

## Prescribe the craft, not the content

Be **strict on how a skill is built** and **agnostic on what any given skill — or its output — should contain.**

- **Prescribe (firm, universal):** progressive disclosure · a third-person, trigger-rich `description` · an
  imperative, lean body · no duplication · every bundled file wired · deliberate invocation control · validation
  that fits the skill type. (See `references/skill-standards.md`.)
- **Do NOT prescribe (the author's call):** the sections a plan/PRD/report should have, the domain vocabulary, the
  output shape, which phases exist. There is no canonical output — guide the author to a good decision, never hand
  them a fixed one.

Strict on the craft so the author stays free on the content. *(This is the course's "guide, don't prescribe" — and
take-vs-build: you **build** a skill when you own the process and want it to follow YOUR way.)*

## Classify the skill first

Pin the **type** before applying the craft — the guidance is proportional, not one-size-fits-all:

| Type | What it is | Apply |
|---|---|---|
| **Workflow** | a multi-step procedure (plan, review, ship) | the full lens incl. verifiable validation gates |
| **Artifact-generator** | produces a document/output | Context-is-King + a *suggested* (never mandated) output shape |
| **Knowledge / reference** | facts the agent consults | Context-is-King + information-dense; **no** phases, **no** validation loop |
| **Tool-wrapper** | drives a script / CLI / API | a deterministic script + sharp triggers; validation = the tool's own exit code |

A skill can blend types — apply the union of what fits. Never force a workflow's machinery (phases, loops, output
skeletons) onto a knowledge skill. Full detail: `references/skill-standards.md` → Skill types.

## Step 0 — pick the mode (from `$ARGUMENTS`)

Parse **`$ARGUMENTS`** to pick the mode and the target:
- Starts with **`create [<name>]`** (or is clearly a new-skill ask) → **create** mode; use `<name>` as the skill
  name if one was given → follow `references/creating-skills.md`.
- Starts with **`refactor <path/to/SKILL.md>`** (or points at an existing skill) → **refactor** mode on that
  path → follow `references/refactoring-skills.md`.
- **Blank or unclear** → ask which mode and what the skill/target is. Don't guess.

Both modes obey the same craft rules → read `references/skill-standards.md` first.

## Create — quick spine (full detail: `references/creating-skills.md`)
1. **Gather context** — the literal phrases that should trigger it, the task start-to-finish, the gotchas, the
   patterns to mirror. Ask the user; don't write yet.
2. **Plan the resources** — what repeats → `scripts/`; what informs the work → `references/`; what shapes the
   output → `templates/`; what you don't own / changes upstream → cite a path/URL; what only exists at runtime →
   gather it (ask the user, read git/codebase).
3. **Scaffold** — copy `templates/SKILL.template.md` to `.claude/skills/<name>/SKILL.md`; add `references/` /
   `templates/` only as the plan needs.
4. **Write the spine first** — third-person trigger-rich `description`; imperative, lean body; push detail to
   references. Get it *triggering* before you write the references.
5. **Validate & iterate** — `references/validation.md` (checklist → trigger test → run it for real).

## Refactor — quick spine (full detail: `references/refactoring-skills.md`)
1. **Inventory** the SKILL.md — mark each block *spine* (keep) vs *extractable* (output templates, schemas, long
   examples, exhaustive pattern/edge-case lists).
2. **Extract verbatim** into the target skill's `references/` (or `templates/` for output shapes) — don't reword
   anything that affects behavior.
3. **Replace with a pointer** — for **always-needed** content, a *mandatory-read* line ("Before producing output,
   read `templates/<x>.md`"); for sometimes-needed content, a lazy pointer.
4. **Behavior-preservation check** — same process, same output as before. Nothing lost, nothing duplicated.
5. **Validate** — `references/validation.md`.

> **The #1 refactor risk:** moving an *always-needed* output format into a lazily-loaded reference, so the agent
> forgets to read it and the output silently changes. Always pair such an extraction with a mandatory-read line.

## When to build a skill at all
Build one when you **own a process** and want the agent to follow *your* way of it, repeatedly — the take-vs-build
rule from V19. A rough threshold: you've prompted the same thing ~3 times (the Rule of Three) → bank it as a skill.
Don't build a skill for a one-off, or for a tool whose owner already ships a good one.

## Resources
- `references/skill-standards.md` — the craft rules: skill types, anatomy, context sources, frontmatter spec,
  progressive disclosure, writing voice, no-duplication, "structure implies a maintainer", wiring, portability.
- `references/creating-skills.md` — the full create runbook (incl. porting an existing prompt/command).
- `references/refactoring-skills.md` — the full split-and-trim runbook, with a before/after.
- `references/validation.md` — the validation gates (structure · description · body · disclosure · behavior · trigger test).
- `templates/SKILL.template.md` — the lean SKILL.md skeleton to scaffold from.
