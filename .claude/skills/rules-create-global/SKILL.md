---
name: rules-create-global
description: "Set up your project's global rules, a lean and well-structured root CLAUDE.md (plus a starter .claude/), following the course methodology. Greenfield: pass your PRD and/or architecture-spec path and it derives rules from your engineering decisions (a PRD alone is product context). Brownfield: leave it blank to derive from your primed codebase (run /prime-codebase first), or pass a codebase-analysis doc for a large repo. Use when initializing or re-deriving the AI Layer's rules, onboarding a codebase, or replacing a generic /init output. The customizable replacement for /init."
argument-hint: "[prd-path] [architecture-path]  (greenfield; brownfield: blank + prime first, or pass a codebase-analysis)"
arguments: [path1, path2]
---

# Create Rules: Set Up Your Project's Global Rules

## Inputs: wire the arguments first

This skill takes **up to two optional paths** and uses them to pick your lane. Read whatever was passed and classify each by its content:
- `$path1`: the first path, if any.
- `$path2`: the second path, if any.

| A passed path that is... | Lane | Use it as |
|---|---|---|
| a **PRD** (intent, what/why, from `plan-create-prd`) | greenfield | product context (the "what this is"), NOT the source of technical rules |
| an **architecture / spec doc** (the how, from `plan-architecture`) | greenfield | the technical decisions your rules derive from (may be the *same file* as the PRD, if the architecture was folded in as an `## Architecture` section) |
| a **codebase-analysis doc** (a large-repo `/prime-codebase` + subagent fan-out) | brownfield | the source of "what is" |

**Pick the lane from what you were given:**
- **Greenfield** if a PRD and/or architecture path was passed, or the workspace is a bare scaffold: derive **what should be** from the **architecture decisions** (`$path2`, or `$path1` if that is where they live).
- **Brownfield** if no path was passed, or a codebase-analysis path was: derive **what is** from the analysis doc if one was passed, otherwise from the **primed codebase in this conversation**.

> **Brownfield, not primed yet?** If no path was passed and this conversation has not been primed on the code, run **`/prime-codebase`** first (or offer to) so you derive from real files, then continue. Never invent rules from nothing.

## What global rules are (30-second intro)

Your global rules — **`CLAUDE.md`** (Claude-native) or **`AGENTS.md`** (the open cross-tool standard) — are the
**always-on steering document**, read on every task. Four kinds of content earn that always-on slot:
1. **A map of the codebase** — the dirs/files that matter, each with a one-line *what it is + why it lives there*.
2. **Ground rules** — the *specific conventions* this project follows (how you do type safety, your error
   philosophy, your git workflow). State the choice, not a slogan.
3. **Commands the agent should run itself** — the real lint / type-check / test / tooling CLIs (with their flags),
   so it can check its own work. (Not slash-commands — those are *skills*.)
4. **Working principles (agent steering)** — how you want the agent to *operate* here: its thinking/reasoning
   posture (plan before non-trivial work, ask when ambiguous instead of guessing, keep scope tight) and the
   engineering primitives you hold (fail fast, explicit errors, single responsibility, simplest thing that
   works). **These don't live in the code — you state them.** They're the part deriving-from-the-codebase can
   never produce — and the part an agent won't reliably follow unless you make it explicit.

**It's all composition.** Rules, references, and skills are just markdown the agent loads when it needs them — so
any of the above can live always-on *or* in an on-demand `references/` doc *or* in a skill; you choose where each
piece lives. Everything not needed every task loads **on demand**, or belongs in a per-task **plan** — not here.

## Two situations, one motion

Global rules encode **technical** truth — so you derive them from technical decisions, never from a product spec:

| You have... | Derive rules from... | "Truth" is... |
|-----------|--------------------|-------------|
| **Greenfield**, a new project, mostly a scaffold | your **architecture decisions** (the technical "how" you settled with the AI), passed as `$path2` | *what should be* |
| **Brownfield**, an existing codebase with no AI Layer | your **primed codebase** (`/prime-codebase`), or a **codebase-analysis** doc passed as a path for a large repo | *what is* |

