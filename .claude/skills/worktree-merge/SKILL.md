---
name: worktree-merge
description: Integrate any number of feature branches from parallel worktrees through one safe integration branch, validating after each merge and running the project's full check suite before touching the main line. Use when parallel worktree development is done and the branches need to be merged, or when the user says "merge my worktrees", "integrate these branches", or invokes /worktree-merge.
argument-hint: "[branch ...]  (two or more branch names; blank = ask)"
---

# Worktree Merge

Integrate **any number** of feature branches into your working branch through a single throwaway integration
branch, so nothing lands on the main line until every branch is merged and the whole suite passes. Validation
commands are **detected from the repo**, never assumed.

## Input

`$ARGUMENTS` is the list of branches to integrate.

- **Fewer than two** → ask which branches to integrate. Don't guess.
- **Two or more** → integrate them in the given order.

## Detect the validation commands ONCE

Find the commands that prove this project works, preferring **what CI already runs**: read `.github/workflows/*`, a
`Makefile`, or the manifest's test/lint scripts, and reuse those exact commands (test runner, type checker,
linter). Do not hardcode `pytest`/`mypy`/`pyright` — use whatever this repo actually uses.

## Steps

1. **Preconditions.** Confirm you're at the repository root, not inside `worktrees/`
   (`[[ $(pwd) =~ /worktrees/ ]]` → error). Store the current branch. Verify every branch in the list exists
   (`git rev-parse --verify <branch>`). Abort early with a clear message if any check fails.

2. **Create one integration branch** off the current branch, named for the set (e.g. `integration-<first>`, with a
   short suffix if there are several — keep it filesystem-safe). This is where merges are tested; the main line
   stays untouched until the end.

3. **Merge each branch in order**, `--no-ff`. After **each** merge, run the detected **test** command so a break
   is localized to the branch that caused it.
   - **On conflict:** stop, name the conflicting branch and files, and give resolution steps (resolve →
     `git add` → `git commit` → re-run the skill). Don't attempt automatic resolution.
   - **On test failure:** stop, report which tests failed, and give the rollback (`git checkout <original>` →
     `git branch -D <integration>`).

4. **Full validation** once all branches are merged: run the project's complete detected suite (tests + type
   checks + lint). Any failure → report it and roll back; nothing reaches the main line red.

5. **Merge the integration branch into the original branch** (`--no-ff`), then delete the integration branch.

6. **Offer cleanup** with AskUserQuestion: remove the N worktrees and delete their feature branches, or keep them.
   On yes, for each branch: `git worktree remove worktrees/<branch>` and `git branch -d <branch>`.

## Report

- **Success:** the integration branch used, each branch merged (with its post-merge test result), the full
  validation result, the merge into `<original>`, and cleanup status (worktrees kept or removed, with the manual
  cleanup commands if kept).
- **Failure:** the step and branch that failed, the current branch state, and exact rollback commands
  (`git checkout <original>` → `git branch -D <integration>`), plus how to continue after fixing (re-run with the
  same branch list).

## Notes

- `--no-ff` preserves each feature branch's history.
- The integration branch is disposable — the original branch only moves after every merge and the full suite pass.
- Prefer opening a PR per branch (the reviewed path from V9) when you're on a team; this skill is for fast local
  integration when you own the merge.
