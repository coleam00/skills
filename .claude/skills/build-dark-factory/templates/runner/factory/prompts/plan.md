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

# Node 2: plan

Run the `piv-plan-implementation` skill for `{{issue}}`.

This is the step you actually read today. Everything downstream
inherits whatever this gets wrong, which is why this node holds the premium model and why
it is the last node that will ever go fully unattended.

## Inputs

- the issue body - this is the ticket
- `.factory/runs/{{run}}/priming.md` - the priming from node 1
- `MISSION.md` - scope, invariants, and the definition of done
- `docs/<YOUR-PRODUCT>.prd.md` - the PRD `MISSION.md` was compressed from. Read it when the
  issue touches *why* something is the way it is; `MISSION.md` is the contract but the
  PRD is the reasoning, and a plan that contradicts the reasoning usually satisfies the
  contract in a way nobody wanted.
- `CLAUDE.md` - conventions
- `FACTORY_RULES.md` - how this runs unattended

## Inherit, don't re-decide

`MISSION.md`'s invariants and the determinism contract in `FACTORY_RULES.md` §5.1
are **already decided**. Plan within them. A plan that proposes changing one has
misunderstood the issue: say so and escalate rather than planning the change.

## You cannot run anything, and the implement node nearly cannot either

**You have `Read`, `Glob`, `Grep` and `Write`. No shell at all.** Do not plan to measure
something yourself; you will be refused, and refusal here is silent - the request goes to a
human who is not there. State the measurement as the implement node's first task instead.

**The implement node has** `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash(python -c:*)` for
measurement, and `Bash({{quick}})`. It has no `git`, no `gh`, and no
other shell. A task that needs anything else does not fail loudly: the node asks for
approval, nobody answers, and it stops having changed nothing. A whole lap was lost that
way - write no task the next node cannot perform.

## Write the plan to `{{rundir}}/plan.md`

Standard `piv-plan-implementation` structure. Four sections matter more here than they do
interactively, because no human reads this before it executes:

**Out of scope / non-goals.** Name what a reasonable reader might assume is included and
is not. Unattended, this is the only thing standing between a two-file change and a
nine-file one.

**Every task has an executable validation command.** Not "verify it works". The command.
The implement node runs these and has nothing else to go on.

**The observability task.** If this change introduces any value that moves as a
consequence of play, exposing it on the state readout and asserting it in the playthrough is
**part of this change**, not follow-up work (`FACTORY_RULES.md` §9). Write it as a task.
A plan that adds a dynamic value without adding its observable is incomplete and the
gate will not catch it - this is the one hole in the harness that only a plan can close.

**The harness task, where one is warranted.** If this change makes a new class of bug
possible, add a deliberate defect to `<THE-MUTATION-SET>` covering it. Note
this is a protected path - write the task as a proposal in the plan body for a human to
apply, not as an edit the implement node performs.

## Escalate rather than guess

Write the reason to `{{rundir}}/ESCALATE` and stop if the plan would require:

- **any locked value** - every threshold in `.factory/locks/*.json` is TBD until
  calibration (any `MISSION.md` open question). Never pick a number, however reasonable.
- an answer to any other MISSION open question
- touching a protected file (`FACTORY_RULES.md` §5)
- weakening any assertion, tolerance, sample size, or mutation (§2.1)

You cannot set the issue's state yourself - you have no `gh` and no state tool. Writing
that file is the escalation: `factory/run-workflow.sh` sees it, moves the issue to
`needs-human` through the transition table, and stops the run before anything is built.

Escalating costs one message. Guessing costs a merged change built on an invented
constant that nobody will find until it is load-bearing.

## Report

Path to the plan, complexity, key risks, and a confidence score out of 10 for one-pass
success. Below 6, escalate instead - a plan you do not believe in is cheaper to abandon
here than after three fix attempts.
