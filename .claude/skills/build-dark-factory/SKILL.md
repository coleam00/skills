---
name: build-dark-factory
description: Take a PRD and build a dark factory around it - a repository that takes work in as an issue and ships validated code out with nobody at the keyboard - one component at a time, into the user's actual repo. Covers the five components in construction order - the guidance layer, the validation harness, the workflow-driven repo, deployment, and the trigger that makes it autonomous - and is agnostic about which coding agent runs underneath (Claude Code, Codex, Archon, the Agent SDK, Cline, Goose, Amp, Pi). It encodes the AI coding process the user already runs rather than replacing it. Requires a PRD as input and deliberately does not write one. Use when the user wants to build a dark factory, an autonomous or self-driving repository, a software factory, an agent that ships its own code, an unattended or overnight coding loop, or asks how to get to level 4 or level 5 of AI coding autonomy; and when they mention dark factory, lights-out coding, autonomous PRs, or a repo that maintains itself.
argument-hint: "[path/to/product.prd.md] [optional: path/to/repo]"
arguments: [prd, repo]
---

# Build a dark factory

**PRD:** $prd
**Repo:** $repo
**Raw input as typed:** $ARGUMENTS

> If those two do not look like two paths, read the raw input instead. An unquoted
> path containing a space splits into two arguments. If only one path was given,
> work out from its extension which one it is, and ask for the other.

A dark factory is a repository where work goes in one end and shipped code comes out
the other, and there is no human in between. Work arrives as an issue. Workflows plan
it, build it, validate it, and merge it. Deployment carries it to real users. Nobody
reviews the diff.

That last sentence is the whole difficulty. Everything else is plumbing.

**Build the factory into the user's repo. Do not hand them a design document.** Every
phase below ends with files committed and something demonstrably working.

---

## What this is, and what it is not

**A dark factory is not a different way of coding with AI. It is the way you already
code with AI, with the human checkpoints removed.**

Whatever process you run today is what goes inside the factory. GitHub Spec Kit, BMAD,
a PRP framework, your own plan-then-implement loop, or just a well-worn habit. The
steps stay the same. The skills stay the same. The MCP servers, the rules files, the
subagents, the commands you already trust: all the same.

One thing changes. Nobody approves the plan, and nobody reads the diff before it ships.

So the job here is not to invent a process. It is to write down the one the user
already has, then build the parts that make it safe to walk away from. **Ask what
their current AI coding workflow looks like early, and encode that**, rather than
imposing the shape of the example factory.

**This skill does not write the PRD.** That is deliberate. Producing the top-level
plan for a product is the part where almost everyone already has a custom approach
worth keeping, and a generic interview would be a downgrade. If the user has no
approach yet, point them at the `plan-create-prd` skill in this same repo and come
back when they have a file.

## What this costs, before you start it

**Say this to the user in your first message, before the interview.** Typing one command
should not silently begin a multi-hour job.

Measured on a real end-to-end build (a small Python game repo, local git, Claude Code):

| | |
|---|---|
| Interview | 10 to 20 minutes of the user's attention, in bursts |
| Building components 1 to 5 | **about 3 hours** of agent time and **roughly $50** |
| Each issue the factory then runs | **$6 to $8**, before any fix cycle |
| A Phase 0 refusal | under a minute and well under a dollar |

Two things follow from those numbers and both are worth saying out loud:

- **Cached reads dominate cost by two orders of magnitude over output.** Context size
  drives the bill far more than how much the agent writes, which is why the premium model
  belongs in the planning slot and a cheaper one everywhere else.
- **Refusing is cheap and building is not.** If Phase 0 is borderline, refuse. The user
  loses a minute. Building the wrong factory costs them an afternoon and fifty dollars,
  and they find out in month two.

Offer to stop after the guidance layer if the user wants a smaller first commitment. That
alone is about an hour and it is useful even if they never turn a cron on.

## Before anything else: the three harnesses

People conflate these and then cannot debug them. Name them once, out loud, early:

| Harness | What it is | Who builds it |
|---|---|---|
| **The agent harness** | Claude Code, Codex, Pi - the loop that turns a prompt into edits | Vendor. Not your problem. |
| **The factory harness** | how work is planned, implemented, reviewed, gated, merged | **You.** Components 1-4. |
| **The validation harness** | the tools the agent uses to check its own work *as a user would* | **You, and it is most of the work.** Component 5. |

The factory harness decides what runs. The validation harness decides whether what
ran was worth keeping. Confusing the two is why people build an impressive DAG that
ships broken software on schedule.

