# The interview

**Three questions decide the project. Six more only the user can answer. Everything else
is a default they confirm.**

That is the whole shape, and it is deliberate. The first version of this file asked 28
open questions in component order, and it failed in a specific way: it opened by asking
what someone would spend per issue - a question its own notes admitted almost nobody can
answer - and it asked, open-ended, for things the templates already ship a right answer
for. Asking someone to invent the protected-path list, the poll interval and the holdout
directory teaches them the interview is homework rather than a conversation, and the ones
that actually decide the build arrived a dozen questions later, after the room was lost.

**Proposing a default is not a shortcut, it is a better question.** "I am going to protect
these five paths, plus your CI config - anything else?" gets a more useful answer than
"which files must the agent never touch?", takes ten seconds, and cannot be answered
wrong by someone who has not built one of these before.

> **Read the PRD before asking anything, and never ask what it already answers.** Play its
> scope and non-goals back as a proposal - *"so triage accepts work in these four areas
> and rejects these six, correct?"* - and spend the time on what it left open. Making
> someone retype a document they already wrote is the most common way a well-designed
> interview fails.

**Use the agent's own question tool where one exists** - `AskUserQuestion` in Claude Code,
or the equivalent. Each question below is marked **[PICKER]** or **[PROSE]**, and the mark
is not a style note:

- **[PICKER]** - a decision among options that are already known. The tool renders them
  with a recommendation, and someone picking from a list answers things they would have
  skipped in a wall of text. Every default in Round 3 is one call, multi-select.
- **[PROSE]** - the answer has to be in the user's own words, and offering options
  replaces it with a menu of your guesses. R1.1 becomes `e2e.py`, the only check with real
  authority; a picker there is worse than no question at all.

Where there is no such tool, ask in prose and mark the [PICKER] ones by listing the
options with your recommendation first. Nothing here depends on the tool existing.

**But degrade Round 3 differently, because a table is not a fallback for a widget.** With
a picker, ten defaults is ten seconds and no reading. Rendered as prose it is a wall, and
a real run produced exactly the failure the picker exists to prevent: the user skimmed it
and said *"I don't have opinions on any of that, you pick"* - which loses the two or three
she did have a view on. So with no picker available:

> **Ask about three. State the rest as decisions you have made.** Pick the three most
> likely to matter to *this* user - usually the protected paths, the notification channel,
> and the stop button - and put them as three short questions. List the other seven as a
> short paragraph of things you have set, with an invitation to change any of them. A
> decision they can object to gets read; a table they must audit does not.

## Two rules that apply to every question below

### 1. Always carry a recommendation. Every question, including the prose ones.

**Never hand someone a blank page.** A question with no proposed answer is homework; the
same question with a draft attached is a two-second correction. This is the single biggest
difference between an interview that finishes and one that gets abandoned in the middle.

- **[PICKER]** - mark exactly one option `(Recommended)` and put it first. Say why in its
  description, in one line.
- **[PROSE]** - draft the answer **from their own PRD and their own repo**, show it, and
  ask them to correct it. *"From §6 of the PRD, the journey looks like: open the app →
  shorten a URL → follow the short link → land on the original. Is that the most valuable
  one, and what am I missing?"*

The prose rule has one hard condition: **the draft must be visibly derived from their
material, not invented.** Cite where it came from. An invented draft anchors them onto
your guess, which is the exact failure that makes a picker wrong for R1.1 - the difference
is that a draft from their PRD is their own answer played back, and they will happily
overwrite it. If you have nothing to derive a draft from, say so and ask open.

Where a recommendation would be dishonest - a genuine coin-flip, or something only they
can know - say **that** instead of inventing confidence: *"I have no basis for a
recommendation here; it depends on X."* That is still better than silence.

### 2. Offer to explain the hard parts, before they answer

Several of these questions use vocabulary that is obvious only after you have built one of
these. A user who does not want to admit they have not heard of a holdout will guess, and
a guessed answer becomes an unenforceable rule.

So **offer the explanation rather than waiting to be asked**. In a picker, add an explicit
option - *"Explain this first"* - as a real choice; it costs one line and it is the option
that gets picked more than you would expect. In prose, put one sentence of plain English
in front of the question and offer to go deeper.

