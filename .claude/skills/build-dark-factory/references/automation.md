# The agent, the orchestrator, and the dispatcher

Three separate choices that people collapse into one. Separate them explicitly in the
interview, because only one of them is hard to change later.

| Choice | What it is | How replaceable |
|---|---|---|
| **The coding agent** | what turns a prompt into edits | **Very.** It is a config value. |
| **The orchestrator** | what defines and runs multi-step workflows | Hard. This is the real commitment. |
| **The dispatcher** | what decides when anything runs at all | Easy, and it must stay boring. |

---

## 1. The coding agent

Every headless coding agent exposes nearly the same contract: a print or exec flag, a
structured output mode, a way to skip approvals, and a session id to resume. The
factory shells out to a command and reads the exit code. That is the whole interface.

| Agent | Headless invocation | Worth knowing |
|---|---|---|
| **Claude Code** | `claude -p "..." --output-format json` | `--allowedTools`, `--disallowedTools`, `--permission-mode`, and `--max-budget-usd` as a hard per-invocation spend cap. There is **no** `--max-turns`; see the warning below. |
| **Claude Agent SDK** | Python `claude-agent-sdk`, TS `@anthropic-ai/claude-agent-sdk` | In-process instead of shelling out. Better when you want to inspect or interject mid-run. |
| **Codex** | `codex exec --sandbox workspace-write --ask-for-approval never` | Sandbox modes are the thing to get right. |
| **Cline** | `cline schedule create ... --cron "0 2 * * *"` | Ships **native cron**, so part of the dispatcher is built for you. |
| **Goose** | `goose run --instructions <file>` | Has its own `goose schedule` too. |
| **Amp** | `amp -x "..."` | Webhooks available if you want event-driven instead of polling. |
| **Pi** | `pi --print` / JSON mode | Provider-independent; useful when the point is not being locked to one model vendor. |
| **Antigravity** | `agy -p "..." --output-format json` | Watch the default print timeout - it is short, and it will kill real work mid-run while looking like a model failure. |

**Verify the exact flags against current docs before writing them into a workflow.**
CLI surfaces move, and a flag that silently changes meaning is worse than one that
errors. Several of these CLIs do not reject unknown flags - the value falls through
into the prompt instead - so a stale flag becomes invisible prompt injection.

> **This page got it wrong, which is the best possible demonstration of why it says so.**
> It listed `--max-turns` as a Claude Code flag. It is not one. Claude Code **accepts it,
> ignores it, and exits 0** - so the runner passed a cost cap on every node, the
> comments all claimed a cap was in force, and no cap ever applied. Nothing errored,
> nothing logged, and the only reason it surfaced is that somebody ran `claude --help`.
>
> **A guard that silently does not apply is worse than no guard**, because you stop
> watching the thing it was guarding. Run this before trusting any flag you write into a
> workflow:
>
> ```bash
> for f in --allowedTools --disallowedTools --permission-mode --max-budget-usd; do
>   claude --help | grep -q -- "$f" && echo "OK $f" || echo "MISSING $f"
> done
> ```
>
> And prefer a **dollar** ceiling to a turn ceiling regardless. Turns are a proxy for cost
> and a bad one; `--max-budget-usd` is the thing you actually care about, and it genuinely
> enforces - the run comes back `is_error: true` when it trips.

### Choosing

Pick the one already authenticated on the machine that will run the factory. Not the
best one. The one that works today. Because the agent is genuinely swappable, this
choice is cheap and reversible, and treating it as the big decision spends attention
that belongs in component 5.

### What does *not* port

Say this out loud, because it is where the real time goes:

- **credential expiry**, silently, mid-run
- **cost cliffs** nobody warns you about
- **no default session timeout** in most of them
- **sandbox egress** you have to design yourself

Same four problems in every agent. None of them solve it for you.

---

## 2. The orchestrator

What defines "plan → implement → review → gate → merge" as steps with dependencies.
The real commitment; changing it means rewriting every workflow.

### There is one in the box

`templates/runner/` is a working orchestrator of the first kind below - plain scripts,
one machine, total transparency - lifted from a factory that runs. Copy it unless you
have a reason not to:

