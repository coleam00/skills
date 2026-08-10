# The interview

Work through this component by component. Reflect every answer back as a concrete
artifact before moving on - "so the merge gate is: the PR merges only if
`APP_STARTED` and `E2E_PASSED` both appear in the run output" - because the point of
the interview is to convert opinions into things that can be written down and run.

**Push back on vague answers.** A vague answer here becomes an unenforceable rule
later, and an unenforceable rule is worse than no rule: it reads like a guarantee.

Each section below lists the questions, what each one is *for*, and the specific
shape of bad answer to reject.

> **Read the PRD first, and do not ask it anything the PRD already answers.**
> Questions marked **[FROM PRD]** are answered before the interview starts. For those,
> the move is to *play the answer back as a proposal and ask what is missing*, not to
> ask the question. An interview that makes someone retype a document they already
> wrote loses them in the first two minutes, and it is the most common way a
> well-designed interview fails in practice.
>
> The single question that shapes more of the build than any other is **Q3.0**, on how
> the user already codes with AI. Everything the factory runs is that process with the
> approvals taken out, so get that answer before deciding any workflow.

---

## 0. Scope and appetite

**Q0.1 [FROM PRD] - what this repo is, in one sentence a product manager would use.**
Take it from the PRD's problem statement and read it back for confirmation. Feeds
`MISSION.md`. Only ask if the PRD's version is architectural ("a FastAPI service with
a React front end"), in which case ask for the *what it does for whom* version.

**Q0.2 - "What level of autonomy do you actually want?"**
Show the dial from `SKILL.md`. Most people say 5 and mean 3. The distinction that
matters: at level 3, code merges without a human reading it. Ask directly - *"are you
willing to have code merge to main that no human has read?"* - and if the answer is no,
build to level 2 and stop. That is a legitimate, useful destination.

**Q0.3 - "What is the blast radius of a bad merge?"**
Personal side project, internal tool, or something with real users and real money.
This sets how much of the harness has to be structural rather than prompted, and how
long the protected list is.

**Q0.4 - "How much are you willing to spend per issue, and how would you know?"**
Almost nobody has instrumented this. The useful outcome is not a number, it is the
user agreeing to instrument tokens before the first unattended run.

---

## 1. The mission and the boundaries (component 4)

**Q1.1 [FROM PRD] - what is in scope.**
The PRD's MVP scope and capability areas. Read the list back. This is what the triage
step will accept against, so the useful follow-up is not "what else" but *"is there
anything on this list you would not want built without you looking at it?"* Anything
that comes back goes on the protected list rather than into scope.

**Q1.2 [FROM PRD, then push hard] - what this must never grow into.**
*The most valuable list in the whole build, and the reason a PRD is required.* Start
from the PRD's **non-goals** section, which is usually most of the way there.

Then push, because a PRD's non-goals are written to keep a team focused this quarter,
and this list has to hold against an agent reading a stranger's feature request at
three in the morning. Prompt with categories until there are five or more: new data
sources, new providers, payments, mobile, social features, public API, integrations,
alternate input modes.

The distinction to hold on to: **a PRD says "not now", and `MISSION.md` has to say
"not ever".** Walk the non-goals one at a time and sort them. "Not now" items belong
in the backlog and must not appear as out-of-scope, or the factory will reject the
work when its turn comes.

Bad answer: *"anything that doesn't fit."* Push: **name five things you would reject
even if a user asked nicely and the code would be easy.**

**Q1.3 - "What is true about this system that must never change, even if an issue
argues well for changing it?"**
These are hard invariants - a rate limit, an auth requirement, a privacy property, a
single-tenant assumption. They differ from out-of-scope items: those are features you
will not add, these are properties that cannot be edited. They go in both `MISSION.md`
and `FACTORY_RULES.md`, deliberately, because the file read at reject time has to
contain the rule.

**Q1.4 - "Which files must the agent never touch?"**
Seed the list, do not just accept theirs. Governance files, `.github/`, Dockerfiles
and compose files, anything under `deploy/` or `infra/`, `.env*`, auth and rate-limit
modules, CI config, lockfiles if they are large. Then ask what else.

**Q1.5 - "What conventions would you tell a new human hire on day one?"**
This is the conventions file, and it is the one they would have written anyway. Keep
it separate from the factory rules - the split is the teaching.

---

## 2. The validation harness (component 5)

Spend the most time here. Read `validation-harness.md` first if it has not been read.

**Q2.1 - "Describe the single most valuable thing a user does with this app, as a
sequence of actions ending in something you can see on a screen."**

This is *the* question. The answer becomes the E2E happy path and therefore the only
check that has real authority.

Force it to be concrete. Not "users can search." Instead: *open the app → sign in as
a test user → type a query with a known answer → the response streams in → it renders
with a citation → click the citation → a modal opens at the right timestamp.*

Bad answer: any description that never mentions something observable. If it cannot be
observed, it cannot be asserted, and the agent will claim it works.

**Q2.2 - "How do you personally check a change did not break things, today?"**
Whatever they say - even "I click around for two minutes" - is the spec for the
automation. Get the click-around narrated step by step.

**Q2.3 - "What is the observable proof the app is actually running?"**
A health endpoint returning a known payload, a port accepting connections, a log line.
This becomes the `APP_STARTED` marker, and it is one of the two gates that must be
code. Without it, a crashed app produces a validator that cheerfully reports "not
testable" and something else counts that as fine.

