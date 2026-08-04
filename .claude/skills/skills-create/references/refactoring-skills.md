# Refactoring a Skill (split & trim)

Read `skill-standards.md` first. Use this when a `SKILL.md` has grown fat — a long body that loads (and costs
tokens) on every use, when most of it is only sometimes needed. Refactoring is **progressive disclosure applied
after the fact**: pull detail into `references/`/`templates/`, leave a lean spine of pointers.

## Step 1 — Inventory

Read the target `SKILL.md` and classify each block:
- **Spine (keep in the body):** the description, the decision logic, the step-by-step workflow, the pointers.
- **Extractable (move out):** output-format templates, schemas, long worked examples, exhaustive pattern catalogs,
  troubleshooting / edge-case lists — anything bulky or only *sometimes* needed.

## Step 2 — Extract verbatim

Move each extractable block into the target skill's own `references/` (or `templates/` for output shapes).
**Don't reword anything that affects behavior** — a refactor preserves behavior; rewriting is a separate change.

## Step 3 — Replace with a pointer
- **Always-needed** content (e.g. an output format the agent must always follow) → a **mandatory-read** line:
  *"Before producing output, read `templates/<x>.md` and follow it exactly."*
- **Sometimes-needed** content → a **lazy pointer:** *"For edge cases, see `references/<x>.md`."*

## Step 4 — Behavior-preservation check
The trimmed skill + its resources must drive the **same process and the same output** as before. At every point
the original inlined content, the body now reaches the right pointer at the right time. Nothing dropped, nothing
duplicated. **When in doubt, keep it in the body** — a smaller token win isn't worth a behavior change.

## Step 5 — Validate
Run `validation.md`, and **Gate 5 (behavior preservation) is non-negotiable** — a refactor that changes the output
is a regression, not a cleanup.

## Before / after (sketch)

**Before** — one 400-line `SKILL.md`: description · workflow · a 120-line output template · a 90-line edge-case
catalog · a long worked example.

**After:**
```
the-skill/
├── SKILL.md                  # description · workflow · "Before output, read templates/report.md" · Resources
├── templates/report.md       # the 120-line output format (mandatory-read)
└── references/
    ├── edge-cases.md          # the 90-line catalog (lazy pointer)
    └── example.md             # the worked example (lazy pointer)
```
The body now triggers and loads cheap; the bulk loads only when a step reaches for it.

> **The #1 risk:** moving an *always-needed* output format into a lazily-loaded reference, so the agent forgets to
> read it and the output silently changes. Always pair that extraction with a mandatory-read line — and verify it
> in Gate 5.
