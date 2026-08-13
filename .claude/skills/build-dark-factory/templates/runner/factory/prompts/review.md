<!--
  THIS PROMPT IS THE INTERVIEW'S OUTPUT, not machinery. It is the one file in the runner
  you are MEANT to rewrite.

  The factory's whole claim is that it runs YOUR process with the approvals removed. So
  these seven prompts should be recognisably your planning step, your implementation
  step, your review step - loading the skills, rules files and MCP servers you already
  load at each one. What is here is a worked example from a real factory, kept because
  the shape is worth stealing; the words are not.

  Every <ANGLE-BRACKET> below is a decision from the interview. factory_doctor reports a
  prompt that still contains one.
-->

# Node 5: review, and open the PR record

Run the `piv-review-changes` skill over the diff, then write the PR record.

You rubber-stamp this when the gate is green and the diff is small, which is most of the
time - so it goes autonomous early. It is still worth running, because it is the only node
that reads the diff *as code* rather than as a set of markers.

## Review

`git diff {{base}}...{{branch}}`, then read each changed file in full - not just the hunks. Look for:

- **Logic errors**: off-by-one, inverted conditionals, a branch that cannot be reached
- **Determinism breaks** that the AST check cannot see: iteration over a set, a dict
  ordering assumption, an `id()` comparison, mutation during iteration. `<THE-CONTRACT-CHECK>`
  catches imports and signatures; it cannot catch these, and they are the ones that make a
  soak flake one run in fifty
- **Scope**: anything here unrelated to the issue
- **Conventions** (`CLAUDE.md`): threaded state, ticks not seconds, no debug output in the core module,
  checks named as a player would describe them
- **Observability**: a new dynamic value without a the state readout key is a block

Governance files are read from the **base branch**. A change is not judged against a
rulebook it just edited.

## Then write `{{prfile}}`

One file, at exactly that path. On the GitHub backend this becomes the body of a real
pull request, opened by `factory/run-workflow.sh` after you exit - you do not open it and
you are not given `gh`. Same rule as the merge: a model's only output is a record, and
code decides what happens to it.

```markdown
---
issue: {{issue_ref}}
title: <the change, in the imperative, as CLAUDE.md wants a commit subject>
branch: {{branch}}
state: open
attempts: 0
---

## What changed
<2-4 sentences, in terms of the game, not the files>

## Files
<path - why it changed>

## Gate
<the counts from .factory/runs/last.json: static, unit, e2e steps,
 balance, mutations caught/total>

## Review findings
<severity / file:line / what and why - or "none">

## Floor raise to apply
<if assertions were added, the new .factory/locks/floor.json values for a human to commit,
 since that file is protected - or "none">
```

`state: open` hands it to the independent validator. **Do not merge.** Your only
merge-related output is this record; `factory/gate.sh` and `factory/merge.sh` decide, and
they re-check the markers themselves rather than trusting this file.

The front matter is read by the script that opens the PR: `title` becomes the PR title and
everything below the second `---` becomes the PR body. Keep the body readable by a human
who has not seen the issue.
