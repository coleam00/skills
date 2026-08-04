---
name: rules-check-drift
description: "Check whether your rules file (CLAUDE.md or AGENTS.md) still matches the codebase after recent changes — run before a merge, or fold into your code-review pass. Reports stale/now-false rules, drifted architecture-map entries, and any new invariant worth adding, each with the minimal edit. Advisory and anti-bloat: it keeps the rules file true, never longer than it needs to be."
argument-hint: "[optional diff range, e.g. main...HEAD]"
---

# /rules-check-drift — keep your rules file true, not longer

Your rules file — **`CLAUDE.md`** or **`AGENTS.md`** — is a **steering document, not documentation**: your ground
rules, your conventions, and a current **map of where things live**. Its only failure mode that matters is being
**wrong**: a stale rule or a drifted map actively misleads the agent on every future run. This skill checks the
rules file against what just changed and proposes the **smallest** edit that keeps it true.

> **Wrong rules are worse than missing rules. A longer rules file is worse than a lean one.** Most changes
> need *no* edit at all — adding a wrong or verbose line makes it worse.

## Input
- `$ARGUMENTS` — optional diff range. Default: uncommitted + staged (`git diff HEAD`); fall back to `main...HEAD`.
- **Scope: the project's rules file(s)** — `CLAUDE.md` and/or `AGENTS.md`, the root file + any package-level
  ones. (If `CLAUDE.md` is just a `@AGENTS.md` import, check `AGENTS.md`.) Ignore README, `docs/`, and `.claude/`
  agent/command/skill files. This skill exists to keep the *rules* honest, nothing else.

## Process

### 1. See what changed
`git diff <range>` + `git status`. Note: moved/renamed/removed files, new modules, changed conventions,
and any new invariant the change establishes.

### 2. Read the rules file as it is now
Load the project's rules file — `CLAUDE.md` or `AGENTS.md` (and any package-scoped ones). Hold each claim against the change set.

### 3. Flag ONLY these three things
1. **A stated rule or fact is now false** — e.g. "routes live in `src/routes/`" but they moved. → fix it.
2. **The architecture map drifted** — a path or "where things live" pointer no longer matches reality.
   → fix the wrong entry (don't catalog every new file).
3. **A new durable invariant must hold going forward** — the change introduces a rule that must stay true
   (e.g. "never call the DB from handlers — go through `repository/`"). → add it as **one line**.

Everything else, leave alone. Do **not** suggest an edit to *record that a feature was added* (that's a
changelog — the codebase is the source of truth), to restate what the code already makes obvious, or to add
background/rationale/prose that doesn't steer future work.

### 4. Write each suggestion the way CLAUDE.md should read
- **One bullet, not a paragraph.** A rule is a line, not an essay.
- **Keep the map current — don't grow it.** Fix the wrong path; don't enumerate the new ones.
- **State rules in natural language; reference the codebase, never paste code.** Copied code goes stale; the
  codebase stays true. Good: "follow the error pattern in `src/core/errors/`." Bad: pasting the class.

## Output
```
## Rules-file drift check — range: <range>

### Fix (now false)
| Where | What's wrong | Minimal fix |
|-------|--------------|-------------|
| "Architecture" map | routes moved `src/routes/` → `src/api/routes/` | update the one path |

### Add (new invariant only)
- <one-line rule> — established by <the change that made it durable>

### Checked, still true — no edit
- <areas you verified need no change>
```
If nothing drifted: **"The rules file is still accurate for these changes — no edits needed."**

## Rules
- **Advisory.** Report the drift; only apply/piv-commit edits if the caller explicitly asks.
- **Rules file only** (`CLAUDE.md` / `AGENTS.md`). Not README, not docs.
- **Lean by default.** When in doubt, suggest nothing.
- **Run it before every merge** (or as part of `/piv-review-changes`) so your rules never drift behind the code.