The terms that need it, and how to say each in one breath:

| Term | One breath |
|---|---|
| **holdout** | Tests the AI writing the code is not allowed to read, so it cannot tune its work to pass them. It is the only honest reason to merge code nobody reviewed. |
| **mutation set** | You break the code on purpose, in specific ways, and check the tests notice. It measures your *tests*, not your code. Until you have run it you do not know your tests can fail at all. |
| **the independence line** | The line between checks the AI can see and checks it cannot. Everything below it is inside its optimisation loop; given enough tries it satisfies those rather than the thing you meant. |
| **the ratchet** | A floor on how many checks must run, kept in a file the AI is not allowed to edit. It stops quality being quietly traded away one deleted assertion at a time. |
| **a structural gate** | A merge decision made by code, not by a model summarising its own work. Two of them must be code, or "it looks fine to me" is the whole gate. |
| **the autonomy dial** | How much runs without you, 0 to 5. Level 3 is the one that matters: code merges without a human reading it. |
| **E2E / the happy path** | One journey through your software the way a real user takes it, asserted end to end. Not a test per function - the single most valuable thing someone does. |
| **`APP_STARTED` / proof it is running** | One specific thing your software says when it is genuinely up - a page that returns a known word, a command that prints a version. Without it, software that crashed on startup and software that is fine look identical to the checks, and "could not test it" gets counted as "nothing wrong". |

**`APP_STARTED` is on that list because a real run showed it being rubber-stamped.** The
user said *"sure, whatever you said, known address known response, fine"* - and it is one
of only two gates that must be code. It sounds obvious to anyone who has run a service and
means nothing to anyone who has not. Explain it before asking R2.3, not after.

Use those words when the user is not technical, and use the precise ones when they are.
Do not lecture: one breath, then the question, then offer more.

**Reflect every answer back as a concrete artifact** before moving on - "so the merge gate
is: the PR merges only if `APP_STARTED` and `E2E_PASSED` both appear in the run output."
The point of the interview is to turn opinions into things that can be written down and
run.

**Push back on vague answers.** A vague answer becomes an unenforceable rule, and an
unenforceable rule is worse than none: it reads like a guarantee.

### 3. Say where the finish line is, and say it again around question eight

Attention runs out before the questions do. In a real run the user asked *"how much longer
is this? I'm quite keen to see something on a screen"* immediately after R2.4 - question
eight of twelve, and two questions before R2.5b, which is the one that produces the
mutation set and the one you least want answered by somebody who has stopped thinking.

The recovery that worked was **a named finish line plus a promise about the deliverable**:

> "Two more real questions, then one list you skim and click through. Then we build. And
> I'll say exactly what the first thing on the screen will be before I write anything."

Not "a few more". A count they can hold. Say it when you start Round 2, and say it again
if you sense drift - a user who keeps typing after they have disengaged is worse than one
who says they are bored, because the answers keep coming and they stop being true.

---

## Round 1 - the three that decide the project

Ask these first, one at a time, before any component discussion. If someone walks away
after three questions, these are the three you needed.

> **On a greenfield repo, R1.1 is about the SKELETON, not the product.** Ask for the
> journey the way it is written, because it defines what the product is for - then say
> which one-slice version of it you are building first, and that everything else in it is
> issue one, two and three. See Phase 0c. Getting this wrong is the standard greenfield
> failure: the agent builds the MVP by hand so the harness has something to test, and the
> factory inherits the leftovers.

### [PROSE] R1.1 - "Describe the single most valuable thing a user does with this app, as a sequence of actions ending in something you can see."

*The* question. The answer becomes the E2E happy path, which is the only check with real
authority, and it is what `harness/e2e.py` gets rewritten into.

Force it concrete. Not "users can search." Instead: *open the app → sign in as a test user
→ type a query with a known answer → the response streams in → it renders with a citation
→ click the citation → a modal opens at the right timestamp.*

**Bad answer:** any description that never mentions something observable. If it cannot be
observed it cannot be asserted, and the agent will claim it works.

### [PROSE] R1.2 - "Walk me through how you build a feature with AI today, step by step."

