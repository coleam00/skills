---
name: worktree-create
description: Create one or more git worktrees for parallel development, each on its own branch with gitignored config copied in, dependencies installed, and a health check, by fanning out a setup subagent per worktree. Use when starting isolated parallel work, running several PIV loops at once, or when the user says "set up worktrees", "create a worktree", "spin up parallel branches", or invokes /worktree-create.
argument-hint: "[branch ...]  (one or more branch names; blank = ask)"
---

# Worktree Create

Stand up **any number** of isolated git worktrees from a list of branches — each created off the right base, given
its gitignored config, its dependencies, and a health check — by fanning out one setup subagent per worktree so
they run in parallel. The per-worktree work is app-agnostic and **detected from the repo**, never hardcoded.

## Input

`$ARGUMENTS` is the list of branches to create.

- **None given** → ask which branches to create (or offer to derive them from the tickets in play). Don't guess.
- **One** → set up a single worktree inline (a fan-out of one is unnecessary).
- **Two or more** → fan out one subagent per branch, in parallel.

## Detect the project setup ONCE, before fanning out

Read `references/worktree-setup.md` — it is the general checklist of everything a fresh worktree needs plus how to
detect each piece. Determine from **this** repo (not from assumptions), one time:

- the **install command(s)** (monorepo → one per package),
- the **gitignored env/config files to copy** (or the repo's `.worktreeinclude`),
- the **verification/health-check command** (a health endpoint if the app exposes one, else a build/test smoke —
  prefer whatever CI runs),
- a **base port**, only if the health check starts a service.

Pick a worktree root (`worktrees/<branch>`, gitignored) and, if services get started, assign each worktree a
distinct port = `base + index` so parallel servers don't collide.

## Fan out one setup subagent per branch (parallel)

Spawn all subagents at once with the Task tool. Give every subagent the same prompt, substituting only `BRANCH`
and `PORT`:

```
Set up a git worktree for branch: BRANCH   (assigned port: PORT, only relevant if you start a service)

Follow the checklist in .claude/skills/worktree-create/references/worktree-setup.md. Concretely:
1. Create the worktree off the base branch:  git worktree add worktrees/BRANCH -b BRANCH
2. Copy the gitignored config/secrets the project needs into worktrees/BRANCH
   (the env/config files detected for this repo; verify each with `git check-ignore` before copying).
3. Install dependencies with the project's detected package manager (every package, for a monorepo).
4. Run any generate/build step the app needs to boot (skip if none).
5. Verify: run the detected health check (start + hit the health endpoint on PORT if there is one,
   else a build/typecheck/test smoke). Then stop any server you started.

Report exactly: worktree path · branch · deps installed (yes/no) · health check (PASS/FAIL) · any errors.
```

Fill the detected commands (install, env-file list, health check) into the template. For a single branch, run the
steps directly instead of spawning.

## Aggregate and report

Collect the reports and print a per-worktree summary (path · branch · deps · health · port), a combined
`N worktree(s) ready` line, the next step (open each worktree / start a PIV loop in it), and the cleanup reminder:
`git worktree remove worktrees/<branch>` once a branch is merged.

If any worktree failed its health check, surface it clearly and do **not** report it ready.

## Resources

- `references/worktree-setup.md` — the general, app-agnostic checklist of everything a fresh worktree needs, and
  how to detect each piece per project. Read it before detecting the setup.
