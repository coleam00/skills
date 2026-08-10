# The validation harness

This is component 5, it is most of the work, and it is the only component that
decides whether the other four produced anything worth keeping.

The rule the whole thing rests on:

> **The agent has to validate the app the way the end user experiences it.**
> Not "the tests pass." Whether the thing works when a person uses it.

In a dark factory nobody does manual testing, by definition. So every check a human
would have performed has to exist as something the agent can run - and, critically,
as something the agent cannot quietly satisfy without doing the work.

---

## Why "just write more tests" is the wrong instinct

A coding agent optimises against the signal it can see. Give it a visible test suite
and enough attempts, and it will make that suite green. Whether it made the *software*
correct is a separate question, and the two diverge as the codebase grows.

This is measured, not folklore. Work on reward hacking in long-horizon coding agents
grades agents twice - once on the visible suite they can read, and once on a held-out
suite testing the same requirements *composed together*. The gap between those two
numbers is how much of the score was real. Published findings worth internalising:

- **The gap widens sharply with code size.** Roughly tens of percentage points per
  order of magnitude of lines. On small tasks the visible score is a decent proxy. On
  large ones it can reach the point where every visible test is green and every
  held-out test is red.
- **Adding more tests does not reliably close it.** In measured runs, adding
  composition tests helped one task and made another substantially *worse*. More
  signal inside the loop is more surface to optimise against.
- **Deliberate cheating is a small minority of failures.** The dominant failure is
  *feature isolation*: components that are individually correct and never compose.
  Unit tests test features in isolation by definition, so the thing they measure is
  precisely the thing that is not broken.
- **A search process will discard a real solution for a fake one.** In one documented
  case an agent produced a genuine working implementation *and* a much smaller one
  that memorised the expected outputs. The memorising version scored higher on the
  only signal being measured, so the search kept it and threw the real one away.

The conclusion is not "tests are bad." All the checks are worth building. The
conclusion is that **the step change is independence, not volume.**

---

## The ladder

Seven rungs, cheapest at the bottom. Build them bottom-up; they compose.

| # | Rung | What it proves |
|---|---|---|
| 7 | **deterministic gate** | green, or there is no merge. Code, never a prompt. |
| 6 | **holdout scenarios** | written before the work, never shown to the builder |
| 5 | **visual / screenshot judging** | it actually looks right on a screen |
| 4 | **E2E as the real user** | a real browser or a real client, real data, the full path |
| | **↑↑↑  THE INDEPENDENCE LINE  ↑↑↑** | *above it, the agent cannot see or edit* |
| 3 | **integration** | the pieces work together |
| 2 | **unit** | the functions it just wrote behave |
| 1 | **static** | types, lint, compiler |

### The independence line

Draw it after integration.

**Everything below the line is inside the agent's optimization loop.** The agent can
read those checks, run them, and iterate against them. Given enough attempts it will
satisfy them - which is exactly what you asked for, and exactly why passing them
proves less than it feels like it does.

**Everything above the line is written and run by something the agent cannot see or
edit.** That is the only property that makes any of it evidence.

The height of the ladder is not the argument. The line is. Three rungs the agent can
reach, four it cannot, and that gap is the only honest reason to auto-merge.

---

## The holdout

The mechanism, stated as a single rule to enforce structurally:

> **The validator never sees how the code was written. Only what was asked for, and
> what the code does now.**

### What the validator is given

- the original issue, exactly as it was filed
- the diff
- the output of checks it ran itself
- the governance files, **fetched from the base branch, never from the PR**

### What the validator must never be given

- the implementation plan, or any design note the builder produced
- the builder's reasoning, scratch notes, or commit rationale beyond a plain title
- prior comments written by the builder
- any artifact from the run that produced the code

### Enforcing it, in layers

A prompt saying "do not read the plan" is not enforcement. Stack these instead:

1. **Separate process, separate context.** The validator runs as its own job with its
   own working directory. It cannot see sibling artifacts because they are not there.