Let this run long. **The workflows are that process with the approvals removed, not a new
pipeline the user has to learn.** Most people have more process than they think and have
never written it down. Draw it out and name each step:

- **Planning.** Do they write a plan first? From what? Does anything read it back?
- **Implementation.** One pass, or sliced? What decides the slice?
- **Review.** What do they look at, and what makes them send it back?
- **The tooling at each step.** Which skills, commands, subagents, MCP servers and rules
  files load where. Get specifics, then go and look - `CLAUDE.md`, `AGENTS.md`, `.claude/`
  and `.cursor/` are usually already in the repo, and that is the answer sitting there.
- **A named framework, if any.** Spec Kit, BMAD, a PRP framework, an in-house SDLC. If
  they have one, it *is* the answer, and the job is to encode it faithfully.

Then say it out loud: *every one of those steps becomes a node, and the only difference is
that nobody clicks approve between them.*

Follow up with the sharp version: **"which of those steps are you actually reviewing, and
which do you already rubber-stamp?"** The rubber-stamped ones are free autonomy and go
first. The ones they genuinely read are where the harness has to earn its place - and that
answer is what the harness is *for* on this specific project.

**Bad answer:** *"I just use Claude Code."* Push once for the sequence - most people have
more process than they think.

**But some genuinely have none, and pushing at them is the exam this interview exists to
avoid.** A career-changer's honest answer is *"I describe the thing, paste it in, run it,
paste the error back."* There is no hidden sequence to excavate; saying "everyone has one"
to that person just tells them they are answering wrong. Ask once, believe the second
answer, and **reframe instead of digging**:

> "That is a real process and it is the one we are automating. The difference is not that
> your steps are wrong - it is that right now the only check is you looking at the result.
> So the questions that follow are about building checks that are better than that look,
> because that look is what disappears."

Then take the workflows from the templates as a starting point rather than from them, and
say that is what you are doing. A user with no process needs a proposal, exactly like
every other question here: it is the one case where the default prompts in
`templates/runner/factory/prompts/` are the answer rather than a worked example.

### [PICKER] R1.3 - "Are you willing to have code merge to main that no human has read?"

Ask it exactly that way, then show the dial. **Level 3 is the recommendation - say so, and
treat it as where the conversation starts.** People often say 5; 5 means the factory writes
its own issues from the mission, which is a separate product decision.

Expect a pause. That pause is the whole build in one question, and the holdout, the
mutation set and the ratchet all exist to make the answer yes.

Then one follow-up that calibrates everything downstream: **"what is the blast radius of a
bad merge?"** A personal side project, an internal tool, or something with real users and
real money. This decides how much of the harness must be structural rather than prompted,
and how long the protected list is.

If the answer to the first part is a considered no, level 2 is legitimate - but write into
`FACTORY.md` what would have to be true to go further, so it stays a decision rather than a
dial nobody touched again. A factory parked at 2 still has a person merging every PR, which
is the bottleneck the build was for.

---

## Round 2 - what only they can answer

Six. Each produces something no template can guess. Spend the time here, especially on the
harness ones.

### [PROSE] R2.1 - "Name five things you would reject even if a user asked nicely and the code would be easy."

*The most valuable list in the build, and the reason a PRD is required.* Start from the
PRD's **non-goals**, which are usually most of the way there, and read them back. Then push,
because a PRD's non-goals keep a team focused this quarter, and this list has to hold
against an agent reading a stranger's feature request at three in the morning.

Prompt with categories until there are five or more: new data sources, new providers,
payments, mobile, social features, public API, integrations, alternate input modes.

**The distinction to hold on to: a PRD says "not now", `MISSION.md` has to say "not ever".**
Walk the non-goals one at a time and sort them. "Not now" items belong in the backlog and
must **not** appear as out-of-scope, or the factory will reject that work when its turn
comes.

**Bad answer:** *"anything that doesn't fit."*

### [PROSE] R2.2 - "What must always stay true, even if an issue argues well for changing it?"

Hard invariants - a rate limit, an auth requirement, a privacy property, a single-tenant
assumption. Different from out-of-scope items: those are features you will not add, these
are properties that cannot be edited. They go in **both** `MISSION.md` and
`FACTORY_RULES.md`, deliberately, because the file read at reject time has to contain the
rule.

