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

**EVERY QUESTION GOES THROUGH THE QUESTION TOOL.** `AskUserQuestion` in Claude Code, or
the equivalent elsewhere. Not most questions, not the ones with obvious options - every
one, including the open-ended ones. This is a hard requirement and it has no exceptions.

The earlier version of this file split questions into pickers and prose and argued the
split was load-bearing: that offering options for *"describe the most valuable thing a user
does"* replaces the answer you need with a menu of your guesses. That argument was wrong,
and it was wrong for a mechanical reason:

> **The question tool always carries an "Other" escape with free text.** So an open-ended
> question loses nothing by being asked through it. The user who wants to answer in their
> own words still can, in one keystroke. The user who would have skimmed a paragraph and
> replied *"you pick"* now sees three concrete candidates and corrects the one closest to
> right - which is the answer you wanted and would not have got.

What was true in that old argument survives as a constraint on the OPTIONS, not on the
tool: for an open question, the options must be **drafted from their own PRD and their own
repo, and cited**, never invented. A draft from their material is their answer played back
and they will happily overwrite it. An invented one anchors them onto your guess. If you
have nothing to derive options from, say so in the question text and lean on Other.

**Shape of a call:**

- Two to four options, one marked `(Recommended)` and placed first.
- Each `description` is one line: what it means, or what happens if they pick it.
- The `header` is 12 characters or fewer.
- Batch related questions into a single call - the tool takes up to four - but never batch
  the three Round 1 questions, which are asked one at a time and in order.
- Never ask a question the PRD already answers. Play that back as a proposal instead.

**A question that wants a LIST** - R2.1 asks for five things, R2.2 for a set of invariants -
is a **multi-select** whose options you drafted from their PRD's non-goals, plus Other for
what you missed. Four drafted candidates they can tick is a far better prompt for the fifth
than a blank line, and the ones they *deselect* are as informative as the ones they keep.
Ask once more with what they added if the first pass produced fewer than you expected.

## Two rules that apply to every question below

### 1. Always carry a recommendation. Every question, no exceptions.

**Never hand someone a blank page.** A question with no proposed answer is homework; the
same question with a draft attached is a two-second correction. This is the single biggest
difference between an interview that finishes and one that gets abandoned in the middle.

Mark exactly one option `(Recommended)` and put it first, with the reason in its
description, in one line.

For an open-ended question the options ARE the draft. Derive them from their PRD and their
repo and cite the source in the question text, e.g. *"From §6 of the PRD the journey looks
like: open the app -> shorten a URL -> follow the short link -> land on the original."*
Then offer that as the recommended option, one or two plausible alternatives, and let Other
carry anything you did not think of.

Where a recommendation would be dishonest - a genuine coin-flip, or something only they
can know - say **that** instead of inventing confidence: *"I have no basis for a
recommendation here; it depends on X."* That is still better than silence.

### 2. Offer to explain the hard parts, before they answer

Several of these questions use vocabulary that is obvious only after you have built one of
these. A user who does not want to admit they have not heard of a holdout will guess, and
a guessed answer becomes an unenforceable rule.

So **offer the explanation rather than waiting to be asked**: add an explicit
*"Explain this first"* option as a real choice. It costs one line and it gets picked more
than you would expect.

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

### R1.1 - "Walk me through the single most useful thing someone does with this, from the first click to the thing they end up looking at."

*The* question. The answer becomes the main path the factory checks on every change.

Force it concrete. Not "users can search", but: *open the app -> sign in -> type a query
with a known answer -> the response streams in -> it shows a citation -> click it -> a
window opens at the right spot.*

**Draft it from their PRD first.** The MVP section is usually most of this already. Offer
that as the recommended option and ask what is wrong with it.

**Bad answer:** anything with nothing you could point at on a screen. If you cannot see it,
nothing can check it, and the agent will tell you it works.

### R1.2 - "How do you build a feature with AI today?"

Let this run long, and **do not interrogate**. One open question with a drafted answer, not
a five-part questionnaire about planning, implementation, review, tooling and frameworks.
Take what they give you, then go and look: `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.cursor/`
are usually in the repo already and answer the tooling half without asking anything.

Then say it once, plainly: *every step you just described becomes a step the factory runs,
and the only difference is that nobody clicks approve between them.*

One follow-up, because it is worth more than the rest: **"which of those steps do you
actually read, and which do you just approve?"** The rubber-stamped ones are free
autonomy. The ones they genuinely read are where the checking has to get good.

**If they have no process** - *"I describe the thing, paste it in, run it, paste the error
back"* - that is a real answer and it is the one being automated. Do not dig. Say:

