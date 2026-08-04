# Validation Gates

Run these after creating or refactoring a skill. Fix failures before declaring done.

## Gate 1 — Structure
- `SKILL.md` exists with valid YAML frontmatter delimited by `---`.
- Frontmatter has `name` (matches the directory, lowercase-hyphen, ≤64) and `description` (≤1024, non-empty).
- Every file referenced in the body actually exists (no dead pointers).
```bash
ls -R .claude/skills/<name>
grep -nE '`(references|templates|scripts|assets)/' .claude/skills/<name>/SKILL.md
```

## Gate 2 — Description quality (the trigger)
- Third person; not "Use this when you…".
- States WHAT it does AND WHEN to use it.
- Contains literal trigger phrases a user would actually say, plus the `/name` invocation.

## Gate 3 — Body style & size
- Imperative / infinitive voice throughout; no second person ("you should").
- The body is the decision spine + pointers, not a data dump.
- Target 1,500–2,000 words; investigate anything over ~5k.

## Gate 4 — Progressive disclosure
- Bulky / occasionally-needed / output-shaped detail lives in `references/` or `templates/` (or is cited by
  path/URL, or gathered at runtime) — not inlined.
- No content duplicated between body and resources.
- Always-needed output formats have a **mandatory-read** pointer; sometimes-needed detail has a lazy pointer.
- References are one level deep and all linked from a Resources section.

## Gate 5 — Behavior preservation (refactors only — non-negotiable)
- The trimmed skill + resources drives the SAME process and SAME output as the original.
- At every point the original inlined content, the body now reaches the right pointer at the right time.
- Nothing dropped, nothing duplicated. When uncertain, keep content in the body.

## Gate 6 — Independent review
Run the `code-reviewer` agent (or Claude Code's native `skill-reviewer`, if available) over the new skill for a
fresh-eyes check of description quality, organization, and progressive disclosure. Apply its high-confidence
findings; ignore noise.

## Gate 7 — Trigger test, then exercise for real
- **User invocation:** confirm `/<name>` appears and runs.
- **Agent invocation:** describe a task in the skill's domain (using one of the trigger phrases) and confirm the
  skill auto-loads. If it doesn't, strengthen the `description` triggers and retry.
- **Exercise it end-to-end on real work** — don't stop at "it loaded." A real run surfaces bugs a load-check never
  will. Fold what you learn back in.

## Done
All gates pass. For a refactor, **Gate 5 is non-negotiable** — a refactor that changes output is a regression.