---

## Construction order, and why it is not 1-2-3-4-5

The five components are numbered in **anatomy** order - the order you explain the
machine in. They are not built in that order. Build in this order instead:

| Build | Component | Why here |
|---|---|---|
| 0th | *(the PRD)* | Not a component. The input. Everything below reads it, and nothing below can be written honestly without it. |
| 1st | **Guidance layer** (#4) | An hour of markdown, and every other component reads it. Cheapest thing with the highest leverage. |
| 2nd | **Validation harness** (#5) | The long pole. Start it before you need it, because you will be wrong about it twice. |
| 3rd | **Workflow-driven repo** (#1) | Now the workflows have rules to obey and checks to pass. |
| 4th | **Deployment** (#3) | Close the loop to real users before you make it unattended. |
| **Last** | **The trigger** (#2) | The cron is the switch. It goes on only when 1-4 are proven. |

**The trigger is built last on purpose.** Turning on a scheduler is the moment the
repo becomes autonomous. Everything before it can be run by hand and inspected.
A factory whose dispatcher was built first is an unsupervised code generator that
nobody has ever checked.

State this to the user before starting. It reframes the whole project from "wire up
an agent" to "earn the right to walk away."

---

## Phase 0. The input, and the two ways to refuse

### 0a. There has to be a PRD

**The input to this skill is a PRD**: what is being built and why, at the level a
product manager writes it. Problem, users, scope, and above all **non-goals**. Call it
a spec, a brief, a product doc, an epic; the name does not matter and the content
does.

It deliberately does **not** contain the tech stack, the architecture, the data model,
or the file layout. Those are engineering decisions, they come later, and in a factory
they are usually decided on the first real run or already settled by the existing
codebase. Asking for them here is how a PRD turns into a spec nobody can change.

Read the PRD at `$prd` in full before asking a single question. Then map it:

| The PRD gives you | The factory builds from it |
|---|---|
| the problem, and why it is worth solving | the framing at the top of `MISSION.md` |
| who the users are | the person the E2E path is acted out as |
| MVP scope, the capability areas | what triage is allowed to accept |
| **non-goals** | **`MISSION.md` out-of-scope-forever, the most load-bearing list in the whole build** |
| success metrics | what the validation harness is ultimately arguing about |
| open questions, anything marked TBD | escalate as `needs-human`; never let the factory guess |

And be explicit with the user about **what the PRD does not give you**, because these
are exactly what the interview exists to produce:

- the E2E happy path, narrated as observable steps
- the protected list
- the two gates that have to be code rather than prompt
- the target autonomy level
- the stop button
- how work arrives, and where the factory runs

**Refuse if there is no PRD.** Say why: without a written scope, `MISSION.md` has no
out-of-scope list, and without that list every plausible feature request is arguably
in scope. The factory will build all of them. That is the single most common way an
autonomous repo goes wrong, and it cannot be patched later by a better prompt.

Point at the `plan-create-prd` skill in this repo and stop. Coming back in twenty
minutes with a real PRD is the fastest path, not a detour.

### 0b. The repo has to be observable

Inspect before asking anything. Look for: a test command that runs, a way to start
the app, existing CI, whether `gh` is authenticated, whether the repo is public, and
**whatever AI coding setup already exists** (`CLAUDE.md`, `AGENTS.md`, `.claude/`,
`.cursor/`, existing skills, commands, MCP config). That last one is the process to
encode, and it is usually already sitting there.

**Refuse, and say why, when:**

- **There is no way to observe the app working.** A library with no runnable surface
  and no test suite has nothing for component 5 to stand on. Fix that first.
- **The repo has no CI and no test command at all.** Start with a test suite. A dark
  factory built on zero checks is a machine for merging plausible code.
- **The user wants the agent to touch auth, payments, or anything with a blast
  radius they cannot absorb.** Those go on the protected list, not into the factory.

Saying no here is cheaper than saying it in month two. If any of these hold, offer
the smaller version: build the guidance layer and the harness now, and stop before
autonomy.

## Phase 1. Interview

Read `references/interview.md` and work through it. It is the whole skill in
question form: what each question is actually for, what a good answer sounds like,
and which vague answers to push back on.

Do not batch all questions into one message. Go component by component, and reflect
each answer back as a concrete artifact ("so the merge gate is: X") before moving on.

**The PRD has already answered part of this.** Do not re-ask what it answers. Read the
scope and the non-goals back as a proposal - *"so triage accepts anything in these
four areas and rejects these six, correct?"* - and spend the time on what it left
open. Re-asking a question the user already answered in writing is how an interview
loses the room in the first two minutes.

Three questions decide the project, so do not let any of them slide:

1. **"Describe the single most valuable thing a user does with this app, as a
   sequence of actions ending in something you can see on a screen."** That sequence
   is the E2E happy path. If the user cannot describe it, they cannot automate
   checking it, and the factory cannot be trusted.
2. **"Walk me through how you build a feature with AI today, step by step."** This is
   what gets encoded. Their planning step, their implementation step, their review
   step, the skills and MCP servers and rules files each one uses. The factory's
   workflows should be recognisably their process with the approvals taken out, not a
   generic pipeline they have to learn.
3. **"What level of autonomy do you actually want?"** Use the dial below. Most people
   say 5 and mean 3.

### The autonomy dial

| Level | What is automatic | What you still do |
|---|---|---|
| 0 | workflows exist | run them by hand |
| 1 | labelled issue → PR opens | review and merge everything |
| 2 | + validator runs and posts a verdict | merge everything |
| 3 | + validator **auto-merges** when every structural gate is green | write the issues, cut releases |
| 4 | + it triages its own issues, and a scheduled test files its own bugs | write the important issues |
| 5 | + it writes its own issues from the mission | nothing |

Build to level 1, prove it, then raise the dial one notch at a time. **Level 3 is the
real threshold** - it is the first level where code merges without a human reading it,
and it is the level the entire validation harness exists to justify.

## Phase 2. The guidance layer (component 4)

Read `references/guidance-layer.md`. Write three files from the templates:

- `MISSION.md` - what is being built, and what is **deliberately out of scope forever**
- `FACTORY_RULES.md` - how the agent behaves unsupervised, and the protected list
- `CLAUDE.md` / `AGENTS.md` - the conventions any project has, factory or not

**`MISSION.md` is a compression of the PRD, not a new document.** Draft it from the
PRD directly and show the user the diff in meaning, not just the file. The PRD's
non-goals become the out-of-scope list almost verbatim, and anything the interview
added on top gets marked as such so it is obvious later which constraints came from
the product and which came from making it unattended.

If a conventions file already exists, **keep it and pull the factory-only rules out of
it** rather than writing a new one over the top. That split is usually the single most
useful edit this phase makes to an existing repo.

The placement test, for every rule:

> Would you write this even with a human doing the work? → conventions file.
> Does it only exist because nobody is watching? → `FACTORY_RULES.md`.
> Is it about what the product is and is not? → `MISSION.md`.

**The one property that matters: the agent cannot amend the rules it is judged by.**
All three files go on the protected list, and a PR that touches them is auto-rejected
before anything else is evaluated. Enforce this in code, not in a prompt.

Run `scripts/factory_doctor.py --repo <path>` now. It will fail loudly, which is
correct - it is a checklist, and this is the start of working through it.

## Phase 3. The validation harness (component 5)

Read `references/validation-harness.md` in full before writing anything. It is the
longest reference because this is where factories actually fail.

The short version, which is not a substitute for reading it:

- **Climb the ladder:** static → unit → integration → **E2E as the real user** →
  visual judging → holdout scenarios → deterministic gate.
- **Draw the independence line after integration.** Everything below it is inside the
  agent's optimization loop, so given time it will satisfy whatever you measured
  rather than the thing you meant. More tests below the line is not the fix.
- **At least two gates must be code the model cannot talk past.** The merge itself,
  and a positive assertion that the app actually started. Everywhere else a "gate" is
  a prompt instruction, which is a suggestion with good manners.
- **Empty is not pass.** Assert how many checks *ran*, not just how many failed. A
  skipped check returns nothing, and nothing is not a failure.
- **The validator never learns how the code was written.** Only what was asked and
  what the code does now.

Deliverable: a `validate` entrypoint that a workflow can call, that emits explicit
markers, and a merge gate in bash that greps for them.

## Phase 4. The workflow-driven repo (component 1)

Read `references/automation.md` for the headless contract of each agent and how to
pick an orchestrator.

Pick **one** coding agent and **one** orchestrator. They are separate choices and the
user usually conflates them. The agent is genuinely swappable - every one of them
takes a prompt, runs headless, and returns an exit code. The orchestrator is not.

Write the workflows the factory needs. Minimum viable set is three: **implement an
issue**, **validate a PR**, **fix a PR**. Triage is a fourth and it is optional until
other people can file issues.

**Build these out of the process the user described in Phase 1, not out of a blank
page.** If they plan with one skill and implement with another, those are two nodes.
If a rules file or an MCP server is loaded at a particular step today, load it at that
step here. The interesting property of a factory is that it runs unattended, not that
it works differently, and a user who recognises their own workflow in the YAML will
trust it and maintain it. One that has to learn a new pipeline will not.

## Phase 5. Deployment (component 3)

Read `references/deployment.md`. It is short and it contains the single trap that
silently kills more factories than anything else: **GitHub does not trigger workflows
on commits made with the default `GITHUB_TOKEN`.** The agent commits, the deploy never
fires, nothing errors, and it takes a week to notice.

If the loop does not end at real users, the user has built a PR generator.

## Phase 6. The trigger (component 2)

Only now. Read the automation reference's dispatcher section.

**The dispatcher must be the dumbest, most deterministic thing in the system.** Not an
LLM deciding what to run - that hallucinates dispatches for work that does not exist.
Bash, a fixed priority order, and shared state that lives in something boring
(GitHub labels are enough; no database, no message bus).

Fixed priority, and this order is load-bearing:

1. fix a PR that needs fixing
2. validate a PR waiting for review
3. implement the highest-priority accepted issue
4. triage untriaged issues

**Finish in-flight work before starting new work.** Backwards, and the factory
triages forever while its own PRs rot.

## Phase 7. Prove it, then raise the dial

1. Run the walking skeleton by hand: one real issue, all the way to a PR you merge
   yourself. Do not proceed on a factory that has never completed a lap.
2. `python scripts/factory_doctor.py --repo <path> --audit` until it is clean.
3. Raise the autonomy dial one notch. Watch one full cycle at that level before the
   next notch.
4. Write `FACTORY.md` from the template - what was built, at which level it currently
   runs, and what has to be true before the next notch. **Link the PRD it was built
   from**, because when the product changes the mission has to change with it, and the
   factory will keep faithfully building the old scope until someone notices.

---

## Things to tell the user before they start

- **The PRD is now a live document, not a kickoff artifact.** In normal development a
  PRD goes stale and a human quietly compensates. Here nobody compensates: the factory
  builds the scope it was given until the scope is edited. Changing what the product
  is means editing `MISSION.md`, in a human commit, on purpose.
- **Instrument tokens on day one.** Cost projections for this are wrong by 10-20x in
  the same direction every time. One "fix an issue" run is far more agent sessions
  than it looks like from the outside.
- **Put one premium model in the planning slot and a cheaper one everywhere else.**
  Premium in one of the two slots that matter buys most of the quality of premium in
  both. Premium in zero slots is what actually costs you.
- **Leash every editing node to its own diff.** A node that can edit without a file
  scope will grow a six-file PR into eleven and introduce a bug on the way through.
- **Run `git check-ignore -v` on every config file before the first workflow that
  commits.** A `git add -A` inside a PR-create step publishes whatever was not
  ignored, and public means public.
- **The agent is the interchangeable part. The plumbing is not.** Credential expiry,
  cost cliffs, no default session timeout and sandbox egress are the same problems in
  every agent, and none of them solve it for you.

## Resources

- `references/interview.md`: the full question set, per component. Read in Phase 1.
- `references/guidance-layer.md`: the three-file split, the placement test, protected
  files, and how to write an out-of-scope list that does real work. Read in Phase 2.
- `references/validation-harness.md`: the ladder, the independence line, holdout
  design, structural vs prompted gates, and the failure modes. Read in Phase 3 before
  writing any check.
- `references/automation.md`: headless contracts for eight coding agents, orchestrator
  options and trade-offs, and the dispatcher rules. Read in Phases 4 and 6.
- `references/deployment.md`: deploy strategies, the `GITHUB_TOKEN` trap, and the
  GitHub scheduling gotchas. Read in Phase 5.
- `templates/`: `MISSION.md`, `FACTORY_RULES.md`, `orchestrator.sh`, `validate-gate.sh`,
  `FACTORY.md`. Copy and fill; never ship a template's placeholder text.
- `scripts/factory_doctor.py`: deterministic audit of a factory repo - protected
  files, holdout leaks, gate-is-code, empty-is-not-pass, ignored secrets, autonomy
  level. Run it in Phases 2 and 7. Never read its source into context; only its output.
- `scripts/_test_factory_doctor.py`: the doctor's own tests. Builds a healthy factory,
  breaks one thing at a time, and requires the doctor to notice. Run it after changing
  the doctor. A gate that has never failed is a gate nobody has tested, and that applies
  to this skill's gate too.