> "That is the process, and we are automating it. The only difference is that right now the
> check is you looking at the result - so the next few questions are about building checks
> that are better than that look, because that look is what goes away."

Then take the shipped prompts as the starting point and say so.

### R1.3 - "Are you willing to let code reach your users without anyone reading it first?"

Ask exactly that, then show the dial. **Level 3 is the recommendation - say so.** People
often say 5; 5 means the factory writes its own work from the mission, which is a different
decision entirely.

Expect a pause. That pause is the entire build in one question, and everything in Round 2
exists to make the answer yes.

Then the follow-up that calibrates everything after it: **"if a bad change did get through,
what is the worst that happens?"** A side project, an internal tool, or real users and real
money. That decides how much of the checking has to be code rather than instructions.

A considered no is fine - level 2 is legitimate. Write into `FACTORY.md` what would have to
be true to go further, so it stays a decision rather than a dial nobody touched again.

---

## Round 2 - what only they can answer

**Seven questions, and every one is about something that has already happened to them.**

That is the rule this round is built on, and it is a correction. An earlier version asked
people to *design* things: name three properties that hold when features combine, list six
ways the software could be silently wrong, define what must stay true under argument. Those
are the right artifacts and they are the wrong questions - they are a design exercise
handed to someone who came here to answer questions about their own product. The person who
wrote the skill got lost in his own interview.

**So: ask about their experience, and derive the artifact yourself.** A user should be able
to answer every question below having never heard of this skill, from memory, about
software they know. Turning those answers into scenarios, defect sets and rules is your
job, and you do it silently.

### Assume more. That is the trade, and it is deliberate.

**When a question is hard to ask simply, answer it yourself and ask them to correct you.**
You have their PRD and their repo, which is more than enough to draft a decent first
version of almost everything here. A drafted answer they can reject in one click is worth
more than a perfect question they abandon.

Concretely, and in this order:

1. **Draft from their material.** Their non-goals are most of the never-do list. Their MVP
   is most of the main path. Their code names the things that can break.
2. **Offer it as the recommended option.** Two or three alternatives, then Other.
3. **Ask only for the correction.** *"Which of these is wrong, and what did I miss?"*
4. **Where you had to guess, say so in one line** - and put it in `MISSION.md` as an
   assumption, so it is visible later rather than silently load-bearing.

**The sacrifice is real and it is accepted.** Assuming means sometimes assuming wrong, and
a user correcting a wrong draft is a better outcome than the same user staring at a blank
question and answering *"I don't know, you pick"* - which is the answer the old interview
actually produced, and it carries no information at all. A wrong guess gets corrected. An
abandoned question does not.

**What you may never assume:** anything in Round 1, and anything that decides what counts
as passing. Guessing whether they will accept unreviewed merges, or how strict the checks
have to be, is not a simplification - it is deciding the project on their behalf.

**Never say these words in a question:** holdout, mutation set, invariant, ratchet,
independence line, structural gate, composition, marker, E2E. Every one names a solution the
user has no reason to know. If a term has to appear at all it appears *after* the answer,
in one sentence, explaining what you are doing with what they just said.

### R2.1 - "Which of these should it never do - not now, not in a year?"

Draft the options **from the PRD's non-goals**, which are usually most of the list already,
and make it multi-select. What they deselect matters as much as what they keep.

**The distinction to hold on to: a PRD says "not now", the factory needs "not ever".** Walk
the non-goals and sort them. "Not now" items go in the backlog and must **not** be listed as
out-of-scope, or the factory will refuse that work when its turn comes.

Then one open follow-up with Other: *"anything else it should turn down even if it were
easy?"* Prompt with categories only if they stall - new data sources, payments, mobile,
social, a public API, integrations.

**What it becomes:** the out-of-scope list in `MISSION.md`, which is what lets the factory
reject a plausible request at three in the morning.

### R2.2 - "What would make you stop whatever you are doing and fix it right now?"

The plain version of "what must always stay true". People answer this instantly because it
is a feeling they have had: the pager, the thing you do not let slide until Monday.

Draft three from the PRD and let them correct: *"I would guess - user data leaking to
another account, the rate limit coming off, anyone being able to see someone else's
records. Which of those is wrong, and what have I missed?"*

**What it becomes:** the properties in `MISSION.md` and `FACTORY_RULES.md` that no request
is allowed to argue away. Different from R2.1: those are features you will not add, these
are things that cannot be changed by anything you *do* add.

### R2.3 - "After you make a change, what do you actually do to check you did not break anything?"

Whatever they say is the specification, including *"I click around for a couple of minutes"*
- **especially** that. Get the clicking narrated, step by step, because that is the check
that has to be automated.

