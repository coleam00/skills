# Creating a Skill

Read `skill-standards.md` first. This is the full create runbook.

## Step 1 — Gather context (Context is King)

Don't write anything yet. Collect, from the user or the codebase:
- **Triggers** — the exact phrases someone would say that should invoke this skill. Ask directly: *"What would
  you type or say that should trigger this?"* Capture 3–6 concrete phrases.
- **Task** — what the skill does, start to finish. What's the end artifact or output?
- **Gotchas & patterns** — the non-obvious domain knowledge, the existing patterns in the repo to mirror, the
  constraints a fresh agent would get wrong.
- **Scope boundary** — one skill = one capability. Two unrelated capabilities = two skills.

Ask the most important questions first; don't bury the user in a questionnaire. Remember context can be **bundled**,
**pointed to** (path/URL), or **gathered at runtime** (ask the user, read git/codebase) — decide per the skill.

## Step 2 — Plan the resources

Classify each part of the task (see `skill-standards.md` → Anatomy / Context sources):
- Code run every time / needing deterministic reliability → `scripts/` (PEP 723 for Python).
- Detail that informs the work (schemas, exhaustive patterns, edge cases) → `references/`.
- A fixed shape the output must follow → `templates/`.
- Files embedded/copied into the output → `assets/`.
- Context you don't own / changes upstream → cite a **path or URL** in the body; don't bundle.
- Context that only exists at runtime → instruct the agent to **gather it**.

Write the list down before scaffolding. It's the skill's blueprint.

## Step 3 — Scaffold

```bash
mkdir -p .claude/skills/<name>
cp .claude/skills/skills-create/templates/SKILL.template.md .claude/skills/<name>/SKILL.md
# add references/ templates/ scripts/ assets/ only as the plan requires
```

Naming: `lowercase-hyphen`, descriptive, prefixed if part of a family (the pack's `piv-*`, `plan-*`, `rules-*`,
`prime-*`). **Directory name = the `/command`.**

## Step 4 — Write the spine first (progressive success)

Write `SKILL.md` to the standard:
- **Description** — third person, lead with what it does, then "Use when …" with the literal triggers from Step 1.
  Include the `/name` invocation as one trigger.
- **Body (imperative)** — the decision logic + workflow only. Each step verb-first. Where a step needs bulk
  detail, write a one-line pointer to a reference instead of inlining it.
- **Invocation** — omit `user-invocable` / `disable-model-invocation` for a normal read/plan skill (both paths
  open); set `disable-model-invocation: true` if it's distributed *and* side-effecting (see standards).
- End with a **Resources** section listing every bundled file.

Get this minimal version **triggering and working** before writing the references. A spine that doesn't trigger is
worth more fixing than a perfect reference no one reaches.

## Step 5 — Fill the resources

Write the planned `references/` / `templates/` / `scripts/`. Apply no-duplication: as content moves into a
reference, **remove it from the body** and leave a pointer. For an output format the skill must ALWAYS follow, put
it in `templates/` + add a mandatory-read line ("Before producing output, read `templates/<x>.md`"). Occasional
detail gets a lazy pointer.

## Step 6 — Validate & iterate
Run every gate in `validation.md` (structure · description · body · disclosure · trigger test). Then **use it on a
real task** and watch where the agent struggles — strengthen triggers if it fails to auto-invoke, clarify or move
content if it misuses it. Fold the fix back in.

## Porting an existing prompt or command (the v1 → v2 motion)

This course turned its v1 slash-*commands* into v2 *skills* — the same move you'll often make. **Fidelity first,
optimize second:** a port is behavior-preservation, not a redesign.
1. Move the body **verbatim** into `.claude/skills/<name>/SKILL.md` — it's the proven process/output.
2. Transform only the frontmatter: add `name`, extend `description` with trigger phrases, keep
   `argument-hint`/`allowed-tools`/`model`.
3. Remove the old command file so there's no duplicate `/name`.
4. If the body's long, hand off to `refactoring-skills.md` to split it — a **separate** step, after the verbatim
   port is proven.
