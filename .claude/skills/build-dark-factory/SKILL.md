---
name: build-dark-factory
description: Take a PRD and build a dark factory around it - a repository that takes work in as an issue and ships validated code out with nobody at the keyboard - one component at a time, into the user's actual repo. Covers the five components in construction order - the guidance layer, the validation harness, the workflow-driven repo, deployment, and the trigger that makes it autonomous - and is agnostic about which coding agent runs underneath (Claude Code, Codex, Archon, the Agent SDK, Cline, Goose, Amp, Pi). It encodes the AI coding process the user already runs rather than replacing it. Requires a PRD as input and deliberately does not write one. Use when the user wants to build a dark factory, an autonomous or self-driving repository, a software factory, an agent that ships its own code, an unattended or overnight coding loop, or asks how to get to level 4 or level 5 of AI coding autonomy; and when they mention dark factory, lights-out coding, autonomous PRs, or a repo that maintains itself.
argument-hint: "[path/to/product.prd.md] [optional: path/to/repo]"
arguments: [prd, repo]
---

# Build a dark factory

**What the user typed:** $ARGUMENTS

> **Work out the PRD path and the repo path from that line yourself, and do not print a
> parse you have not checked.** The positional split is on whitespace, so anyone who
> types a sentence ("build a dark factory for my repo at C:\code\thing") gets the first
> two *words* as the two paths - three separate test runs opened with `PRD: Build` and
> `Repo: a`, which is a broken-looking first contact for a parse the skill then quietly
> recovered from anyway.
>
> So: read the line, find the thing that looks like a `.md` PRD and the thing that looks
> like a directory, and confirm both back to the user as one sentence before Phase 0. If
> only one is given, work out from its extension which it is and ask for the other. If
> the PRD path does not exist, say so and stop - that is Phase 0a, reached early.

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

## Two things that shape every decision below

<!-- NO COST OR DURATION ESTIMATES IN THIS FILE, and none in the opening message. They
     used to be a table here that the skill was told to recite before the interview, and
     every run opened by quoting figures at someone who had just asked for a dark factory.
     People know a build like this takes a while and costs something; being warned about
     it reads as hedging, and it buries the first useful sentence. Do not reintroduce
     them. (Also: never write a `$` followed by a digit in this file - it renders as a
     positional argument substitution and silently eats the surrounding text.) -->

- **Cached reads dominate cost by orders of magnitude over output.** Context size drives
  the bill far more than how much the agent writes, which is why the premium model belongs
  in the planning slot and a cheaper one everywhere else.
- **Refusing is cheap and building is not.** If Phase 0 is borderline, refuse. Building
  the wrong factory is discovered in month two, and it cannot be patched by a better
  prompt.

Offer to stop after the guidance layer if the user wants a smaller first commitment. It is
useful even if they never turn a cron on.

## Before anything else: the three harnesses

People conflate these and then cannot debug them. Name them once, out loud, early:

| Harness | What it is | Who builds it |
|---|---|---|
| **The agent harness** | Claude Code, Codex, Pi - the loop that turns a prompt into edits | Vendor. Not your problem. |
| **The factory harness** | how work is planned, implemented, reviewed, gated, merged | **`templates/runner/`.** Components 1-4, mostly copied. |
| **The validation harness** | the tools the agent uses to check its own work *as a user would* | **You, and it is most of the work.** Component 5. |

The factory harness decides what runs. The validation harness decides whether what
ran was worth keeping. Confusing the two is why people build an impressive DAG that
ships broken software on schedule.

That distinction is also what decides which parts of this ship as a template:

> **The factory harness is templatable. The validation harness is not.**

The dispatcher, the runner, the gate, the guard, the merge and the state machine are the
same in every factory, so they are in `templates/runner/` with their scars intact. What
"working" means for this app is the one thing nobody can write in advance, so component 5
is yours - and it is where the week should go.

---

## Construction order, and why it is not 1-2-3-4-5

The five components are numbered in **anatomy** order - the order you explain the
machine in. They are not built in that order. Build in this order instead:

