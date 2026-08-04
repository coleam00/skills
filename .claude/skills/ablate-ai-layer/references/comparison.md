# Reading the two runs

The hard part of an ablation is not deleting things. It is seeing what you lost.

**Both runs will look fine.** In benchmarking this across dozens of runs on a
production repo, the stripped agent never produced obviously broken code. It
produced code that compiled, read well, and would have passed review. The
difference showed up in what it did not know to do.

So do not ask "did the ablated run fail?" It will not. Ask the questions below.

---

## 1. Registration and wiring

The single most repeatable failure. Many repos require a new file to be declared
somewhere before it does anything.

- A new test file that is not added to an enumerated test script **never runs**,
  and the suite stays green.
- A new module missing from a barrel file, index, or export map.
- A new route, command, migration, or plugin not registered in its registry.
- A new env var not added to the schema, sample file, or CI config.

Check: did each run register what it created? Diff the manifest-ish files
(`package.json`, `index.ts`, `mod.rs`, `__init__.py`, CI config) between runs.

## 2. Generated artifacts

If the repo generates code, schemas, docs, or lockfiles from a source of truth,
editing the source without regenerating leaves the tree inconsistent, and CI
usually catches it later rather than sooner.

Check: did one run run the generator and the other not?

## 3. Error posture

Projects have a house position on failure: throw early, or degrade quietly.
An agent with no instructions defaults to defensive, forgiving code.

Check: empty catches, swallowed errors, functions that return a default where
the repo would raise, retries where the repo wants a hard stop.

## 4. Where things live and what they are called

Directory placement, file naming, test co-location, module boundaries. Derivable
by reading neighbours, which is exactly what an agent skips when nothing tells it
to look.

## 5. The design choice itself

The highest-value case and the easiest to miss, because both answers work.

Some problems have an obvious fix that the repo has deliberately ruled out: a
timeout where the project forbids timers, a new config field where the project
routes through presets, an extension to a mini-language the project has frozen.
If your instructions encode a decision like that, the ablated run is where you
find out whether the model would have made it on its own.

Check: are the two implementations the *same design*, or two different designs
that both happen to work?

## 6. Dependencies and tooling

A new package added where the repo has a policy. A different test runner, HTTP
client, or date library than the one already in use.

---

## Scoring it honestly

For each difference, sort it into one of three buckets:

| Bucket | Meaning | Action |
|---|---|---|
| **Cosmetic** | Different but equally valid. Naming, ordering, comment density. | Delete the rule. It was never earning its keep. |
| **Convention** | The ablated run broke a house rule that is real but not derivable. | Keep the rule. Make it shorter and more specific. |
| **Correctness** | The ablated run is actually wrong. | Keep the rule, and consider whether it should be a hook or a test instead, so it cannot be ignored. |

The most common honest outcome is a pile of cosmetic differences and one or two
convention ones. That is a good result: it means most of the file can go and a
small part of it is load-bearing.

## The re-add rule

Re-add one line at a time, and only for differences you actually observed. A rule
you cannot tie to a specific difference in this comparison is a rule you are
keeping on faith.

Prefer, in order:

1. **A test or a lint rule.** Deterministic, cannot be ignored, costs no context.
2. **A hook or pre-commit check.** Runs as code, spends no attention budget.
3. **An on-demand instruction** (a skill, a path-scoped rule) so it loads only
   when relevant.
4. **An always-loaded line.** Last resort, because it is charged to every session
   for the rest of the project's life.

If a rule exists to make the model *reason* better, it has probably expired.
If it exists to make the model *check* something it would not think to check,
it has not.
