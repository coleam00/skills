---
name: ablate-ai-layer
description: Safely test whether a repository's AI instructions still earn their place, by backing them up, stripping the always-loaded ones, running the same real task with and without them, and comparing the two results. Agent-agnostic across CLAUDE.md, AGENTS.md, .claude/, .agents/, .cursor/rules, .clinerules, .windsurfrules and copilot-instructions. Use when the user wants to prune, audit, clean up, shrink or "delete" their CLAUDE.md, AGENTS.md, cursor rules, agent instructions or AI layer; when they ask whether their rules are still needed, whether their context is bloated, or what to cut; or when they mention ablating, ablation, or testing their agent without its instructions.
---

# Ablate the AI layer

Model upgrades quietly retire instructions. Rules written to work around a
weaker model become dead weight that competes for attention with the rules that
still matter. This skill finds out which is which, by experiment rather than
opinion.

**The one thing that makes this work: run the task twice, with and without.**
A stripped agent does not visibly fail. It produces working, plausible code and
reports success. Without a control run to diff against, the user will conclude
"seems fine" and delete something load-bearing. Never let them ablate and eyeball
a single run.

Nothing is ever deleted. Files are moved into `.ablation/held/` with a verified
copy in `.ablation/backup/`, and `restore` puts them back.

---

## Step 1. Map the layer

```bash
python <skill>/scripts/map_layer.py [repo_root]
```

Read-only. Detects which agents the repo is set up for and sorts every artifact
into three groups:

- **always-loaded** — enters context every session whether the task needs it or
  not. This is the only group worth ablating.
- **on-demand** — skills, subagents, commands, path-scoped rules. Costs nothing
  until it fires. Deleting it buys back no context.
- **enforcement** — hooks, permissions. Runs as code, spends no attention.

Show the user the always-loaded total. That number is what they pay on every
session before typing anything.

If nothing is found, say so and stop. There is nothing to test.

## Step 2. Check for build dependencies

```bash
python <skill>/scripts/ablate.py check [repo_root]
```

Some repos import their own AI layer as source. A CLI that compile-time imports
its skill markdown will fail to build the moment those files move, and the user
will read a compile error as an agent regression.

If this warns, keep `--scope always` (the default), which never touches skills.

## Step 3. Pick the probe task

This decides whether the experiment can detect anything. Get it right.

**A good probe task:**
- is real work the user would do anyway, ideally an open issue or ticket
- touches code where house conventions plausibly apply
- adds something that has to be wired in: a test, an endpoint, a migration, a command
- has a verifiable outcome

**A bad probe task:**
- a typo, a rename, a one-line fix. Fully derivable, so both runs will match and
  the user will wrongly conclude their whole layer is worthless
- anything with no conventions at stake
- anything so large it will not finish twice

Ask the user for the task. Do not invent one for them; they know which work
exercises their conventions.

## Step 4. Baseline run, layer intact

```bash
git checkout -b ablation/control
```

Have the user run the probe task **in a normal session with the layer in place**,
then commit the result on that branch. Record the exact prompt used. It must be
reused verbatim.

## Step 5. Back up and ablate

```bash
python <skill>/scripts/ablate.py backup [repo_root]
python <skill>/scripts/ablate.py ablate [repo_root] --scope always
```

`backup` refuses nothing but warns on a dirty tree, records the git commit, hashes
every file, and adds `.ablation/` to `.gitignore`. `ablate` refuses to run without
a backup, and refuses to run twice.

`--scope always` (default) moves only the always-loaded set. `--scope all` also
moves skills and subagents, which tests the harder claim that the whole layer has
expired. Default to `always`: it isolates the variable that actually costs context.

**Claude Code shortcut.** `claude --safe-mode` starts a session with CLAUDE.md,
skills, rules, hooks and MCP all disabled, touching no files at all. That is the
zero-risk way to run step 6 for Claude Code users. It is all-or-nothing, so it
corresponds to `--scope all`, not to the default. `--bare` is not a substitute:
it ignores subscription auth and needs an API key.

## Step 6. Ablated run

```bash
git checkout main && git checkout -b ablation/stripped
```

**Start a new agent session.** The layer is read once at session start, so an
already-open session is still running on the old instructions and the run is void.

Run the identical prompt from step 4. Commit on this branch.

## Step 7. Restore immediately

```bash
python <skill>/scripts/ablate.py restore [repo_root]
```

Do this as soon as the ablated run finishes, before any analysis. Never leave the
user sitting in an ablated repo.

Restore verifies every file against its backup hash. If the agent created a file
at a path that was moved aside (an `/init` run, say), that version is preserved in
`.ablation/created-during-ablation/` rather than silently overwritten. Mention it
if it appears: it is a direct signal of what the model thought was missing.

## Step 8. Compare

```bash
git diff ablation/control ablation/stripped
```

Read `references/comparison.md` before analysing. It lists the six places the
difference actually shows up and the three buckets to sort each one into.

Do not ask whether the ablated run failed. It did not. Ask what it did not know
to do.

Report to the user as:

- **Cosmetic differences** — delete those rules
- **Convention differences** — keep, but rewrite shorter and more specific
- **Correctness differences** — keep, and consider a test or hook instead

## Step 9. Re-add deliberately

Re-add one line at a time, only for differences observed in step 8. A rule with
no observed difference behind it is being kept on faith.

Prefer a test or lint rule, then a hook, then an on-demand instruction, and only
then an always-loaded line. Always-loaded is charged to every future session.

Finish by re-running `map_layer.py` so the user sees the new always-loaded total
next to the old one.

---

## Honest framing to give the user

- One probe task is a data point, not a verdict. Encourage repeating on a second
  task before deleting anything large.
- A null result is a real result. If the two runs match, that part of the layer
  has genuinely expired and can go.
- The reverse is also true. Do not let a single clean run justify deleting rules
  that exist for cases this task never exercised, such as security, compliance,
  or release procedure.
- Cheaper and smaller models lean on instructions more than frontier models do.
  A layer that looks redundant on a frontier model may still be carrying a
  cheaper one.