**Bad answer:** *"I run the tests."* Ask what they do after the tests pass, before they
believe it.

### R2.3b - "If you were not looking at the screen, how would you know it was running properly - not just started?"

One of the two things that must be code. A URL that answers, a page that renders, a line in
a log. A process that starts, hangs and returns zero looks exactly like a healthy one.

**Bad answer:** *"it starts up."*

### R2.4 - "What is the laziest way to make the tests pass without actually fixing anything?"

Ask it in those words. It is a question about their code, not about agents, and people
answer it well and enjoy it: delete the test, weaken the check, mock the thing being
tested, catch the error and carry on, special-case the test input.

**What it becomes:** rules in `FACTORY_RULES.md` and, where it can be, a check in code.

### R2.5a - "Tell me about a bug that got past your tests and reached you anyway. What happened?"

**This replaces the hardest question in the old interview**, which asked people to name
three properties that hold only when features are used together. Almost nobody can do that
cold; the file admitted as much and then asked anyway.

Everybody has this story, and the story is the same artifact. A bug that survives a test
suite is nearly always one that needs two things to be true at once - it saved but did not
reload, it worked once but not twice, the second user saw the first user's data. That is
exactly the material needed, and it arrives as a memory instead of a design exercise.

Ask for two or three. Then one follow-up: **"what would have caught it?"**

**What it becomes:** the scenarios kept where the building agent cannot read them, which
is the only honest reason to merge code nobody reviewed. Say that in one sentence *after*
they answer, not before.

**If they genuinely have none** - a greenfield project with no history - draft from the PRD
by pairing capabilities that have to survive each other, and ask which is wrong: *"make one,
restart it, is it still there"*, *"do it twice with something else in between, same answer"*,
*"something you rejected never quietly becomes accepted."*

### R2.5b - "If I broke one thing quietly and nobody noticed, what would hurt the most?"

The best question in the interview. Keep the words.

**But stop asking for six.** The old version wanted six or seven and people stalled, said
they would come back to it, and never did. Ask for **the one that scares them most**, then
draft five more from it and their code and ask which are wrong. Editing a list is easy;
producing one from nothing is where interviews die.

Shapes to draft from, named against their real features rather than in the abstract: a
check quietly reversed, a counter that stops moving, an answer that is always the same
number, an error that returns instead of raising, a save that stops happening so everything
works until a restart, an off-by-one at a boundary.

**What it becomes:** the deliberate defects the checks are measured against. The line worth
saying afterwards: *every one of these that gets through is a kind of bug that can currently
ship with nobody reading the diff.*

### R2.7 - "Once it is live, what would you run or click to prove it is really working?"

And: **what would you see if it worked?** Both halves, because a deploy step with no check
is a step that cannot fail, and a step that cannot fail is a comment.

Push for something a user would notice - a request served, a page rendered, a row written.

---

**Three questions that used to be here now ride in Round 3**, as defaults to amend rather
than questions to answer. They were the most abstract in the interview and all three have a
right answer that is already written down:

| was | now |
|---|---|
| *"Which parts of this can a machine never check?"* | drafted from the PRD - feel, look, readability - and confirmed in the Round 3 call |
| *"What may the factory decide on its own, and what must it stop and ask about?"* | the split is fixed policy, so only the additions are asked, in Round 3 |
| *"What must never merge, and what would you rather ship than block on?"* | the boring default is recommended: it must start, the main path must pass, no protected file touched |

*(There is no push-or-poll question. The answer is always poll: a push trigger that breaks
fails silently and looks exactly like a factory with nothing to do, and GitHub does not fire
workflows on default-token commits at all. Tell them; do not ask. See `deployment.md`.)*

---

## Round 3 - the defaults, confirmed in one call

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
  on a Saturday, away from the machine. `setup.md` has a working line for each.
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
| **What must never merge** | it has to start, the main path has to pass, no protected file was touched - and everything else ships | the boring answer is the right one for almost every project, and it is far easier to argue with than an empty question. This used to be asked open and produced either a list of one or a list of forty |
| **What only a person can judge** | drafted from their PRD: feel, look, wording, whether a newcomer understands it | the factory's scope is smaller than the product's and always in the same way. Derive it, show it, let them add. Written into `MISSION.md` as permanently human, so a green gate is never read as "the product is good" |
| **What it should ask about before doing** | changes a revert does not undo: schema migrations, money, auth and secrets, anything that sends something outside the building | the split itself is fixed policy - it decides ordinary product values and shows you, it never decides what counts as passing - so only the additions are worth asking for. Push back on length in one direction only: everything on this list costs throughput, everything missing from it costs more than throughput |
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
