---
name: piv-review-pr
description: Full pull-request review — fetch the PR, run the project's validation, review the diff with fresh eyes (dispatching the code-reviewer agent), categorize issues by severity, post the review to GitHub (approve / request-changes / comment), and save a report. The agentic gate that runs on an open PR before a human approves. Use after piv-create-pr.
argument-hint: "<pr-number | pr-url | branch> [--approve | --request-changes]"
---

# Review PR: The Agentic Gate Before the Human

**Input**: $ARGUMENTS

The point of this skill is **fresh eyes**: it reviews the PR in a clean context — *not* the context that wrote
the code — and can hand the deep analysis to the **`code-reviewer` agent**, which is the whole reason the review
catches what the author's own context rationalizes away. It posts its verdict on the PR, then a **human** makes
the final call.

## Phase 1 — Fetch the PR

Resolve the input to a PR number (a number, a URL, or a branch via
`gh pr list --head <branch> --json number -q '.[0].number'`). Then:

```bash
gh pr view {N} --json number,title,body,author,headRefName,baseRefName,state,additions,deletions,changedFiles,files
gh pr diff {N}
gh pr checkout {N}
```

State guard: `MERGED`/`CLOSED` → stop ("nothing to review"); `DRAFT` → review direction, don't approve/block.

## Phase 2 — Load the context (so you review against the right bar)

- **`CLAUDE.md`** + any `.claude/references/` — the project's standards are the review rubric.
- **The implementation report** (if `piv-implement` wrote one — `.claude/reports/*{branch}*`) + its plan: read the
  **documented deviations**. A documented deviation is an *intentional decision*, **not** an issue — only flag
  *undocumented* divergences. (No report? Review normally and note its absence.)
- The PR's own intent (title/body): what problem it claims to solve.

## Phase 3 — Run validation

Run the project's real suite (the **`piv-validate`** skill, or the plan's validation commands) — tests, type-check,
lint, build. Capture pass/fail + counts. A red suite is a finding in itself.

## Phase 4 — Review the diff (dispatch the code-reviewer agent)

Hand the deep pass to the **`code-reviewer` agent** (`.claude/agents/code-reviewer.md`) — it reviews against the
project's standards and reports **high-confidence issues only**. Read every changed file *in full* (not just the
diff) for context. Cover: correctness · type safety · pattern/standards compliance · security · performance ·
tests present · maintainability.

**Categorize every issue by severity:**

| Severity | Meaning |
|----------|---------|
| **Critical** | Blocking — security, data loss, crashes |
| **High** | Should fix before merge — type-safety holes, missing error handling, logic errors |
| **Medium** | Pattern inconsistencies, missing edge cases, *undocumented* deviations |
| **Low** | Suggestions, minor polish |

Acknowledge what's done well, too — review is constructive, not just a defect list.

## Phase 5 — Decide

- **Approve** — no critical/high issues, validation passes, matches intent.
- **Request changes** — high issues, or fixable validation failures, or undocumented pattern violations.
- **Block** (request-changes, strongly) — critical security/data issues, or wrong fundamental approach.
- Honor an explicit `--approve` / `--request-changes` flag, but never approve over an unresolved critical issue.

## Phase 6 — Post to GitHub + save the report

Write the report to `.claude/code-reviews/pr-{N}-review.md` (summary · issues by severity with `file:line` + fix ·
validation table · what's good · recommendation). Then post it:

```bash
# approve
gh pr review {N} --approve --body-file .claude/code-reviews/pr-{N}-review.md
# request changes
gh pr review {N} --request-changes --body-file .claude/code-reviews/pr-{N}-review.md
# or just comment (draft PRs / advisory)
gh pr comment {N} --body-file .claude/code-reviews/pr-{N}-review.md
```

## Output + hand off

Print: PR number/URL · issue counts by severity · validation results · the recommendation. Then hand off:
**"Posted on the PR. A human now reviews the code + this review and merges."** If there are issues, the natural
next step is **`piv-fix-review-findings`** on the report, then re-run validation.

## Notes

- **Fresh eyes is the whole point** — run this in a clean context (or let the `code-reviewer` agent be the clean
  context). Don't review with the session that wrote the code; it rationalizes instead of scrutinizing.
- This is the *agentic* gate; it does not replace the human — it gives the human a validated, triaged PR to
  approve. Going deeper (multiple review agents, tuning the reviewer to your stack, the validation pyramid) is
  the code-review-as-a-component material later in the course.