| file | what it is |
|---|---|
| `factory/config.sh` | **the only file you edit.** Agent, models, validate command, markers, dial, limits, paths |
| `factory/orchestrator.sh` | the dispatcher: fixed priority, per-target lock, autonomy dial, stop button |
| `factory/run-workflow.sh` | **the runner. THIS is the orchestrator** - there is no second definition of the pipeline |
| `factory/gate.sh` | the structural gate: required markers, counts, calibration, verdict |
| `factory/guard.py` | protected paths and the size cap. Fails **closed** |
| `factory/merge.sh` | the merge. Code, never a model |
| `factory/deploy.sh` | poll, health-check, swap, rollback |
| `factory/state.py` + `gh_backend.py` | the transition table, and GitHub labels as state |
| `factory/tripwire.py` · `cost.py` · `node_failure.py` | holdout tripwire, token instrumentation, why-a-node-failed |
| `factory/prompts/*.md` | the seven nodes. **The interview's output - rewrite these** |

**Two definitions of one pipeline is one too many.** That repo carried YAML DAG
definitions alongside the bash for a while, on the theory that an engine would run them.
Nothing did, so they drifted - and what they drifted into was a `deny_paths` entry that
made the holdout read-block look enforced when the only thing enforcing it was a sentence
in a prompt. **A stale spec that invents a safety property is worse than no spec**, and
the one nobody runs is always the one that drifts. Pick one definition.

If you are bringing your own engine, the runner is still the reference for *what each node
must do*: fresh context per node, tool allowlists, the holdout deny passed to the agent,
an explicit commit step, the guard from the root checkout, governance from the base
branch. Port the properties, not the bash.

| Option | Shape | Good when | Cost |
|---|---|---|---|
| **Plain shell scripts** | sequential calls, exit codes | small factories, one machine, total transparency | no parallelism, no resume, state is yours to invent |
| **A YAML DAG runner** | declared nodes and edges, per-node model and tool limits, artifacts dir | you want node-level control of context isolation and tools - which component 5 needs | a dependency to run and understand |
| **GitHub Actions** | jobs and steps in the repo | you want it in CI with no extra infrastructure | ephemeral runners make long E2E and app-startup awkward; watch the token trap in `deployment.md` |
| **An agent SDK, in process** | your own program driving sessions | you need custom control flow or to interject mid-run | you are now maintaining an orchestrator |
| **Model-led orchestration** | one agent spawns and coordinates others | flexible, adapts to unexpected shapes | non-deterministic; the shape of the work is decided by a model each time |

### The genuine trade-off, stated fairly

A **declared DAG** means you wrote the nodes and edges, and the model fills in the
work without choosing the shape. Reproducible, debuggable, and it lets you set tool
allowlists and fresh-context boundaries per node - which is how the holdout gets
enforced structurally rather than by instruction.

**Model-led** means a coordinating agent decides how to decompose and spawn. More
adaptive, less predictable, and much harder to prove an independence property about.

Neither is the winner. But note which one component 5 needs: **the holdout is a
statement about what a given step is allowed to read**, and that is far easier to
guarantee when the steps are declared than when they are invented at runtime.

---

## 3. The dispatcher

> **The dispatcher must be the dumbest, most deterministic thing in the entire
> system. It is the one component where a wrong answer is worse than no answer.**

### Do not ask a model what to run

An LLM asked "what work is pending?" will invent dispatches for work that does not
exist - runs for issues that were never filed, PRs that do not exist. It is a
plausible-sounding answer with nothing behind it, and the factory then acts on it.

Bash. A fixed priority order. Boring shared state.

### Shared state

GitHub labels are enough, and they have a real advantage: they are visible, editable
by a human from a phone, and they *are* the audit trail.

```
factory:accepted → factory:in-progress → factory:needs-review
                                        ├── factory:approved      (merge, then deploy)
                                        ├── factory:needs-fix     (back to in-progress)
                                        └── factory:needs-human   (stop; the only thing that reaches you)
```

No database. No message bus. If information has to travel between workflows, it moves
as a label or a comment. That constraint keeps the system inspectable, and inspectable
is the property you will want at 2am.

#### Four things labels are not, all learned the hard way

Labels are good shared state and a bad lock. Every one of these was written down as a
prediction first and then contradicted by a real run.

1. **There is no compare-and-swap.** Two dispatchers reading `factory:accepted` both
   claim the issue, because "read the label, write the label" is not atomic and nothing
   in the API makes it so. **Moving to GitHub does not retire your per-target lock.** If
   you built one for the file backend, keep it; the label is the audit trail, not the
   mutex.
2. **Label writes are not immediately visible to label reads.** Measured lag between
   setting a label and seeing it on the list endpoint was two to four seconds. A
   dispatcher that writes then immediately re-reads will occasionally see the old world.
