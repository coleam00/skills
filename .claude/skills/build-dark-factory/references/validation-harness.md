# The validation harness

This is component 5, it is most of the work, and it is the only component that
decides whether the other four produced anything worth keeping.

---

## What the runner expects you to build

Read this first if you are using `templates/runner/`. Both people who built a factory from
this skill inferred the whole layout from one default string in `config.sh`, and one of
them had to read the runner's source to work out how a check's output reaches the gate.
Neither should have had to.

**`templates/harness/` is a working skeleton of all of this** - `ci.py`, `appproc.py` and
`e2e.py`. Copy it, run it, then delete every assertion in `e2e.py` and write yours. It
satisfies the contract below out of the box, so you are editing something that already
passes rather than debugging plumbing while also deciding what "working" means.

**The contract is four things.**

**1. A single entrypoint, named in `config.sh`.**

```bash
FACTORY_VALIDATE_CMD="${FACTORY_VALIDATE_CMD:-python harness/ci.py}"
FACTORY_VALIDATE_QUICK="${FACTORY_VALIDATE_QUICK:-python harness/ci.py --quick}"
```

`harness/ci.py` is a **convention, not a requirement** - point it at `make check`,
`npm run gate`, `./scripts/validate.sh`, anything. What matters is that one command runs
the whole gate. The layout that goes with the convention:

```
harness/          the checks. The builder CAN read and run these
  ci.py           the entrypoint: runs everything, prints markers, exits non-zero on failure
.factory/
  holdout/        assertions the builder is BLOCKED from reading (--disallowedTools)
  locks/          thresholds and floors a human set. Protected
  runs/           per-run artifacts. Gitignored
```

**2. It must print a positive marker for every check family that RAN**, and the markers
must match `FACTORY_REQUIRED_MARKERS` in `config.sh`. `APP_STARTED` and `E2E_PASSED` are
not negotiable. Counts, not just names:

```
APP_STARTED port=8080
E2E_PASSED steps=11
HOLDOUT_PASSED scenarios=2 assertions=30
MUTATIONS_TOTAL=7
MUTATIONS_CAUGHT=7
GATE_OK
```

**3. It must exit non-zero when the software is broken.** The gate reads the markers, but
the exit code is what the implement node's own `--quick` run sees.

**4. The append contract, which is the one that bites.** The runner writes `guard.py`'s
output to the run's `gate.log` and then **appends** your validate command's output to the
same file. `gate.sh` asserts every required marker against that combined log. Two
consequences:

- `PROTECTED_OK` comes from the guard, not from you. Do not print it yourself.
- If your entrypoint truncates or redirects over that log rather than writing to stdout,
  the guard's markers vanish and every gate fails for a reason that has nothing to do with
  your code. **Print to stdout and let the runner do the plumbing.**

**`--quick` is a real obligation, not a nicety.** The implement node runs it on itself
while it works, so it must be fast and it must be a strict subset - never checks the full
run does not have. It is inside the agent's optimisation loop by definition, which is
exactly why the full gate re-runs everything independently afterwards and why nothing
downstream trusts what `--quick` said.

**Do not let the builder edit the harness.** `factory/guard.py` seeds the mutation set on
the protected list, but `ci.py` *is* the definition of "works" - a builder that can edit
its own judge can make any claim true. Protect `harness/**`, and route legitimate coverage
growth to your normal test directory instead.

---

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
| 5 | **visual / screenshot judging** *(not scaffolded — you build it)* | it actually looks right on a screen |
| 4 | **E2E as the real user** | a real browser or a real client, real data, the full path |
| | **↑↑↑  THE INDEPENDENCE LINE  ↑↑↑** | *above it, the agent cannot see or edit* |
| 3 | **integration** | the pieces work together |
| 2 | **unit** | the functions it just wrote behave |
| 1 | **static** | types, lint, compiler |

### The reachability constraint, and it is an architecture decision

**The harness reaches software exactly three ways**: `http` (a server), `cli` (a command),
`library` (imported and called). See `templates/harness/appproc.py`.

A rendered window, a game loop, a canvas, a native UI is **none of them**. So this is not
a preference about clean architecture, it is a precondition: **the rules have to live
behind a headless, scriptable surface an E2E can drive.** Simulation apart from rendering,
domain apart from view. If the logic only exists inside engine nodes and a render loop
there is nothing to assert, and the factory cannot run at level 3 — not because the skill
is limited but because nothing can check the work.

On a **greenfield** build, say this before any code exists. It is nearly free then and it
is a rewrite afterwards. On a brownfield one, it is the first thing to find out, because
the answer decides whether component 5 is additive or a refactor.

**`templates/harness/ci.py` implements 1, 2, 4, 6 and 7. Rung 5 is not scaffolded**, and
saying so matters: a doc that lists a rung the scaffold does not ship reads as "you have
this". You do not. Screenshots an `e2e.py` captures are artifacts nobody looks at until
something is written to look at them. Build rung 5 if the product has a screen worth
judging, and treat the row above as a thing to do rather than a thing you have. See the
frontend section of `templates/harness/README.md` for what that costs.

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

### What the factory says to humans is an output, and outputs need assertions too

Everything above is about checks. The factory also produces **artifacts for people**: the
comment explaining a rejection, the PR body, the escalation note. Those get graded by
nobody, and they fail silently.

Observed on a real run. Triage rejected an out-of-scope issue perfectly: correct verdict,
correct label, issue closed not-planned, and a written rejection citing two rules by
number with an appeal path for the filer. What actually reached the filer was two
characters:

```
@-
```

The reasoning had been assembled in a shell pipeline instead of going through the
factory's own comment helper, and on Windows the pipeline collapsed to a literal `@-`.
Every state transition was right. The `gh` call exited 0. The run reported success. The
only thing lost was the entire explanation, which is the part a human was ever going to
read.

Two rules come out of it, and the second is the general one:

- **Route every human-facing write through one helper, and make the helper the only way.**
  A hand-rolled `gh issue comment` in a node is the same class of mistake as a hand-rolled
  merge: it works until quoting, encoding, or a newline eats it.
- **Assert the artifact after writing it, not before.** Read the comment back and check it
  contains the rule citation you meant to send. `exit 0` from the tool that posted it
  proves the API call succeeded, not that it carried anything. This is exactly
  empty-is-not-pass, applied to output rather than to checks, and it is easy to miss
  because output feels like a side effect rather than a result.

The tell that this class of bug is present: **a step whose success is measured by the
transition it caused rather than by the thing it produced.**

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

Measured on a real factory built by this skill. Seven assertions could be removed and
every gate would still report `OK`. Nothing was broken and nobody was careless: the
factory had been adding checks correctly, and raising the floor to match is a protected
edit it is not allowed to make.

**Then the same factory was measured again after one round of harness work**, and this is
the part that matters:

```
metric               floor  observed  slack      floor  observed  slack
                       ---- before ----            ---- after -----
playthrough_checks       9        12      3          9        12      3
unit_tests               7         9      2          7         9      2
feel_checks             23        24      1         23        24      1
legibility_frames        -         -      -         60        87     27
                              TOTAL       7                  TOTAL   33
```

**The hole grew from 7 to 33 in one cycle**, and it grew *because the harness got better*.
A new check family arrived running 87 frames against a floor of 60, and every assertion
of that surplus is deletable. Improvement widens the gap, which is the opposite of what a
ratchet is supposed to do.

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