| Build | Component | Why here |
|---|---|---|
| 0th | *(the PRD)* | Not a component. The input. Everything below reads it, and nothing below can be written honestly without it. |
| 0.5th | *(the walking skeleton)* | **Greenfield only.** Not a component either, and deliberately tiny: the thinnest slice that yields one assertable behaviour. Component 5 cannot be written against software that does not exist. See Phase 0c - the danger is building the MVP here rather than a slice. |
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

**Decide which of two repos this is by LOOKING - you have just inspected it. Do not ask.**
The refusals below are written for one of them and misfire badly on the other, and the
difference is visible in the file list:

- **Brownfield** - source files that are not scaffolding. The refusals apply as written.
- **Greenfield** - a PRD, maybe a `.gitignore`, `.claude/`, a README, and nothing that
  runs. **Both refusals are then trivially true and neither carries any signal.** Go to
  0c; do not refuse.

Say which one you concluded and why, in one line, so the user can correct it: *"No source
files outside docs/ and .claude/, so I am treating this as greenfield."* A wrong guess is
cheap to fix and asking costs a question you already have the answer to.

**Refuse, and say why, when:**

- **There is no way to observe the software working** - nothing to start, nothing to
  invoke, and nothing importable either. Component 5 has nothing to stand on.

  **This is about software that cannot be observed, not software that does not exist
  yet.** A greenfield repo trips this and the next bullet by definition, and refusing it
  would be refusing the premise rather than a defect. See 0c.

  **A library is not this case.** The harness ships three drivers - `http` (a server),
  `cli` (a command), and `library` (no process at all; the E2E imports it and calls it) -
  and `APP_STARTED driver=library` means the import succeeded, which is the same claim a
  server answering makes. This bullet used to open with the words "a library", and a test
  run against a pure Python library nearly hard-refused a repo the scaffold supports out
  of the box. Read `templates/harness/appproc.py` before deciding something is
  unobservable.
- **The repo has no CI and no test command at all.** Start with a test suite. A dark
  factory built on zero checks is a machine for merging plausible code.
- **The user wants the agent to touch auth, payments, or anything with a blast
  radius they cannot absorb.** Those go on the protected list, not into the factory.

Saying no here is cheaper than saying it in month two. If any of these hold, offer
the smaller version: build the guidance layer and the harness now, and stop before
autonomy.

### 0c. Greenfield: the walking skeleton, and it is SMALL

**This is the common case, not the exception.** Most people want a dark factory at the
start of a project, which is also the best time to build one - the guidance layer is
cheapest to write when nothing contradicts it yet, and the sim/presentation split below is
free before there is code and expensive afterwards.

Greenfield is **not** a refusal. But it does mean component 5 has nothing to stand on
today, and no ordering of the phases fixes that. Something has to exist first.

#### The skeleton is the thinnest vertical slice, NOT the MVP

This is where a greenfield build goes wrong, and it goes wrong in the same direction every
time: the agent proposes building the core of the product so the harness has something to
test, the user agrees because it sounds necessary, and now the interesting, risky work has
been done by hand and the factory is left with the leftovers. That inverts the entire
point.

**Build the smallest slice that produces one observable, assertable behaviour end to end.**
For a game: one enemy, one hit, one damage number, persisted across a restart. For a
service: one endpoint that writes one row and reads it back. For a CLI: one command with
one flag that changes one line of output.

The test is not "is this useful" - it is **"can an E2E assert something a user would
notice?"** If yes, stop building and start building the factory. Everything else in the
MVP is issues, and the factory building them is the thing you are here for.

State the size explicitly before starting, and say what you are deliberately leaving out:
*"I am building one horn level, one wave, one damage number and a save file. Not the
reward curve, not the elemental interactions, not wave composition - those are issue
one, two and three."*

#### The reachability constraint, decided NOW

**The harness reaches software exactly three ways** - `http` (a server), `cli` (a command),
`library` (imported and called). Read `templates/harness/appproc.py`. A rendered window, a
game loop, a canvas, a native UI is **none of them**.