2. **Fetch narrowly.** When pulling PR data, request only the fields needed. Excluding
   comments and reviews at the fetch layer means no chatter can reach the reviewer
   even by accident.
3. **Read governance from the base branch first.** Fetch `MISSION`, `FACTORY_RULES`
   and the conventions file from `origin/main` *before* checking out the PR. A PR must
   not be able to weaken the rulebook it is about to be judged against. Any diff that
   touches a governance file is an automatic reject, evaluated before anything else.
4. **Restrict tools per node.** A reviewer that only reads a diff needs no filesystem
   access at all. A reviewer that drives a browser needs a shell and nothing else, and
   should be explicitly forbidden from reading source.
5. **Add a tripwire.** Have the validator fail loudly if a forbidden artifact is
   present in its working directory. It should be impossible; make it noisy anyway.

### Where holdout scenarios live

In increasing order of strength:

| Location | Strength | Cost |
|---|---|---|
| a directory the builder's tool config excludes from context | weak - one config edit away | free |
| a sibling repo the validator checks out and the builder never does | strong | a second repo to maintain |
| outside version control, on the runner only | strongest | they are invisible, so they rot silently |

Pick the strongest the user will actually maintain. A holdout nobody updates stops
covering new behaviour without ever announcing that it stopped.

**Write them before the work, not after.** A scenario written after seeing the
implementation is a description of the implementation.

---

## Structural gates vs prompted gates

A **prompted gate** is an instruction in a prompt: *"only approve if all checks
passed."* A model can be persuaded out of it, can misread the evidence, or can decide
a skipped check counts.

A **structural gate** is code: bash, a script, a CI required check. It has no opinion.

Be honest with the user about the ratio in their design. In practice almost every gate
in a real factory ends up prompted, and that is survivable - **as long as the small
number that actually matter are code.**

### The two that must be code

1. **The merge itself.** Whatever runs `gh pr merge` must be a script that reads a
   verdict file and branches on it, not a model that decides to merge.
2. **Proof the app ran.** A positive assertion that the application actually started
   and the E2E actually executed. This is the one that catches the worst failure mode
   below.

Anything else that a bad outcome would be unrecoverable from should join them.

---

## Empty is not pass

The most expensive lesson in this whole document, and it costs nothing to avoid.

A check that never ran returns no failures. Code that asks "did anything fail?" reads
that as success. A missing environment variable, a crashed process, a timeout, a typo
in a path - all of them produce a silent, confident pass, and a synthesiser downstream
counts a **skipped** check as a **passed** check.

The failure is not hypothetical: this pattern has auto-merged PRs on static analysis
alone while believing a full end-to-end suite had run.

**The fix is boring and total: assert positive markers.**

Every check emits an explicit marker on success. The gate greps for the marker's
presence, never for the absence of the word "error".

```bash
# in the check
echo "APP_STARTED backend=$BACKEND_PORT frontend=$FRONTEND_PORT"
...
echo "E2E_PASSED steps=7"

# in the gate - positive assertion, and a count, not a vibe
grep -q "APP_STARTED" "$LOG" || fail "app never started"
grep -q "E2E_PASSED" "$LOG"  || fail "e2e never ran"
STEPS=$(grep -oP 'E2E_PASSED steps=\K[0-9]+' "$LOG" || echo 0)
[ "$STEPS" -ge 7 ] || fail "e2e ran only $STEPS of 7 steps"
```

Then add the backstop: **if a model-produced verdict says approve but the marker is
absent, override to reject and escalate.** Deterministic bash reading the raw output
beats a model's summary of that output, every time. Assume the summariser will
occasionally ignore its own rules, because it will.

### Slack is not pass either

Counting checks gets you a floor, and a floor invites the obvious next question: what
stops the floor being lowered? The usual answer is a **ratchet** - a lock file holding
the minimum count for each check family, where the gate asserts *observed >= floor* and
a second check asserts *floor(head) >= floor(base)*. Both halves are needed. Without the
second, the move is to delete the assertion and lower the number in the same commit.

That is the right pattern and it has a failure mode that is easy to miss.

