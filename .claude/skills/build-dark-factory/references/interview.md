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

**Reflect every answer back as a concrete artifact** before moving on - "so the merge gate
is: the PR merges only if `APP_STARTED` and `E2E_PASSED` both appear in the run output."
The point of the interview is to turn opinions into things that can be written down and
run.

**Push back on vague answers.** A vague answer becomes an unenforceable rule, and an
unenforceable rule is worse than none: it reads like a guarantee.

---

## Round 1 - the three that decide the project

Ask these first, one at a time, before any component discussion. If someone walks away
after three questions, these are the three you needed.

### R1.1 - "Describe the single most valuable thing a user does with this app, as a sequence of actions ending in something you can see."

*The* question. The answer becomes the E2E happy path, which is the only check with real
authority, and it is what `harness/e2e.py` gets rewritten into.

Force it concrete. Not "users can search." Instead: *open the app → sign in as a test user
→ type a query with a known answer → the response streams in → it renders with a citation
→ click the citation → a modal opens at the right timestamp.*

**Bad answer:** any description that never mentions something observable. If it cannot be
observed it cannot be asserted, and the agent will claim it works.

### R1.2 - "Walk me through how you build a feature with AI today, step by step."

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

**Bad answer:** *"I just use Claude Code."* Push for the sequence. Everyone has one.

### R1.3 - "Are you willing to have code merge to main that no human has read?"

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

### R2.1 - "Name five things you would reject even if a user asked nicely and the code would be easy."

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

### R2.2 - "What must always stay true, even if an issue argues well for changing it?"

Hard invariants - a rate limit, an auth requirement, a privacy property, a single-tenant
assumption. Different from out-of-scope items: those are features you will not add, these
are properties that cannot be edited. They go in **both** `MISSION.md` and
`FACTORY_RULES.md`, deliberately, because the file read at reject time has to contain the
rule.

### R2.3 - "How do you check a change did not break things today, and what tells you the app is actually running?"

Two halves, one conversation.

The first: whatever they say - even *"I click around for two minutes"* - is the spec for
the automation. Get the click-around narrated step by step.

The second is one of the two gates that **must be code**: a health endpoint returning a
known payload, a port accepting connections, a specific log line. It becomes the
`APP_STARTED` marker. Without it, a crashed app produces a validator that cheerfully
reports "not testable" and something downstream counts that as fine.

**Bad answer to the second half:** *"it starts up."* A process that starts, hangs and
returns zero is indistinguishable from a healthy one.

### R2.4 - "If someone wanted to make the tests pass without actually fixing anything, what is the easiest cheat?"

Ask it in those words - it is a question about their code, not about agents, and people
answer it well. The answers are the holes: delete a test, weaken an assertion, mock the
thing under test, catch and swallow, special-case the test input.

Each answer becomes a rule in `FACTORY_RULES.md` and, where possible, a structural check.

### R2.5 - the two harness questions, and they are the hard part

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

Then say the thing that makes it stick: **every defect that escapes is a class of bug that
can currently merge with nobody reading the diff.** That converts an abstract exercise into
a list of specific holes they now want closed.

### R2.6 - "What is the one thing that, if broken, means do not merge no matter what else passed? And what would you rather ship than block on?"

Both halves together, because they are the same dial from opposite ends. The first becomes
`FACTORY_REQUIRED_MARKERS` - a small, boring list: the app starts, the E2E path passes, no
protected file was touched. The second is the severity policy, and without it every lint
nit blocks the loop and the user turns the factory off out of irritation.

### R2.7 - "When something merges, what command would prove the build actually works, and what would it print?"

`deploy.sh` **refuses to move the pointer** without both. A deploy with no health check is a
deploy that cannot fail, and a step that cannot fail is a comment. These two answers are
`FACTORY_HEALTH_CMD` and `FACTORY_HEALTH_MARKERS`.

Push for an observable a user would notice - a request served, a page rendered, a row
written.

*(There is no push-or-poll question. The answer is always poll: a push trigger that breaks
fails silently and looks exactly like a factory with nothing to do, and GitHub does not fire
workflows on default-token commits at all. Tell them; do not ask. See `deployment.md`.)*

---

## Round 3 - the defaults, confirmed in one message

**Send these as a single list with the proposed value filled in, and ask what to change.**
Not one at a time, and not as questions. Every line has a working default, and most users
will change one or two.

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
