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

# Node 3: implement

Run the `piv-implement` skill against `{{rundir}}/plan.md`.

You skim this step at best, so it goes autonomous first. Work the plan task by task,
in order, running each task's validation command as you go.

## Absolute prohibitions (`FACTORY_RULES.md` §2)

1. **Never modify a test, assertion, tolerance, sample size or lock to make something
   pass.** Fix the source. If a check is genuinely wrong, say so in the report and stop -
   that is a `needs-human` escalation, not a change you make. Most of the protected paths
   are unreachable from this node by construction; this rule covers the rest.
2. **Never touch a protected file** - governance, `.factory/locks/**`,
   `.factory/holdout/**`, `factory/**`, `<THE-MUTATION-SET>`, `docs/<YOUR-PRODUCT>.prd.md`.
3. **Never add a dependency.** the core module's dependency policy is in `CLAUDE.md`. A
   dependency in the simulation is a dependency in every soak run.
4. **Never build beyond what the plan asked for.** No opportunistic refactors, no "while
   I was in here". The plan's non-goals section is binding.
5. **Never commit a binary asset**, including a placeholder. Art is text or code
   (<THE-INVARIANT-THAT-FORBIDS-IT>, <THE-OUT-OF-SCOPE-ENTRY>).
6. **Stay under 500 changed lines.** Over the cap, stop and report - the work needs
   splitting, and something nobody could review even in principle is not shippable here.

## The determinism contract

The core module is editable. Its contract is not (`FACTORY_RULES.md` §5.1):

- randomness comes from the threaded `Rng`, never from `random`, never from a global
- no wall-clock reads, ever
- `step(world, input)` advances exactly one tick, and takes no default arguments
- the state readout may **gain** keys freely. It may never lose one.

`<THE-CONTRACT-CHECK>` enforces all of this structurally. It will catch you; the point of
reading it here is that finding out now is cheaper than finding out in validation.

## Observability ships with the change

If this change introduces a value that moves as a consequence of use, expose it on
the state readout and assert it in `<THE-BEHAVIOURAL-CHECK>` **in this change**. A value that
moves and is not observable cannot be proven to work by anybody, ever, and in a repo that
merges without review that means it cannot be built (<THE-OBSERVABILITY-RULE>).

Adding an assertion is always in scope and needs no justification (<THE-HARNESS-IS-ONE-WAY-RULE>).
If you added one, raise the matching count in `.factory/locks/floor.json` - that file is
protected, so write the new value into your report for a human to apply rather than editing
it. The gate will pass either way; the ratchet only requires observed ≥ floor.

## Validate as you go

After each task, run **exactly this command, verbatim**:

```
{{quick}}
```

It is the only one on your allowlist, so any other way of running the tests is denied and
your work goes unchecked until the validator sees it. That is contract, unit and
the end-to-end path - fast, and enough to catch a mistake while you still remember
making it.

**Do not run the full gate.** It belongs to the validator. A builder that can run the gate
it is judged by will iterate against the gate rather than against the problem, and the two
diverge exactly when it matters.

## Report

Write `{{rundir}}/report.md`: what was built, tasks completed, tests
added, validation results, **deviations from the plan and why**, and any floor raise a human
should apply. Deviations are the reviewer's signal of intent - a documented one is a
decision, an undocumented one is a bug.