**Q2.4 - "If the agent wanted to make the checks pass without fixing anything, what
is the easiest way?"**
Ask it exactly this way. The answers are the holes: deleting a test, weakening an
assertion, mocking the thing under test, catching and swallowing, adding a special
case for the test input. Each answer becomes a rule in `FACTORY_RULES.md` and, where
possible, a structural check.

**Q2.5 - "Where can the holdout scenarios live so the agent cannot read them?"**
Options in increasing strength: a path the validator reads but the builder's tooling
excludes; a sibling repo; outside version control entirely on the runner. Pick the
strongest one the user will actually maintain. A holdout the user stops updating is
worse than none, because it silently stops covering new behaviour.

**Q2.6 - "What is the one thing that, if broken, means do not merge no matter what
else passed?"**
The deterministic gate. There should be a small number of these and they should be
boring: the app starts, the E2E path passes, no protected file was touched.

**Q2.7 - "What would you rather ship than block on?"**
Severity policy. Without it, every lint nit blocks the loop and the user turns the
factory off out of irritation.

---

## 3. The agent and the workflows (component 1)

**Q3.0 - "Walk me through how you build a feature with AI today, step by step."**

Ask this before anything else in this section, and let it run long. **The workflows
are meant to be this process with the approvals removed, not a new pipeline.**

Most people have more process than they think they do and have never written it down.
Draw it out step by step and name each one:

- **Planning.** Do they write a plan first? From what? Does anything read it back?
- **Implementation.** One pass, or sliced into tickets? What decides the slice?
- **Review.** What do they look at, and what makes them send it back?
- **The tooling at each step.** Which skills, commands, subagents, MCP servers, rules
  files and reference docs are loaded where. Get specifics, and go look: `CLAUDE.md`,
  `AGENTS.md`, `.claude/`, `.cursor/` are usually already in the repo.
- **The named framework, if any.** Spec Kit, BMAD, a PRP framework, an in-house SDLC.
  If they have one, it is the answer, and the job is to encode it faithfully.

Then say the thing out loud: *every one of those steps becomes a node, and the only
difference is that nobody clicks approve between them.*

Follow up with the sharpest version of it: **"which of those steps are you actually
reviewing, and which do you already rubber-stamp?"** The rubber-stamped ones are free
autonomy and should go first. The ones they genuinely read are where the validation
harness has to earn its place, and that answer tells you what the harness is for on
this specific project.

Bad answer: *"I just use Claude Code."* Push for the sequence. Everyone has one.

**Q3.1 - "Which coding agent do you already have working, authenticated, today?"**
Not which is best. Which one is authenticated on the machine that will run this. The
factory shells out to a headless command and reads an exit code; every agent exposes
that. Start with the one that already works.

**Q3.2 - "Where will the factory run?"**
Laptop, a VPS, CI runners, or a container. This decides more than the agent choice
does - credential lifetime, whether a schedule survives a reboot, whether the app can
even be started for E2E, and what the sandbox can reach.

**Q3.3 - "How does work arrive?"**
Usually GitHub issues. Sometimes a spec file committed to a branch with an issue
pointing at it. The detail matters less than picking exactly one and making everything
else read from it.

**Q3.4 - "What does 'done' mean for one unit of work?"**
A merged PR? A deployed change? A closed issue? Name it, because the dispatcher's
state machine terminates on it.

**Q3.5 - "How big is a PR allowed to be?"**
Give a number. Line count is crude and it works. Unsupervised agents ship 3,000-line
PRs nobody can review, and "nobody can review it" is the point at which a factory
stops being auditable even in principle.

---

## 4. Deployment (component 3)

**Q4.1 - "When something merges to main, what should happen, and how would a user
see it?"**

**Q4.2 - "Is the deploy triggered by a push, or does something poll?"**
If push-triggered from a workflow, flag the `GITHUB_TOKEN` trap immediately - it is
the single most common silent failure. See `deployment.md`.

**Q4.3 - "How do you roll back?"**
If the answer is "I would fix forward", that is fine but it must be said out loud,
because an unattended system will eventually merge something bad and the recovery
path should not be invented at 2am.

---

## 5. The trigger (component 2)

Ask these last, and only once the rest is real.

**Q5.1 - "How often should it look for work?"**
Slower than feels right. Every 30 minutes is plenty. A fast loop multiplies the cost
of a mistake before you have noticed the mistake.

**Q5.2 - "How many things may run at once?"**
Start at one. Parallelism is where per-target races appear - two workflows operating
on the same PR - and it should be earned after the serial version is boring.

**Q5.3 - "What is the stop button?"**
There must be one, it must be obvious, and the user must have used it once on purpose
before going unattended. Removing a label, a kill file the dispatcher checks, or
disabling the schedule. Test it.

**Q5.4 - "What reaches you, and how?"**
Exactly one escalation channel, and it should be quiet. If everything notifies, the
user mutes it, and then nothing notifies. `needs-human` should be rare enough to be
worth reading.

---

## Closing the interview

Play the whole thing back as a single spec before writing any file:

- the PRD this was built from, by path, and the mission compressed out of it
- five things that are out of scope **forever**, sorted apart from "not this quarter"
- the hard invariants and the protected list
- **their existing process, written as the ordered steps the workflows will run**
- the E2E happy path, narrated as steps
- the two structural gates
- where the holdout lives
- the chosen agent, orchestrator, and where it runs
- what happens on merge, and how to roll back
- the target autonomy level, and the level being built first
- the stop button

If any line is still vague, that is the line the factory will fail on. Go back to it.