### [PROSE] R2.3 - "How do you check a change did not break things today, and what tells you the app is actually running?"

Two halves, one conversation.

The first: whatever they say - even *"I click around for two minutes"* - is the spec for
the automation. Get the click-around narrated step by step.

The second is one of the two gates that **must be code**: a health endpoint returning a
known payload, a port accepting connections, a specific log line. It becomes the
`APP_STARTED` marker. Without it, a crashed app produces a validator that cheerfully
reports "not testable" and something downstream counts that as fine.

**Bad answer to the second half:** *"it starts up."* A process that starts, hangs and
returns zero is indistinguishable from a healthy one.

### [PROSE] R2.4 - "If someone wanted to make the tests pass without actually fixing anything, what is the easiest cheat?"

Ask it in those words - it is a question about their code, not about agents, and people
answer it well. The answers are the holes: delete a test, weaken an assertion, mock the
thing under test, catch and swallow, special-case the test input.

Each answer becomes a rule in `FACTORY_RULES.md` and, where possible, a structural check.

### [PROSE] R2.5 - the two harness questions, and they are the hard part

Do not use the word "holdout" in the question. Ask the plain version, then explain what it
becomes.

**a) "Name three things that must be true when several features are used TOGETHER - the
kind of thing that works fine in isolation but breaks when combined."**

Push for **composition**, because that is where the real failures are. The dominant failure
mode in unattended coding is not cheating, it is **feature isolation**: components that are
individually correct and never work together. Unit tests test features in isolation by
definition, so what they measure is precisely the thing that is not broken.

Good answers sound like sequences, not properties: *"create one, restart the service, and
it still resolves"*; *"do it twice with other work in between and the answer is the same"*;
*"what the operator reads matches what actually happened."*

**Recommend three, then ask what is wrong with them.** Draft them from the PRD's own
capability list by pairing capabilities that have to survive each other: *"from §6 I would
propose - (1) shorten, restart the service, resolve: persistence and code generation
agreeing across a process boundary; (2) shorten the same URL twice with other work in
between: idempotence under interleaving; (3) a rejected URL never becomes a redirect: the
invariant probed from several directions. Which of those is wrong, and what would you
add?"* Almost nobody produces three of these cold. Almost everybody can correct three.

**Bad answer:** a restatement of a unit test. If a single function's test would catch it, it
is not one of these.

Two follow-ups worth thirty seconds: *"would you have written these before seeing the
implementation?"* (one written after is a description of the implementation) and *"what
input would you use?"* (it must appear nowhere else in the repo - a value the builder can
grep for is one it can special-case).

Then explain what you are doing with it: these become scenarios the building agent is
blocked from reading, which is the only honest reason to merge code nobody reviewed.

**b) "If I broke this software silently, what would you be most afraid nobody would
notice?"**

**The mutation set, and nothing else in the interview produces it.** It is the only question
here that measures the *harness* rather than the code, and until a defect has been injected
and caught there is no evidence any check can fail at all.

Take the fears literally; each becomes one textual change to real source. Six or seven is a
real set. Prompt with shapes if they stall:

- an invariant quietly inverted - a comparison flipped, a guard removed
- a counter that exists and stops moving
- an output made constant - always the same answer, right shape, wrong number
- an error path that silently succeeds instead of raising
- a persistence write dropped, so everything works until a restart

**Recommend a starting six, drawn from their own code or PRD**, and ask which are wrong:
one invariant inverted, one counter frozen, one output made constant, one error path that
returns instead of raising, one persistence write dropped, one off-by-one at a boundary -
each named against a real function or capability of theirs, not in the abstract. Editing a
list of six is a two-minute job; producing one from nothing is where people stall and say
"I'll come back to it", and then the gate has never been shown to fail.

Then say the thing that makes it stick: **every defect that escapes is a class of bug that
can currently merge with nobody reading the diff.** That converts an abstract exercise into
a list of specific holes they now want closed.

### [PROSE] R2.5c - "Which parts of this can a machine never check?"

