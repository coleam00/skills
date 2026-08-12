# The runner

The execution layer. Copy `factory/` into your repository and you have a working
dark-factory pipeline: a dispatcher, a runner, a structural gate, a protected-path guard,
a merge, a deploy, and seven node prompts.

**This is the part of a factory that is the same everywhere, so it is the part that ships
as a template.** What is *not* here is component 5 - the validation harness - because
what "working" means for your app is the one thing nobody can write for you. That split
is not an omission, it is the whole thesis:

> **The factory harness is templatable. The validation harness is not.**

Every comment in these files that reads like a war story is one. They are the expensive
half of what you are copying - a factory rebuilt from the design alone rediscovers all of
them, in production, unattended. Do not tidy them away.

---

## What you get

```
factory/
  config.sh          THE FILE YOU EDIT. Every project-specific value.
  orchestrator.sh    the dispatcher: fixed priority, autonomy dial, stop button
  run-workflow.sh    the runner. THIS is the orchestrator; there is no second definition
  gate.sh            the structural gate: positive markers, counts, calibration
  guard.py           protected paths, size cap - fails CLOSED
  merge.sh           the merge. Code, never a model
  deploy.sh          poll, health-check, swap, rollback
  state.py           the transition table. Refuses illegal transitions
  gh_backend.py      GitHub issues + labels as state, with read-back verification
  tripwire.py        fails loudly if a builder artifact reached the validator
  cost.py            token instrumentation, on from run one
  node_failure.py    why a node failed: budget, denial, crash and refusal are different
  prompts/*.md       the seven nodes. THE INTERVIEW'S OUTPUT - rewrite these
  install-trigger.sh arms cron / systemd / Task Scheduler. Refuses below dial 1
  init-labels.sh     creates the factory:* label vocabulary on GitHub. Run once
issues/0001-example.md   the INPUT. The front matter is the state machine
.gitignore         REQUIRED - the pre-flight refuses to start without it
.gitattributes     REQUIRED on Windows - pins LF so *.sh survive a Linux box
```

## Install it

```bash
cp -r templates/runner/factory        <your-repo>/factory
cp    templates/runner/.gitignore     <your-repo>/.gitignore      # or merge into yours
cp    templates/runner/.gitattributes <your-repo>/.gitattributes
cp -r templates/runner/issues         <your-repo>/issues          # file backend only
mkdir -p <your-repo>/.factory/{locks,holdout,runs}

# GitHub backend only, once: the factory:* labels ARE the state machine
bash factory/init-labels.sh
```

**Both dotfiles are load-bearing and the factory will not run without the first one.**
`run-workflow.sh` pre-flights every committing workflow and refuses to start when a
credential-shaped path is not ignored - so on a repo with no `.gitignore` the very first
lap exits 3 with `PREFLIGHT: .env is not gitignored` and parks your issue at
`needs-human`. The `.gitattributes` pins LF, without which every `factory/*.sh` fails on
a Linux box with `bad interpreter: ^M`.

Then confirm both, before anything else:

```bash
git check-ignore -v .env secrets.json credentials.json    # must print a match for each
git check-ignore -v .factory/runs                          # builder artifacts stay out
```

Then, in order. Do not skip to step 4.

### 1. Fill in `factory/config.sh`

Everything project-specific reads from here. If you find yourself editing another script
to change a path or a command, that is a bug in `config.sh` and it should grow a variable
instead.

The line that matters most is `FACTORY_VALIDATE_CMD`. That is component 5, and it is
yours to build.

### 2. Set the protected list in `factory/guard.py`

Seed it, do not just accept what came out of the interview. Governance files, `.github/`,
Dockerfiles, anything under `deploy/` or `infra/`, `.env*`, auth modules, rate-limit
constants. Then ask what else.

**The one property that matters: the agent cannot amend the rules it is judged by.**

### 3. Rewrite `factory/prompts/*.md` as your process

These are the interview's output. The factory's claim is that it runs *your* process with
the approvals removed, so these should be recognisably your planning step, your
implementation step, your review step - loading the skills and rules files you already
load at each one. A user who recognises their own workflow here will maintain it. One who
has to learn a new pipeline will not.

### 4. Prove one lap by hand, at level 0

`FACTORY_AUTONOMY` starts at 0 and `orchestrator.sh` refuses to dispatch below 1. That is
deliberate. Drive a real issue all the way to a PR you merge yourself:

```bash
python factory/state.py next                      # what the dispatcher WOULD run
bash factory/run-workflow.sh implement-issue <target>
bash factory/run-workflow.sh validate-pr <target>
bash factory/orchestrator.sh --dry-run            # says what it would do, does nothing
```

### 5. Then, and only then, raise the dial one notch

```bash
FACTORY_AUTONOMY=1 bash factory/orchestrator.sh
```

Watch one full cycle at each level before the next. **Level 3 is the real threshold** -
the first level where code merges without a human reading it.

---

## The things that are load-bearing

Change these only on purpose.

**The dispatcher never asks a model what to run.** An LLM asked "what work is pending?"
invents dispatches for issues that were never filed. Bash, a fixed priority order, boring
shared state.

**Priority order: fix, validate, implement, triage.** Finish in-flight work before
starting new work. Reversed, the factory triages forever while its own PRs rot and
throughput looks busy while going to zero.

**Each node gets a fresh session.** Not a performance choice. A node that inherits the
previous node's context inherits its reasoning, and the entire holdout argument rests on
some nodes not having seen it.

**The holdout is enforced by the agent's deny list, not by a prompt.** `--disallowedTools`
on `$FACTORY_HOLDOUT_DIR`. Test it in both directions before believing it: without the
deny the agent returns the file's first line, with it the agent returns blocked.

**Governance is read from the BASE branch.** A PR must not be able to weaken the rulebook
it is about to be judged against.

**The guard runs from the root checkout, not from inside the worktree.** Run it in the
worktree and a PR supplies the code that judges it.

**Empty is not pass.** Every marker in `FACTORY_REQUIRED_MARKERS` must be present. Never
test for the absence of the word "error".

**Editing nodes are leashed by file count, not just line count.** `FACTORY_FILE_CAP`
catches the failure a line cap cannot see: a refactor node growing a six-file PR into
eleven with five one-line "while I was in here" edits, well under the line cap the whole
way, in files nobody asked it to touch.

**The gate overrides the model.** When the raw markers and the verdict disagree, the raw
output wins and the PR escalates.

**The stop button fails closed.** Any error reading the stop state counts as stopped. Use
it once on purpose before going unattended.

---

## What is deliberately missing

- **The validation harness.** `FACTORY_VALIDATE_CMD` points at something you write. See
  `references/validation-harness.md`; it is the longest reference for a reason.
- **The holdout scenarios.** They go in `$FACTORY_HOLDOUT_DIR`, they are written *before*
  the work, and the builder never reads them.
- **The governance files.** `MISSION.md`, `FACTORY_RULES.md` and your conventions file
  come from `templates/`, filled in from your PRD and the interview.
- **A scheduler.** See `references/setup.md`.

Run `scripts/factory_doctor.py --repo <your-repo>` at every step. It will fail loudly at
first, which is correct - it is a checklist, and this is you working through it.
