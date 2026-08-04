---
name: piv-validate
description: Runs this project's full validation suite — tests, type checks, and linting across every part of the stack — then reports overall health. Use before committing, before opening a PR, or after finishing a chunk of work to confirm zero regressions.
---

# Validate

Run every check this project has and report a single PASS/FAIL verdict.

> ## ⚠️ Make this yours first
>
> **This skill is a template. The command list below is a placeholder — replace it with the commands
> *your* project actually uses.** That is the entire point of a custom checker: it is the one skill
> that cannot be generic, because it wraps your stack's CLIs.
>
> Find your real commands in `package.json` scripts, `pyproject.toml`, `Makefile`, `justfile`,
> `docker-compose.yml`, your CI workflow, or the README — then delete these and paste yours in.
>
> **Two things to get right, because they are the usual reason a checker silently lies:**
> 1. **Working directory.** Many tools only discover their config from the current directory. If your
>    config lives in `backend/pyproject.toml`, the command is `cd backend && uv run pytest`, not
>    `uv run pytest` from the repo root.
> 2. **Cross-platform.** Avoid POSIX-only idioms if anyone on the team is on Windows — `lsof`,
>    `python3`, and background-then-`kill` are the common offenders.

Run the checks in order. Keep going after a failure so the report covers everything, and capture the
output of any command that fails.

## 1. Tests

```bash
# REPLACE: your test command, run from the right directory
<your test command>
```

**Expected:** all tests pass.

## 2. Type check

```bash
# REPLACE: e.g. mypy, tsc --noEmit, go vet
<your type-check command>
```

**Expected:** no type errors.

## 3. Lint / format check

```bash
# REPLACE: e.g. ruff check, biome check, eslint
<your lint command>
```

**Expected:** clean.

## 4. Repeat per surface

A full-stack project has more than one of each. Add a section per surface — backend tests, backend
types, backend lint, frontend tests, frontend types, frontend lint — so a single command covers the
whole repo.

## 5. Optional — live smoke test

Only when the change touches routing, middleware, or startup; skip it when your test suite already
exercises the app in-process.

```bash
# REPLACE: start your app, hit one endpoint, confirm the status code, stop it
<your run command>
```

Prefer starting the server in a second shell over backgrounding and killing it from inside this
skill — the background-and-kill idiom is not portable.

## 6. Summary report

Report each check with a ✅ or ❌, then an overall verdict:

- One line per check
- **Overall: PASS or FAIL**

For every ❌, include the failing command and the relevant output. Do not fix anything here —
this skill reports; fixing is a separate step.

## Notes

- Keep this skill fast. It runs before every commit; if a step gets slow, that is a signal to fix the
  slow step, not to drop it from the checker.
- A checker that cannot fail is worthless. Once your commands are wired in, break something on
  purpose and confirm this skill reports ❌.