So on greenfield this stops being an architecture preference and becomes a hard
requirement: **the logic must live behind a headless, scriptable surface that an E2E can
drive.** Simulation separate from rendering. Domain separate from view. If the rules only
exist inside engine nodes and a render loop, there is nothing to assert and the factory
cannot be built at level 3 - not because the skill is limited, but because nothing can
check the work.

Say this before any code is written. It is nearly free now and it is a rewrite later.

#### The factory's scope is strictly smaller than the MVP

Some MVP items are not machine-validatable and never will be: *"combat feels good"*,
*"the escalation is visibly and audibly different"*, *"a first-time player understands
it"*. Those are feel, presentation and readability.

Name them out loud, write them into `MISSION.md` and `FACTORY_RULES.md` as **permanently
human**, and be clear that the factory owns the simulation layer rather than the product.
That is still a large and valuable surface - usually most of the actual risk - but
pretending it is the whole MVP is how you end up with a green factory shipping a game
nobody wants to play.

#### Then, in order

1. **The skeleton** (small, above), with a test suite and one E2E that drives it.
2. Everything else exactly as the construction order says: guidance layer → validation
   harness → workflow repo → deployment → trigger.

#### Put the fork to the user with the question tool

This is a real decision with three known answers, so use `AskUserQuestion` (or the
equivalent) rather than a paragraph, and **recommend the first**:

1. **Build the thin skeleton now, then the factory on it** *(recommended)* - name the
   slice and name what you are leaving out, so "recommended" cannot be read as "I will
   build your MVP".
2. **Guidance layer and scaffolds only** - `MISSION.md`, `FACTORY_RULES.md`, `CLAUDE.md`,
   plus `runner/` and `harness/` copied in with the contract documented and the assertions
   left empty. The user builds the skeleton; you resume at component 5. A real option, not
   a consolation: the `MISSION.md`/`FACTORY_RULES.md` pair earns its keep in interactive
   work whether or not a cron is ever turned on.
3. **Stop - architecture first** - when the PRD defers the thing 0c's reachability
   constraint depends on, and the user would rather settle it before code exists.

## Phase 1. Interview

Read `references/interview.md` and work through it. It is the whole skill in question
form: what each question is actually for, what a good answer sounds like, and which
vague answers to push back on.

**It is three rounds, not a questionnaire.** Round 1 is the three questions below, asked
one at a time before anything else. Round 2 is six that only the user can answer. Round 3
is a **single message** listing every remaining setting with its default already filled
in, asking what to change.

**Propose defaults; do not interrogate.** The protected paths, the poll interval, the
concurrency, the stop button, the PR cap, the model routing and the holdout location all
have working defaults that ship in `config.sh` and the templates. Asking for them
open-ended makes the user do the skill's homework and buries the questions that matter.
"I am going to protect these five paths, plus your CI config - anything else?" is a better
question than "which files must the agent never touch?", and it cannot be answered wrong
by someone who has never built one of these.

**The PRD has already answered part of this.** Never re-ask what it answers. Read the
scope and the non-goals back as a proposal - *"so triage accepts anything in these four
areas and rejects these six, correct?"* - and spend the time on what it left open.
Re-asking something the user already wrote down is how an interview loses the room in the
first two minutes.

Reflect each answer back as a concrete artifact ("so the merge gate is: X") before moving
on.

**Use the agent's own question tool where one exists** - `AskUserQuestion` in Claude Code,
and whatever the equivalent is elsewhere. It renders real options with a recommendation
instead of asking someone to read a paragraph and type a reply, and a user picking from a
list answers questions they would have skipped. Fall back to prose where there is no such
tool; nothing below depends on it.

**But only for decisions among options you already know.** The split is not stylistic:

| Use the question tool | Ask in prose |
|---|---|
| the autonomy dial (R1.3) | the user journey (R1.1) |
| the greenfield fork (Phase 0c) | how they build a feature with AI today (R1.2) |
| **all of Round 3** - one call, multi-select, "which of these do you want to change?" | the never-ever list (R2.1), the invariants (R2.2) |
| the severity dial (R2.6), when the options are real | the harness questions (R2.3, R2.4, R2.5) |