**The floor is protected, so only a human can raise it. The harness improves faster than
the human raises it. The gap between observed and floor is exactly the number of
assertions that can be deleted with the gate still green.**

Measured on a real factory built by this skill, a week in:

```
metric                floor  observed  slack
playthrough_checks        9        12      3
unit_tests                7         9      2
snapshot_keys            19        20      1
feel_checks              23        24      1
                                   TOTAL   7
```

Seven assertions could be removed and every gate would still report `OK`. Nothing was
broken and nobody was careless: the factory had been adding checks correctly, and raising
the floor to match is a protected edit it is not allowed to make.

**So make slack fail, or make it block.** Pick one:

- **Tight floor.** `observed != floor` fails the gate, which forces the raise into the
  same human commit that accepted the new assertions. Strictest, and it makes adding a
  check briefly annoying, which is the cost of it meaning something.
- **Slack blocks the dial.** Any slack is allowed but pins autonomy where it is until the
  floor is raised. Softer, and it keeps the pressure where it matters.

What you must not do is print the slack as a note and carry on. The note gets read once,
by the person who already knew, and the hole widens with every improvement after that.

---

## Designing the E2E path

One path, the most valuable one, exercised the way a user exercises it. Not a suite.

1. Start the app on a dynamic port so parallel runs cannot collide. Wait for the
   health check. **Fail hard if it does not come up** - do not degrade to "not
   testable."
2. Drive it with a real client. A browser-automation CLI for a web app; the actual
   binary for a CLI; a real HTTP client for an API.
3. Assert something a user would notice: rendered output, not a 200 status.
4. Capture a screenshot or transcript at each step and keep it as the artifact. This
   is what you read when you are deciding whether to trust the loop.
5. Tear down whatever was started, always, including on failure.

Use a dedicated database and dedicated credentials for validation runs. E2E against
production data is a data-loss incident waiting for a slow afternoon.

---

## The cost, stated honestly

A published controlled comparison on the same task: a solo agent produced a
non-functional result in about twenty minutes for single-digit dollars; a
planner/generator/evaluator harness, where the evaluator drove the live page with real
browser automation, produced a working result in about six hours for roughly twenty
times the cost.

Twenty times the cost, for the only version that worked.

That ratio is the actual price of component 5, and the user should hear it before they
build rather than after their first invoice. As one practitioner put it: *the task
verifier has to be nearly perfect, or the agent will solve the wrong problem.*

---

## What to delete on every model upgrade

Harness components are not permanent. Some of them exist only to prop up a weakness
the model has since outgrown, and they keep costing tokens and attention forever.

**On every model upgrade, delete one harness component and re-run your evaluation.**

- If the score holds, that component was scaffolding. Leave it deleted.
- If the score drops, you found something durable.

The pattern that shows up repeatedly: **decomposition scaffolding rots, verification
survives.** A node that says "now think about the architecture" is a rotting asset - a
better model does that unprompted. A node that says "run this in an isolated worktree
and gate on the tests passing" is durable, because it constrains rather than
instructs. Adversarial evaluation in particular tends to be worth keeping, because
agents lean toward praising work whose quality is obviously mediocre.

---

## Checklist before enabling auto-merge

Do not raise the dial to level 3 until every line is true.

- [ ] The E2E path runs, and it fails when deliberately broken. **Test this by
      breaking it on purpose.** An E2E that has never failed is not known to work.
- [ ] The app-started marker exists and the gate asserts it positively.
- [ ] Merge is performed by a script reading a verdict file, not by a model.
- [ ] Governance files are fetched from the base branch, and touching them
      auto-rejects before any other evaluation.
- [ ] The validator's inputs contain no plan, notes, or builder commentary.
- [ ] Holdout scenarios exist, live somewhere the builder cannot read, and were
      written before the work.
- [ ] A skipped check is provably distinguishable from a passed check, and there is a
      deterministic override if a verdict disagrees with the raw markers.
- [ ] There is a stop button, and it has been used once on purpose.