> **Greenfield note:** your rules come from your **architecture decisions** (the spec), not the PRD. The flow: discuss
> *what* you're building with the AI and capture it as a PRD (`plan-create-prd`), then settle the **architecture**
> with `plan-architecture` (stack, patterns, directory structure, conventions). *Those* decisions are what this
> skill derives rules from. A PRD captures the *product* (what/why): useful context, but technical rules don't live there.

> **Brownfield note:** this skill does **not** explore the codebase for you. Prime first: run **`/prime-codebase`**
> so the structure, key files, and conventions are loaded into this conversation, then run this skill with no path.
> (Large repo? Optionally fan out a few built-in subagents to explore areas in parallel, aggregate a short
> `codebase-analysis.md`, and pass that path instead.) This skill packages the *derive → extract → seams → prune → check*
> steps, not the exploration.

> **Before you run this — protect any existing rules.** If the project already has a `CLAUDE.md` /
> `AGENTS.md`, **copy or rename it first** (e.g. `CLAUDE.md.bak`) so this skill doesn't overwrite something
> you want to keep. Even better, **feed it in as input** — point the skill at it ("read my existing
> `CLAUDE.md` first") so the derivation *builds on* what's already there instead of starting from scratch.

## Required reading (do this first) — and pick the file

**First, which rules file does this project use?** Detect it, then read the matching guidance (don't rely on a snapshot):
- **`CLAUDE.md`** (Claude Code's native file) → Anthropic memory + best practices:
  https://code.claude.com/docs/en/memory · https://code.claude.com/docs/en/best-practices
- **`AGENTS.md`** (the open cross-tool standard, read by dozens of agents) → the AGENTS.md spec: https://agents.md
- **Both present?** Usually the shared content lives in **`AGENTS.md`** and `CLAUDE.md` is a single line —
  `@AGENTS.md` — so Claude Code auto-loads AGENTS.md and there's one source of truth. In that case, write to AGENTS.md.
- **Neither yet?** `CLAUDE.md` for a Claude-Code-only project; `AGENTS.md` if the team is multi-tool.

Content + structure are ~90% identical either way — everything below is **"your rules file,"** not one vendor's.
Use the structure laid out below (it works as an AGENTS.md just as well).

## The methodology (bake this in)

- **What goes always-on:** the **map** + **ground rules** (specific conventions) + the **working principles**
  (agent steering). Everything true *project-wide, every task*.
- **Working principles are *elicited*, not derived.** The map + ground rules come from the code/decisions; the
  working principles come from **you** — so **ask**: "how should the agent work here — plan-first? clarify before
  coding? scope discipline? which engineering primitives do you hold?" Keep only the ones that actually *change
  behavior* and reflect *your* stance — not a generic lecture the model already follows.
- **The four destinations** — sort every candidate line:
  - **Keep always-on** → map / ground rules.
  - **Push to on-demand** → a recurring but task-*type*-specific pattern → an on-demand reference
    (`.claude/references/<topic>.md` on Claude Code; anywhere your tool looks — e.g. `.agent/` — it's just markdown) or a skill.
  - **Move to a plan** → task-specific "what to build next" content → it was never a rule.
  - **Delete** → redundant, or a slogan the model already follows ("write clean code", "KISS/DRY").
- **State the choice, not the slogan:** "derive types with `z.infer`", not "type safety is critical".
- **Brownfield = "what is", not "what should be":** every rule must point to the file that proves it; if you
  can't, leave it out. Aspirational rules make the agent fight the codebase.
- **Lean:** don't bloat it to the point it eats context or the agent starts ignoring its own rules. No magic
  line number — cut anything that wouldn't cause a mistake if removed.

## Workflow

### 1. Read the inputs
- **Greenfield:** read the **architecture / spec doc** you passed as `$path2` (or `$path1`, if that is where the
  architecture lives): stack, patterns, directory structure, conventions, security choices, plus any scaffold
  files. *(A PRD passed as `$path1` is product context: read it for **what** you're building and why, not for the
  technical rules.)* No path passed but the workspace is a fresh scaffold? Ask for the architecture doc, or settle
  the decisions now with `plan-architecture` first.
- **Brownfield:** derive from the **primed codebase** already loaded in this conversation (from `/prime-codebase`);
  or, if a `codebase-analysis.md` path was passed, read that (with its file:line citations). Spot-check the actual
  code either way. Not primed and no path passed? Run `/prime-codebase` first.
- **If a rules file already exists:** read it first and treat it as a starting point — and make sure it's
  backed up (see "protect any existing rules" above) so nothing you wrote by hand is lost.
- Read the best-practices docs above. Follow the structure laid out in this skill.

### 2. Derive the root `CLAUDE.md`
Fill the template's sections, sourced from the input:
- **What this is** — one paragraph + the stack in one line.
- **Architecture map** — the tree of dirs/files that matter, one-line what/why each.
- **Ground rules** — the specific conventions (greenfield: decided in your **architecture spec**, not the PRD;
  brownfield: *observed in the code*, each traceable to a file).
- **Working principles (agent steering)** — **ask the user** (this can't be derived from code): how should the
  agent operate here? Capture the thinking/reasoning posture (plan-first, clarify-don't-guess, scope discipline,
  verify against the *real* suite) + the engineering primitives they hold (fail fast, explicit errors, single
  responsibility, simplest-thing-that-works). State the project's *actual* stance; keep it lean.
- **Commands** — the few you actually run (install / test / type-check / lint / run).
- **On-demand pointers** — where detail loads when needed.
Don't dump the PRD or the analysis in. Link to them.

### 3. Extract on-demand context
Pull recurring, task-type-specific patterns out into `.claude/references/<topic>.md` **stubs** (a paragraph
each, not full docs). Test: *does it recur every time you touch that area?* → guide. One-off → leave in the
source doc.

### 4. Find the seams
Add a short **"where new code goes"** section — the interfaces/folders where new work plugs in. This is what
makes the agent *extend* the codebase instead of bolting on. (Greenfield: the seams are *designed* from the
architecture, not discovered.)

### 5. Prune to lean
First draft is always too big. Delete generic advice, restated defaults, and anything that can't point to its
evidence. Apply the per-line test: *would removing this cause a mistake? If not, cut it.*

### 6. Report
- Files created/changed.
- A 3–5 line summary of what went into `CLAUDE.md` and why.
- What was pushed to on-demand context (and where).
- Next step: the rules are ready — start the first PIV loop.

## Quality checks

- ✅ Root `CLAUDE.md` is a **map + ground rules**, not documentation or a PRD/analysis copy.
- ✅ Every ground rule is a **specific choice** (brownfield: traceable to a file) — no slogans.
- ✅ A **working-principles / agent-steering** section exists — *elicited from the user* (plan / clarify / scope
  posture + engineering primitives), lean and behavior-changing, not generic filler.
- ✅ Recurring task-type detail lives in `.claude/references/`, not always-on.
- ✅ Lean enough that nothing earns its slot without paying rent.

## Notes

- Rules **evolve** — revisit `CLAUDE.md` as the project grows and after major model releases, and run
  `/rules-check-drift` before merges so the map never drifts.
- Greenfield: run after you've settled the architecture with `plan-architecture` (and after `plan-create-prd`, if
  you wrote a PRD for the product); pass those paths in as `$path1` (PRD) and `$path2` (architecture). Brownfield: run after
  `/prime-codebase`, or after a large-repo fan-out produces a `codebase-analysis.md` you pass in.