Ask it right after the two above, while the user is already thinking about what a check
can and cannot see. **The factory's scope is strictly smaller than the product's**, and the
gap is always the same shape: feel, presentation, readability. *"Combat feels good."* *"The
escalation is visibly and audibly different."* *"A first-time player understands it."*

None of those are machine-validatable and none ever will be. Name them, write them into
`MISSION.md` and `FACTORY_RULES.md` as **permanently human**, and say plainly which layer
the factory owns instead - usually the simulation, the domain, the rules.

That is not a downgrade. It is usually where most of the risk lives, and it is the half
that can actually be defended. But a user who thinks the factory owns the whole MVP will
read a green gate as "the product is good", and it never meant that.

### [PICKER] R2.6 - "What is the one thing that, if broken, means do not merge no matter what else passed? And what would you rather ship than block on?"

**Recommend the boring default and let them argue with it:** block on the app starting,
the E2E path passing, and no protected file being touched - and ship anything else. That
is the right answer for most projects and it is a much easier thing to disagree with than
an empty question.

Both halves together, because they are the same dial from opposite ends. The first becomes
`FACTORY_REQUIRED_MARKERS` - a small, boring list: the app starts, the E2E path passes, no
protected file was touched. The second is the severity policy, and without it every lint
nit blocks the loop and the user turns the factory off out of irritation.

### [PROSE] R2.7 - "When something merges, what command would prove the build actually works, and what would it print?"

`deploy.sh` **refuses to move the pointer** without both. A deploy with no health check is a
deploy that cannot fail, and a step that cannot fail is a comment. These two answers are
`FACTORY_HEALTH_CMD` and `FACTORY_HEALTH_MARKERS`.

Push for an observable a user would notice - a request served, a page rendered, a row
written.

*(There is no push-or-poll question. The answer is always poll: a push trigger that breaks
fails silently and looks exactly like a factory with nothing to do, and GitHub does not fire
workflows on default-token commits at all. Tell them; do not ask. See `deployment.md`.)*

---

## Round 3 - the defaults, confirmed in one message  **[PICKER]**

**Send these as a single list with the proposed value filled in, and ask what to change.**
Not one at a time, and not as questions. Every line has a working default, and most users
will change one or two.

**This is the round the question tool was made for.** One call, **multi-select**, phrased
as *"which of these do you want to change?"* with the proposed value in each option's
description. Selecting nothing is a valid and common answer, and it takes one click
instead of ten replies. Ask for the new value only for the ones they select.

Beware the option cap: real question tools allow only a handful of options per call. Put
the ones a user is most likely to want to change first - concurrency, poll interval, PR
cap, protected paths - and hand the rest over as plain text alongside. Do not drop a row
to fit the widget.

| what | proposed default | why it is a default, not a question |
|---|---|---|
| **Protected paths** | governance files, `factory/**`, `.factory/locks/**`, `.factory/holdout/**`, `.github/`, `deploy/`, `infra/`, Dockerfiles, auth and rate-limit modules, lockfiles | seed it, then ask what else. Their answer is an addition, not the list |
| **Never-committed files** | `.env*`, `*credential*`, `*secret*`, `*.pem`, keys, service accounts | a **different question** from "never edited": being unable to edit a file does not stop `git add -A` publishing one that appears next month. Becomes `FACTORY_SECRET_FILES`, and the pre-flight **refuses to start** until each is git-ignored |
| **Where the hidden scenarios live** | `.factory/holdout/`, read-blocked per node and guarded on the diff | one right answer, already shipped. Mention the stronger options - a sibling repo, or outside version control on the runner - and take the strongest they will actually maintain. A holdout nobody updates is worse than none |
| **PR size cap** | 500 lines, 12 files | crude and it works. Unsupervised agents ship 3,000-line PRs, and "nobody can review it" is where a factory stops being auditable even in principle |
| **Poll interval** | every 30 minutes | slower than feels right. A fast loop multiplies the cost of a mistake before anyone has noticed the mistake |
| **Concurrency** | one | parallelism is where per-target races live. Earn it after the serial version is boring |
| **Stop button** | `.factory/STOP` kill file **and** a `factory:stop` label | two, because they fail in different places. The file works with the network down |
| **Per-node runaway guard** | `FACTORY_MAX_BUDGET_USD` | a ceiling high enough that hitting it means something went wrong. Not a budget - a guard against a node that never terminates |
| **Model routing** | premium in the **planning** slot, cheaper everywhere else | a premium model in *one* of plan/implement buys most of the quality of both. Zero-to-one is a large real improvement; one-to-two is usually noise. Picking the wrong slot is cheap; premium in zero slots is not |
| **Conventions file** | their existing `CLAUDE.md` / `AGENTS.md`, kept | if one exists it is already the answer. **Split it, do not replace it** - move factory-only rules out into `FACTORY_RULES.md`. If none exists, ask what they would tell a new hire on day one |

