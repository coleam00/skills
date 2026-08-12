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

# Node 1: prime

Run the `prime-codebase` skill, scoped to what `{{issue}}` actually touches.

You do not skip this step and neither does the factory. The plan node is the expensive
one; feeding it a cold read of the repository is how a premium model gets spent
re-deriving what a cheap one could have handed it.

## Read

- `git ls-files`, `git log -10 --oneline`, `git status`
- `MISSION.md`, `CLAUDE.md`, `README.md`
- `<THE-CORE-MODULE>` in full - the bottom of your dependency graph, the thing
  everything else reads
- the harness modules relevant to the issue's capability area
- `.factory/locks/*.json` - the thresholds a human has set, which the plan must stay inside

## Report to `{{rundir}}/priming.md`

Keep it scannable. Cover:

- **What the issue touches**: the capability area from `MISSION.md`, and the files
- **Existing patterns to mirror**, with `file:line`. Naming, how state threads through
  the step function, how checks are written and counted
- **The observability surface**: which keys the state readout already exposes, and which of
  them the issue's area depends on
- **Current gate counts**: from `.factory/runs/last.json`, so the plan knows what the
  ratchet floor is
- **Anything that looks like it is already broken** in the area, distinct from the issue.
  Do not fix it. Name it, and note whether it is worth a separate issue.

You are read-only. If you find yourself wanting to edit something, that is a finding for
the report, not an action.