3. **The stop button must be a label you ADD, and the read must fail closed.** "Remove a
   label to stop" is the obvious design and it is backwards: a missing label is
   indistinguishable from an API call that failed to list it, so a network blip reads as
   "carry on". Add `factory:stop`, treat *any* error listing it as stopped, and keep a
   local kill file too, because the local one works with the network down.
4. **Closed is not a disposition.** `deferred` and `rejected` are both closed issues and
   are indistinguishable without labels. Get that wrong and the factory rejects the
   roadmap the quarter it arrives, which is the failure the mission file's
   deferred-versus-never split exists to prevent. GitHub also performs transitions your
   table never authorised: `Closes #N` in a merged PR closes the issue, so
   closed-and-unlabelled is a real state you have to handle.

#### Branch protection does not replace your merge script

The tempting move on GitHub is to delete `merge.sh` and let a required check plus branch
protection be the gate, on the grounds that a ruleset is not something the agent can
edit.

It is, in the case that matters. **The factory authenticates as a principal that
administers the repository, and an account that can edit a ruleset can bypass one.**
Unless you have provisioned a separate least-privilege identity for the factory, and
verified it cannot administer the repo, the merge stays in code you control.

Two smaller traps in the same area: nothing publishes a check run if your gate executes
on the dispatching machine rather than in Actions, so a *required* check that never
reports blocks every merge forever. And a third-party App can comment on a PR seconds
after it opens, so a judge that reads PR comments is reading a stranger's text. Have it
read the diff and the issue from disk instead.

### Priority order, and why it is load-bearing

1. **fix** a PR labelled needs-fix (under the attempt cap)
2. **validate** a PR labelled needs-review, oldest first
3. **implement** the highest-priority accepted issue
4. **triage** untriaged issues

**Finish in-flight work before starting new work.** Reversed, the factory triages
forever while its own PRs rot, and throughput looks busy while going to zero.

### A node that exits 0 having done nothing

Three separate versions of this showed up in real dispatch, and none of them
were visible when the same workflows were driven by hand.

- **An agent hit its turn cap**, escalated, and the message named a fault that did not
  exist. The expensive planning half had been paid for and thrown away. Read the agent's
  own JSON result and report the real terminating reason.
- **An agent asked to run a command its allowlist did not cover**, was refused, said so
  politely in prose, and exited 0 having changed nothing. **A tool denial is not a
  failure and it is not a success**; it is the node telling you it wanted something it
  could not have. Log denials per node, and quote them into the escalation whenever the
  diff comes back empty. Doing this once revealed that a planning node had been silently
  denied tools on essentially every run since it was written, asking, being refused, and
  working around it.
- **A node edited its worktree and committed nothing**, and the cleanup removed the
  worktree seconds after the guard had correctly reported two changed files. A human
  commits without being told to. An agent does not, unless the workflow makes it a step.

The general rule: **assert on the artifact, not on the exit code.** A run that produced no
commit, no PR and no diff did not succeed, whatever it returned.

### Limits that are not optional

- **Attempt cap.** Two fix attempts per PR, then escalate. Without it a PR ping-pongs
  until the budget is gone.
- **Concurrency cap, starting at one.** Raise it only after the serial version is
  boring. When you do raise it, add a per-target lock: never dispatch a workflow whose
  (workflow, target) pair is already in flight, or two runs will race on the same PR.
- **Batch caps.** Cap triage per run. A backlog should drain across cycles rather than
  in one expensive burst.
- **Flood protection**, if other people can file issues. Cap issues per author per
  day; exempt yourself.
- **A stop button.** A kill file the dispatcher checks, or disabling the schedule.
  Obvious, documented, and tested once on purpose.

### Scope every editing node to its own diff

Any node that edits code must be leashed to the files it is allowed to touch:

```bash
git diff --name-only <base>...HEAD
```

A cleanup or refactor node with no diff scope will grow a six-file PR into eleven,
and introduce a bug on the way through. If a node cannot name the files it may touch,
it will touch more of them.

### Model routing

Two slots decide quality: the one that **plans** and the one that **implements**.

Putting a premium model in **one** of them buys most of the quality of putting it in
both. Going from zero premium slots to one is a large, real improvement. Going from
one to two is usually inside the noise.

**Plan with the expensive model. Build with the cheaper one.** Picking the wrong slot
is cheap. Running a premium model in zero slots is what actually costs you.

Measure this on your own repo before believing it, and state your noise floor when you
do - a benchmark without one is a story.
