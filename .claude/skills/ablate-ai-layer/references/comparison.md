# Grading the runs

The hard part of an ablation is not deleting things. It is seeing what you lost.

**Every run will look fine.** The stripped agent does not produce broken code. It
produces code that compiles, reads well, and would pass review. The difference is
in what it did not know to do.

So never ask "did the stripped run fail?" It did not. Grade rule by rule instead.

---

## Grade per rule, not per diff

Diffing one control run against one stripped run is the obvious move and a bad one.
Two independent implementations of the same task differ in a hundred irrelevant
ways, and the differences that matter drown in the ones that do not.

Instead, turn the always-loaded files into a numbered checklist of **testable
claims**, then judge every run against every claim.

A testable rule names something you can see in a diff:

- "Every public function is decorated with `@tracked`" is testable.
- "Write clean, maintainable code" is not. Mark it `unfalsifiable` and move on.
  It was never going to survive an experiment, which is itself worth reporting.

For each (run, rule) pair record exactly one of:

| Verdict | Meaning |
|---|---|
| `followed` | the diff visibly complies |
| `violated` | the diff visibly breaks it |
| `n/a` | this task never gave the rule an opportunity to apply |

## Grade blind

Do not tell the grader which arm a diff came from, and do not grade a diff in the
same breath as the rule text you just read out of CLAUDE.md. Knowing that a diff is
"the stripped one" is enough to make violations appear. Shuffle the diffs, grade
them, then join the verdicts back to their arms.

## Then read the pattern across runs

Only now bring the arms back together. For each rule, compare how often it was
followed in each arm:

| Pattern | What it means | Action |
|---|---|---|
| control follows, stripped violates | **Load-bearing.** The rule is doing real work. | Keep it. Rewrite it shorter and more specific. |
| both arms follow it | The model does this anyway. The rule is buying nothing. | Delete it. |
| both arms violate it | The rule is ignored *even when loaded*. | Do not just delete it. If it matters, move it to a hook, test, or lint rule. If it does not, delete it. |
| never applicable | This task never exercised it. **No evidence either way.** | Keep it, and mark it untested. Deleting on this is deleting on faith. |
| inconsistent within an arm | Noise, not signal. | More runs, or a better probe task. |

That fourth row is the one people get wrong. A rule the probe task never touched
looks identical to a rule that made no difference, and they mean opposite things.
Report them as separate lists and never merge them.

---

## The confound that will bite you

**Existing code substitutes for the rules file.**

In validation, a stripped run wrote two files. In the file that already contained a
similar function, it matched all four house conventions perfectly, copying them
from the neighbour. In the brand-new file, with no local example, it broke them and
fell back to defaults.

Same run, same missing CLAUDE.md, opposite results, entirely because of what
happened to be on screen.

So when you grade, separate **edits to existing files** from **newly created
files**. A rule that only holds up in new files is not worthless; it means your
codebase is already teaching that convention by example, and the rule is a backstop
for greenfield work. That is a real finding and a different decision from "delete
it". Weight new-file evidence more heavily, and say which kind of evidence each
verdict rests on.

---

## Six places the difference actually shows up

When a rule is vague, or when you want to find rules you never wrote down, read the
diffs for these. They are where ablation differences concentrate.

**1. Registration and wiring.** The single most repeatable failure. A new test file
not added to an enumerated test script never runs, and the suite stays green. Also:
modules missing from a barrel or export map, routes or migrations not registered,
env vars not added to the schema or CI config.

**2. Generated artifacts.** If the repo generates code, schemas, docs, or lockfiles
from a source of truth, editing the source without regenerating leaves the tree
inconsistent, and CI catches it later rather than sooner.

**3. Error posture.** Projects have a house position on failure: throw early, or
degrade quietly. An agent with no instructions defaults to defensive, forgiving
code. Look for empty catches, swallowed errors, a default returned where the repo
would raise.

**4. Placement and naming.** Directory layout, test co-location, module boundaries.
Derivable by reading neighbours, which is exactly what an agent skips when nothing
tells it to look. Expect this one to be heavily affected by the confound above.

**5. The design choice itself.** The highest-value case and the easiest to miss,
because both answers work. Some problems have an obvious fix the repo has
deliberately ruled out: a timeout where the project forbids timers, a config field
where the project routes through presets. Ask whether the two arms produced the
*same design* or two different designs that both happen to work.

**6. Dependencies and tooling.** A package added where the repo has a policy. A
different HTTP client, test runner, or date library than the one already in use.

---

## The re-add ladder

Re-add one line at a time, and only for a rule you graded `load-bearing`. A rule you
cannot tie to an observed difference is a rule you are keeping on faith.

Prefer, in order:

1. **A test or lint rule.** Deterministic, cannot be ignored, costs no context.
2. **A hook or pre-commit check.** Runs as code, spends no attention budget.
3. **An on-demand instruction** (a skill, a path-scoped rule) so it loads only when
   relevant.
4. **An always-loaded line.** Last resort. It is charged to every session for the
   rest of the project's life.

If a rule exists to make the model *reason* better, it has probably expired. If it
exists to make the model *check* something it would not think to check, it has not.
