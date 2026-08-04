---
name: ablate-ai-layer
description: Measure whether a repository's AI instructions still earn their place, by running the same real task many times with the layer intact and with it stripped, then grading every rule against what actually changed. Runs both arms itself in throwaway git worktrees and never touches the working tree. Agent-agnostic across CLAUDE.md, AGENTS.md, .claude/, .agents/, .cursor/rules, .clinerules, .windsurfrules and copilot-instructions. Use when the user wants to prune, audit, clean up, shrink or "delete" their CLAUDE.md, AGENTS.md, cursor rules, agent instructions or AI layer; when they ask whether their rules are still needed, whether their context is bloated, or what to cut; or when they mention ablating, ablation, or testing their agent without its instructions.
---

# Ablate the AI layer

Model upgrades quietly retire instructions. A rule written to work around a weaker
model becomes dead weight that competes for attention with the rules that still
matter. Reading the file will not tell you which is which. Only an experiment will.

**You run the experiment. The user picks the task and approves the conclusion.**
Do not hand the user a list of commands to run; the script drives both arms.

## What makes the result trustworthy

- **Both arms, many runs each.** A stripped agent does not visibly fail, so a single
  run has nothing to compare against and "seems fine" becomes "delete something
  load-bearing". Two runs of the *same* arm can also differ more than the two arms
  differ, so one pair per arm is the floor, not the target.
- **Nothing is moved aside.** Every run happens in a detached git worktree built
  from HEAD in a temp directory, outside the repo, and deleted afterwards. The
  user's working tree is never modified, so there is no restore step to forget.
- **Only the always-loaded set is stripped by default.** Skills, subagents and
  path-scoped rules cost nothing until they fire, so deleting them buys back no
  context. Hooks and permissions are never touched: they run as code and spend no
  attention.

---

## Step 1. Map the layer

```bash
python <skill>/scripts/map_layer.py [repo_root]
```

Read-only. Sorts every artifact into always-loaded, on-demand, and enforcement, and
prints what the always-loaded set costs on every session before the user types
anything. Show them that number.

If nothing is found, say so and stop. There is nothing to test.

## Step 2. Get the probe task

**This is the one thing you must not decide for the user.** The task determines
whether the experiment can detect anything at all.

A good probe task is real work they would do anyway, touches code where house
conventions plausibly apply, and adds something that has to be wired in: a test, an
endpoint, a migration, a command.

A bad one is a typo, a rename, or any one-line fix. It is fully derivable, both arms
will match, and the user will wrongly conclude their whole layer is worthless. Say
that out loud if they offer one, and ask for something with conventions at stake.

Write the agreed task verbatim to a file. Every run reuses it byte for byte.

## Step 3. Show the plan and get approval

Report before spending anything: how many runs, which model, roughly what it will
cost, and that the working tree will not be touched.

```bash
python <skill>/scripts/run_ablation.py <repo> --task-file <task.md> --dry-run
```

The dry run also surfaces two things worth pausing on:

- **A dirty working tree.** Worktrees are built from HEAD, so uncommitted edits are
  not under test. Offer to commit or stash first.
- **A build-dependency warning.** Some repos import their own AI layer as source. A
  CLI that reads its skill markdown at build time breaks the moment those files go
  missing, and the user will read a compile error as an agent regression. Keep
  `--scope always` if this warns.

## Step 4. Run it

```bash
python <skill>/scripts/run_ablation.py <repo> --task-file <task.md> --runs 2
```

This is the whole experiment. It builds a fresh worktree per run, strips the layer
in the stripped arm, runs the same prompt in each, captures every diff, cleans up
every worktree, and writes results to `.ablation/<timestamp>/` (gitignored).

Useful flags: `--runs 3` when the user intends to act on the result, `--scope all`
to test the harder claim that skills and subagents have expired too, `--model`,
`--jobs` for concurrency, `--runner` for a non-Claude agent that reads a prompt on
stdin.

If an arm produced nothing usable, stop. An empty arm is a broken experiment, not a
finding. Re-run before drawing anything from it.

## Step 5. Grade

Read `references/comparison.md` before analysing. It is the rubric, and it contains
the two things that make the difference between a real result and a confident wrong
one: grade **per rule** rather than diffing the arms against each other, and grade
**blind** to which arm a diff came from.

The short version:

1. Turn the always-loaded files into a numbered checklist of testable claims. Mark
   anything unfalsifiable ("write clean code") as exactly that.
2. Judge every run's diff against every claim: `followed`, `violated`, or `n/a`.
3. Only then join verdicts back to arms and read the pattern.

## Step 6. Report

Give the user a table, one row per rule, sorted so the actionable rows are first:

| Pattern across runs | Verdict | Action |
|---|---|---|
| control follows, stripped violates | load-bearing | keep, rewrite shorter |
| both arms follow | model does this anyway | delete |
| both arms violate | ignored even when loaded | make it a hook or test, or delete |
| never applicable | **untested** | keep, no evidence either way |
| inconsistent within an arm | noise | more runs or a better task |

Keep "untested" visually separate from "no difference". They look identical in the
data and mean opposite things, and merging them is how a rule that protects a case
this task never touched gets deleted.

## Step 7. Apply, with the user's approval

Never edit the rules file unattended. Propose the edit, show the diff, wait.

Re-add or keep one line at a time, only for rules with observed evidence, and prefer
a test, then a hook, then an on-demand instruction, and only then an always-loaded
line. Finish by re-running `map_layer.py` so the new always-loaded total sits next to
the old one.

---

## Honest framing to give the user

- **One probe task is a data point, not a verdict.** Encourage a second task on a
  different part of the codebase before deleting anything large.
- **A null result is a real result.** If the arms match, that part of the layer has
  genuinely expired and can go.
- **The reverse is also true.** Do not let one clean run justify deleting rules for
  cases this task never exercised: security, compliance, release procedure.
- **Existing code substitutes for the rules file.** A stripped run copies
  conventions from neighbouring code when there is a neighbour to copy. The same
  rule can hold in an edited file and break in a new one. Weight new-file evidence
  more heavily and say which kind each verdict rests on.
- **Cheaper and smaller models lean on instructions more than frontier models do.**
  A layer that looks redundant under a frontier model may still be carrying a
  cheaper one. If the team runs a mix, ablate against the weakest model in use.

## Resources

- `scripts/map_layer.py`: read-only inventory of the layer, agent-agnostic.
- `scripts/run_ablation.py`: runs both arms and collects the diffs. `--help` lists
  every flag. Never read either script into context; only their output.
- `references/comparison.md`: the grading rubric. Read it before Step 5.
