---
name: piv-fix-review-findings
description: Triage code-review findings (manual or AI), fix the ones you choose one at a time with tests, defer/log the rest, then validate — and if the work is on a PR, commit and push so the PR reflects the fixes. Use after a review has produced a list of issues or a review file.
argument-hint: "[code-review-file-or-issues] [scope / what to fix now vs defer]"
arguments: [review, scope]
---

# Fix Review Findings

A review produced findings — but a review is **input, not a work order.** You decide what happens to each one.

Code-review (file or description of issues): $review

Direction / scope (what to fix now vs defer): $scope

If the Code-review is a file, **read the entire file first** so you understand every finding before triaging.

## 1. Triage first (the human's call)

Sort the findings before touching code. Honor any direction in the scope argument; if it's unclear, surface the
findings grouped and **ask** rather than fixing everything by default:

- **Fix now (this PR)** — real, in-scope, belongs with this change.
- **Defer / log as an issue** — real but later; don't bloat this PR. **Create a tracker issue** (or note it) instead
  of fixing it here.
- **Needs a human look / manual test** — anything you should inspect or test by hand before trusting it. Flag it,
  don't silently auto-fix.
- **Noise / won't-fix** — say why, then drop it.

Don't let the reviewer dictate scope — "real, but later" is a valid and common call; a clean small PR beats a
sprawling one.

## 2. Fix the "fix now" set — one at a time

For each:
1. Explain what was wrong.
2. Make the fix.
3. Create and run a test that proves it.

## 3. Validate

Run the `piv-validate` skill to finalize the fixes.

## 4. If operating on a PR — commit and push

If these fixes are on a PR branch, **commit them (use `piv-commit`) and push** so the PR reflects the fixes and the
review can re-run on the updated PR. If nothing was fixed (everything deferred), there's nothing to push — just make
sure the deferred items are logged as issues.

## Output

A short report: what was **fixed** (with its test), what was **deferred/logged** (with issue refs), what needs a
**manual look/test** — and, if on a PR, the **pushed commit** + confirmation the PR is updated.
