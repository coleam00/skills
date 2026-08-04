# Skill Standards

The rules every skill obeys — create or refactor. This is the shared "curated context"; keep it here, not
duplicated into the workflow files. These govern the **craft** (how a skill is built), never the **content** (the
sections a plan/PRD/report has, the domain vocabulary, the output shape) — that's the author's per-project call.
Strict on the craft, agnostic on the content.

## Skill types

Classify before applying the rules — the guidance is proportional:

| Type | What it is | Apply |
|---|---|---|
| **Workflow** | a multi-step procedure (plan, review, ship) | full lens incl. verifiable validation gates |
| **Artifact-generator** | produces a document/output | Context-is-King + a *suggested* (never mandated) output shape; validate only if it self-checks |
| **Knowledge / reference** | facts the agent consults | Context-is-King + information-dense; **no** phases, **no** validation loop |
| **Tool-wrapper** | drives a script / CLI / API | deterministic script + sharp triggers; validation = the tool's exit status |

A skill can blend types — apply the union. What you never do is impose a workflow skill's machinery (phases,
validation loops, output skeletons) on a skill that isn't one.

## Anatomy

```
skill-name/
├── SKILL.md          # required: YAML frontmatter + markdown body
├── references/       # docs the agent READS on demand (schemas, patterns, edge cases)
├── templates/        # shapes the OUTPUT follows (report skeletons, output formats)
├── assets/           # non-text resources copied/embedded into the result
└── scripts/          # executable code, RUN without loading its source into context
```

- **references/** = "read this to inform the work."
- **templates/** = "follow this shape when producing output."
- **assets/** = "copy/embed this into the result."
- **scripts/** = "execute this for deterministic, token-free work."

## Context sources

Context is King, but it needn't all be bundled. Draw it from the cheapest place that fits — and curate, don't dump:

1. **Inline** (in `SKILL.md`) — the essentials needed every run. Always loaded; keep it to the spine.
2. **Bundled** (`references/`, `templates/`, `assets/`, `scripts/`) — disclosed on demand.
3. **External pointers** — repo file paths or URLs (optionally `#anchored`). Read/fetched when a step needs them;
   nothing copied in. Use for docs you don't own or content that would go stale if duplicated.
4. **Runtime-gathered** — the skill obtains it when it runs: ask the user (an interactive PRD skill), or inspect
   the environment (read git state, scan the codebase, call a tool).

Choose by **ownership + volatility:** bundle what you own and want versioned; point to what you don't own or what
changes upstream; gather at runtime what only exists in the moment.

## Frontmatter spec

| Field | Required | Constraint | Notes |
|-------|----------|------------|-------|
| `name` | yes | ≤64 chars, lowercase-hyphen, **matches the directory** | the directory name is what becomes `/the-command` |
| `description` | yes | ≤1024 chars, third person, non-empty | the trigger — WHAT it does + WHEN to use it + literal user phrases |
| `argument-hint` | no | string | autocomplete hint, e.g. `<path/to/plan.md> [--base <branch>]` |
| `allowed-tools` | no | string/list | tools usable without a prompt while active |
| `model` / `effort` | no | model / level | per-skill execution override |
| `disable-model-invocation` | no | bool | `true` = user-only (no auto-invoke) |
| `user-invocable` | no | bool | `false` = agent-only, hidden from `/` |

**Invocation control is a deliberate decision, and it depends on context.** A personal read/plan skill can stay
fully open (omit both flags). But a **distributed** skill (shipped in a plugin) that auto-invokes a
**side-effecting** action — commits, pushes, deletes — can surprise other people's agents; for those, set
`disable-model-invocation: true` in the distributed copy. Match the openness to who runs it and what it does.

Other optional fields exist (`when_to_use`, `disallowed-tools`, `paths`, `hooks`, `context: fork`, `shell`) —
reach for them only when a skill needs one, and **confirm against the current Claude Code skills docs** (the field
set evolves).

## Progressive disclosure (the core mechanic)

Three load levels — design every skill around them:

1. **Metadata** (`name` + `description`) — always in context. ~100 words. The trigger budget.
2. **Body** (`SKILL.md`) — loaded when the skill triggers. Target **1,500–2,000 words**, hard ceiling ~5k. Paid
   for on every use.
3. **Resources** (`references/`, `templates/`, `scripts/`) — loaded only when the agent reaches for them.
   Effectively unlimited; scripts cost ~zero context (only their output enters the conversation).

**Implication:** the decision spine + workflow go in the body; bulky, occasionally-needed, or output-shaped detail
goes in resources. *(This skill is its own example — a lean body, the detail down here.)*

## Writing voice — two distinct registers
- **`description` → third person, with literal trigger phrases.**
  - Good: `Extract text and tables from PDFs… Use when the user mentions PDFs, forms, or document extraction.`
  - Bad: `Helps with documents.` (vague) · `Use this when you…` (wrong voice, no triggers)
- **Body → imperative / infinitive, NOT second person.**
  - Good: `Validate the output before reporting.` · `To extract fields, run scripts/analyze.py.`
  - Bad: `You should run the script.` · `Claude will validate the output.`

## No duplication
A fact lives in exactly one place — body **or** a reference, never both. Prefer references for detail; keep only
the spine + pointers in the body. Duplication is how skills rot (the two copies drift).

## Structure implies a maintainer
If a skill's output carries **stateful** sections — status markers, lifecycle/metadata, an amendments log, a
progress checklist — *something* must keep them current: the same skill on a later run, a companion skill, or an
explicit step. **Never template a stateful section nothing updates.** A "modified" field no step appends, or status
markers no builder flips, is dead weight that quietly lies to the reader. When you template a stateful section,
name its maintainer.

## Wiring
Every bundled file must be linked from `SKILL.md` (end the body with a **Resources** list, one line each on when to
read it) — or the agent won't know it exists. Keep references **one level deep** (linked directly from SKILL.md),
not nested chains. External pointers (paths, URLs) are cited inline at the point of use, but must resolve — a dead
pointer is a broken skill.

## Portability (cross-tool)
- The portable core is `name` + `description` + body + bundled files. Other tools (Cursor, Gemini CLI, the AGENTS
  ecosystem) ignore unknown Claude-only fields rather than erroring.
- Keep the body's *core value* provider-agnostic; note where Claude-only mechanics (subagent fan-out, Stop-hook
  loops) degrade elsewhere.
- Make `scripts/` self-contained: PEP 723 inline deps for Python (`uv`-runnable, no setup), and **derive the
  project root from the cwd / `git rev-parse --show-toplevel`, never from `__file__`** — the script ships in the
  skill but operates on the *user's* project, so a path from its own location breaks once it's installed elsewhere.
- **One source of truth.** A skill lives in exactly one place. If it must exist in two (a dogfood copy + a
  distributed plugin), generate one from the other — never hand-maintain both, or they drift.