The prose column is not a limitation of the tool, it is the point of those questions.
Offering options for "describe the most valuable thing a user does" replaces the answer
you need with a menu of guesses you wrote - and that answer becomes `e2e.py`, the only
check with real authority. A picker there is worse than no question.

**Two rules apply to every question, in both columns:**

1. **Always carry a recommendation - never hand someone a blank page.** In a picker, mark
   exactly one option `(Recommended)` and put it first. In prose, draft the answer **from
   their PRD and their repo**, cite where you got it, and ask them to correct it: *"from §6
   the journey looks like X - is that the most valuable one, and what am I missing?"* A
   question with a draft attached is a two-second correction; the same question blank is
   homework, and homework is where interviews get abandoned. Where a recommendation would
   be dishonest, say *that* rather than inventing confidence.
2. **Offer to explain the hard parts before they answer.** Holdout, mutation set, ratchet,
   independence line, structural gate - these are obvious only after you have built one of
   these, and a user who does not want to admit they have not heard of a holdout will
   guess. In a picker, add an *"Explain this first"* option. In prose, lead with one
   sentence of plain English. `interview.md` has a one-breath explanation for each term;
   use those words, and do not lecture.

Round 1 - three questions decide the project, so do not let any of them slide:

1. **"Describe the single most valuable thing a user does with this app, as a
   sequence of actions ending in something you can see on a screen."** That sequence
   is the E2E happy path. If the user cannot describe it, they cannot automate
   checking it, and the factory cannot be trusted.
2. **"Walk me through how you build a feature with AI today, step by step."** This is
   what gets encoded. Their planning step, their implementation step, their review
   step, the skills and MCP servers and rules files each one uses. The factory's
   workflows should be recognisably their process with the approvals taken out, not a
   generic pipeline they have to learn.
3. **"What level of autonomy do you actually want?"** Use the dial below. **Recommend
   level 3, and build for it unless they say otherwise.** People often say 5; 5 means
   the factory writes its own issues from the mission, which is a different product
   decision and not the one they are asking for.

### The autonomy dial

| Level | What is automatic | What you still do |
|---|---|---|
| 0 | workflows exist | run them by hand |
| 1 | labelled issue → PR opens | review and merge everything |
| 2 | + validator runs and posts a verdict | merge everything |
| 3 | + validator **auto-merges** when every structural gate is green | write the issues, cut releases |
| 4 | + it triages its own issues, and a scheduled test files its own bugs | write the important issues |
| 5 | + it writes its own issues from the mission | nothing |

**Level 3 is the default. Build for it.**

It is the first level where code merges without a human reading it, and it is the whole
point: a factory that stops at 2 is a code generator with a queue, and the person is still
the bottleneck they were trying to remove. Everything difficult in this build - the
holdout, the mutation set, the ratchet, the two gates that must be code - exists to earn
level 3, so building for anything less means doing the hard part and then not using it.

Levels 0 to 2 are **stages on the way**, not destinations. Ship them in order, prove a lap
at each, and keep going to 3. The dial is enforced in `orchestrator.sh` and
`factory_doctor` blocks 3 outright until a holdout exists, so "build for 3" cannot turn
into "switch on 3" before the evidence is there.

Stop below 3 only when the user has a specific reason - an unmovable review requirement, a
blast radius they cannot absorb, a harness they do not yet trust. That is a legitimate
choice and it should be their choice, made out loud, rather than the default that happens
because nobody raised the dial.

Above 3 is a different question, not a further step: 4 hands over what gets built and 5
hands over what to build. Neither is implied by wanting the merge automated.

## Phase 2. The guidance layer (component 4)

Read `references/guidance-layer.md`. Write three files from the templates:

