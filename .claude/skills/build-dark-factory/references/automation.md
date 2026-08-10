# The agent, the orchestrator, and the dispatcher

Three separate choices that people collapse into one. Separate them explicitly in the
interview, because only one of them is hard to change later.

| Choice | What it is | How replaceable |
|---|---|---|
| **The coding agent** | what turns a prompt into edits | **Very.** An afternoon. |
| **The orchestrator** | what defines and runs multi-step workflows | Hard. This is the real commitment. |
| **The dispatcher** | what decides when anything runs at all | Easy, and it must stay boring. |

---

## 1. The coding agent

Every headless coding agent exposes nearly the same contract: a print or exec flag, a
structured output mode, a way to skip approvals, and a session id to resume. The
factory shells out to a command and reads the exit code. That is the whole interface.

| Agent | Headless invocation | Worth knowing |
|---|---|---|
| **Claude Code** | `claude -p "..." --output-format json` | `--allowedTools`, `--permission-mode`, `--max-turns`, and a hard per-invocation spend cap. A bare/CI mode exists - use it. |
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

### Choosing

Pick the one already authenticated on the machine that will run the factory. Not the
best one. The one that works today. Because the agent is genuinely swappable, this
choice is cheap and reversible, and treating it as the big decision wastes the week
that should have gone into component 5.

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

### Priority order, and why it is load-bearing

1. **fix** a PR labelled needs-fix (under the attempt cap)
2. **validate** a PR labelled needs-review, oldest first
3. **implement** the highest-priority accepted issue
4. **triage** untriaged issues

**Finish in-flight work before starting new work.** Reversed, the factory triages
forever while its own PRs rot, and throughput looks busy while going to zero.

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