Four things must be **stated rather than proposed**, because there is no safe default:

- **Which coding agent is authenticated on the machine that will run this.** Not which is
  best - which one already works. The factory shells out to a headless command and reads an
  exit code; every agent exposes that.
- **Where the factory runs.** Laptop, VPS, CI runner, container. This decides credential
  lifetime, whether a schedule survives a reboot, whether the app can even be started for
  E2E, and what the sandbox can reach.
- **How work arrives.** Usually GitHub issues; sometimes a spec file with an issue pointing
  at it. The detail matters less than picking exactly one and making everything read from it.
- **What reaches them, and how.** Exactly one escalation channel, and it should be quiet -
  if everything notifies, they mute it, and then nothing notifies. **Get an actual command,
  not a preference**: "Slack, probably" does not survive contact with the runner.
  `FACTORY_NOTIFY_CMD` needs something that runs. Ask what they would genuinely see within
  an hour on a Saturday. `setup.md` has a working line for each.
  **Bad answer:** *"I'll just check the file."* Nobody checks the file - that is the whole
  reason this exists. A factory whose only output is a file nobody opens is not unattended,
  it is unmonitored.

One more, asked plainly: **"how do you roll back?"** If the answer is "I would fix forward",
that is fine, but it has to be said out loud - an unattended system will eventually merge
something bad, and the recovery path should not be invented at 2am.

---

## Closing the interview

Play the whole thing back as a single spec before writing any file:

- the PRD this was built from, by path, and the mission compressed out of it
- five things out of scope **forever**, sorted apart from "not this quarter"
- the hard invariants and the protected list
- **their existing process, written as the ordered steps the workflows will run**
- the E2E happy path, narrated as steps
- the two structural gates
- where the hidden scenarios live
- the chosen agent, and which model sits in the planning slot
- where it runs, and what schedules it
- what happens on merge, **the command that proves the build works and what it prints**,
  and how to roll back
- the target autonomy level, and the level being built first
- the stop button, and the one channel that reaches them

**Six of these are settings the factory refuses to run without**, so a vague answer is not a
soft failure - it is a blocked first lap. Name them back explicitly:

| answer | becomes | what happens without it |
|---|---|---|
| files that must never be committed | `FACTORY_SECRET_FILES` + `.gitignore` | pre-flight refuses; no lap ever starts |
| the command that proves the app runs | `FACTORY_VALIDATE_CMD` | the gate has nothing to run |
| the observable proof it started | `APP_STARTED` in `FACTORY_REQUIRED_MARKERS` | the gate cannot tell skipped from passed |
| the health command and its output | `FACTORY_HEALTH_CMD` / `_MARKERS` | `deploy.sh` refuses to publish |
| the stop button | `FACTORY_STOP_FILE` / `factory:stop` | nothing can halt it |
| the escalation channel | `FACTORY_NOTIFY_CMD` | unattended quietly means unmonitored |

**And four things the scaffolds hand you as worked examples, which are only yours once you
have replaced them.** `factory_doctor` blocks on each until you delete its marker, because a
gate that is green about somebody else's product is worse than no gate:

| from | you write | answer that produces it |
|---|---|---|
| `harness/e2e.py` | the journey, asserted | R1.1 |
| `.factory/holdout/run.py` | composed scenarios the builder cannot read | R2.5a |
| `harness/mutations/defects.json` | the defects that must be caught | R2.5b |
| `factory/prompts/*.md` | your process, approvals removed | R1.2 |

If any line is still vague, that is the line the factory will fail on. Go back to it.