- `MISSION.md` - what is being built, and what is **deliberately out of scope forever**
- `FACTORY_RULES.md` - how the agent behaves unsupervised, and the protected list
- `CLAUDE.md` / `AGENTS.md` - the conventions any project has, factory or not
  (template in `templates/CLAUDE.md`; if one already exists, split it rather
  than replacing it)

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
longest reference because this is where factories actually fail. **Its opening section
is the contract the runner expects** - the entrypoint, the markers, the append rule, and
the `--quick` subset. Read that even if you skim the rest, because getting the append
rule wrong breaks every marker assertion for a reason that looks like your code.

**Start from the scaffold, then delete its assertions.**

```bash
cp -r templates/harness <repo>/harness
```

`templates/harness/` is the plumbing, and only the plumbing. **It is not
Python-only and not web-only**: every command lives in `harness.config.json`,
and the driver is `http`, `cli` or `library`. Proven on a Python HTTP service, a
Node CLI (five config values changed, nothing else) and a Python library.

What it gives you: the step ladder, the markers
with counts, the step-namer, the `--quick` subset, and an app-process manager that binds
a dynamic port, waits for health and tears down on every path. It runs out of the box.

That split is not a hedge, it is the finding. Two people built this harness from scratch
without a scaffold, independently, on different products, and wrote the *same* file -
down to both inventing a "zero tests discovered is not a pass" guard. The plumbing is
determined by the marker contract, not by the app.

**Every assertion in `e2e.py` is a worked example and all of it should be deleted.**
The same goes for `.factory/holdout/run.py` and `harness/mutations/defects.json`.
Each carries a marker line you delete when the content becomes yours, and
`factory_doctor` **blocks at level 2+** until you do - because a gate that is green
about the template's sample product is worse than no gate at all.

The interview produces all three: **R1.1** the journey, **R2.5a** the composed
scenarios the builder cannot read, **R2.5b** the defects that must be caught. What
a user would notice is the part nobody can write for you, it is the answer to R1.1, and
it is where the week goes. The scaffold buys you the day; it does not buy you the week.

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

Read `references/automation.md` for the headless contract of each agent and what is in
the runner.

**Copy the runner; do not write one.** `templates/runner/factory/` is a working
execution layer - dispatcher, runner, structural gate, protected-path guard, merge,
deploy, state machine, seven node prompts. Its `README.md` is the install order.

```bash
cp -r templates/runner/factory <repo>/factory
mkdir -p <repo>/.factory/{locks,holdout,runs}
```

Then three edits, and the third is the real work of this phase:

1. **`factory/config.sh`** - the agent, the models, and `FACTORY_VALIDATE_CMD` pointing
   at the harness from Phase 3. Every project-specific value lives here; if you are
   editing another script to change a path, that is a bug in `config.sh`.
2. **`factory/guard.py`** - the protected list. Seed it, do not just accept what the
   interview returned.
3. **`factory/prompts/*.md`** - **rewrite these as the user's own process.** This is
   where Phase 1's R1.2 answer lands. If they plan with one skill and implement with
   another, those are two nodes. If a rules file or an MCP server is loaded at a
   particular step today, load it at that step here.

The interesting property of a factory is that it runs unattended, not that it works
differently. A user who recognises their own workflow in these prompts will trust it and
maintain it; one who has to learn a new pipeline will not. **The prompts are the
personalisation. The plumbing is not** - and that is exactly why the plumbing ships as a
copy and the prompts ship as a skeleton with the decisions marked.

If the user has a workflow engine they already run (Archon, a YAML DAG, GitHub Actions,
an Agent SDK program), the runner is still the reference for *what the nodes must do* -
the fresh-context boundary, the tool allowlists, the holdout deny, the commit step, the
gate. Port those properties; do not port the bash.

## Phase 5. Deployment (component 3)

Read `references/deployment.md`. It is short and it contains the single trap that
silently kills more factories than anything else: **GitHub does not trigger workflows
on commits made with the default `GITHUB_TOKEN`.** The agent commits, the deploy never
fires, nothing errors, and it takes a week to notice.

If the loop does not end at real users, the user has built a PR generator.

## Phase 6. The trigger (component 2)

Only now. Read `references/setup.md` in full and the automation reference's dispatcher
section.

`references/setup.md` is the unglamorous half nobody writes down: prerequisites, cron and
systemd and Task Scheduler, the `.gitattributes` line-ending pin, `core.longpaths`,
`PYTHONIOENCODING`, the `git check-ignore` pre-flight, credential expiry, and how to test
the stop button on purpose. Every item on it broke a real factory. You can have five
perfect components and a machine that has never completed a lap because line endings were
rewritten on checkout.

The dial itself is already enforced in the runner: `orchestrator.sh` reads
`FACTORY_AUTONOMY` and refuses each action below its level, so raising it is a deliberate
act rather than a note in a file.

**Say this out loud, because almost everyone arrives with the wrong model: nothing
pushes.** Filing an issue does not trigger a run. There is no webhook and there is not
meant to be one - a scheduler wakes on a timer, reads the state, and dispatches at most
one thing. An issue filed at 09:01 waits for the next tick. A push trigger that breaks
fails *silently* and looks exactly like a factory with nothing to do; a poll that breaks
is a poll you can see not running.

Arm it with the installer rather than by hand, and note that it **refuses while the dial
is at 0** - a scheduler at level 0 wakes up forever and correctly does nothing, which is
how people convince themselves a factory is running when it has never completed a lap:

```bash
bash factory/install-trigger.sh --status     # what is armed right now
bash factory/install-trigger.sh --install    # cron, systemd timer, or Task Scheduler
bash factory/install-trigger.sh --remove
```

Then run `factory_doctor` once more. It now checks whether a scheduler is actually armed,
because a fully built factory with nothing scheduled audits identically to a running one.

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

## Phase 7. Prove it, then get to level 3

**The target is 3 and the job is not finished until the dial is there.** These steps are
the evidence that earns it, not a ladder to stop partway up.

1. Run the walking skeleton by hand: one real issue, all the way to a PR you merge
   yourself. Do not proceed on a factory that has never completed a lap.
2. `python scripts/factory_doctor.py --repo <path> --audit` until it is clean. It refuses
   level 3 while there is no holdout, which is the check that decides whether the rest of
   this was real.
3. Raise the dial to 1, then 2, watching one full cycle at each - then **raise it to 3**.
   Stopping at 2 leaves a person merging every PR, which is the bottleneck the whole build
   was for. If the user chooses to stop below 3, write down in `FACTORY.md` what would
   have to be true to go further, so it is a decision with a way out of it rather than a
   dial nobody touched again.
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
- `references/setup.md`: prerequisites, the platform tax, scheduling, and turning it on.
  Skim in Phase 0b to refuse early; read in full in Phase 6.
- `templates/`: `MISSION.md`, `FACTORY_RULES.md`, `FACTORY.md`. Copy and fill; never ship
  a template's placeholder text. There is no separate `orchestrator.sh` or
  `validate-gate.sh` sketch any more - they were strictly worse duplicates of the real
  ones in `templates/runner/factory/`, and shipping a second definition of the pipeline is
  the exact failure `automation.md` warns about. The one nobody runs is the one that
  drifts.
- **`templates/runner/`**: the working execution layer, ~3,000 lines, copied into the
  repo in Phase 4. Read its `README.md` for the install order and the list of things that
  are load-bearing. Its comments record real incidents - a factory rebuilt from the design
  alone rediscovers every one of them, unattended, in production.
- **`templates/harness/`**: the validation harness's *plumbing*, copied in Phase 3. Runs
  out of the box; every assertion in it is an example to delete. The factory harness is
  templatable and so is the harness's plumbing - what is not templatable is what "working"
  means for this product, and that is the whole of component 5.
- `scripts/factory_doctor.py`: deterministic audit of a factory repo - protected
  files, holdout leaks, gate-is-code, empty-is-not-pass, ignored secrets, autonomy
  level. Run it in Phases 2 and 7. Never read its source into context; only its output.
- `scripts/_test_factory_doctor.py`: the doctor's own tests. Builds a healthy factory,
  breaks one thing at a time, and requires the doctor to notice. Run it after changing
  the doctor. A gate that has never failed is a gate nobody has tested, and that applies
  to this skill's gate too.
