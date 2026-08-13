# The guidance layer

Three files, three different jobs. The split is the whole teaching.

Almost everybody stuffs all of this into one conventions file and then wonders why the
agent drifts, argues with its own constraints, or edits the rule that was inconvenient.

| File | Owns | Example |
|---|---|---|
| **conventions** (`CLAUDE.md` / `AGENTS.md`) | constraints and conventions any project has | *Bun, not npm. All SQL lives in `repository.py`.* |
| **`FACTORY_RULES.md`** | how the agent operates *unsupervised* | *Max 500 lines per PR. Never edit a test to make it pass. Touching a protected file is an instant reject.* |
| **`MISSION.md`** | what is being built, and what is deliberately out of scope | *No payments. No mobile app. No second channel.* |

## The placement test

For every rule, in order:

1. **Would you write this even if a human were doing the work?** → conventions file.
2. **Does it only exist because nobody is watching?** → `FACTORY_RULES.md`.
3. **Is it about what the product is and is not?** → `MISSION.md`.

### Three borderline cases, resolved

- **"Max 500 lines per PR."** Feels like a code convention. But no human on the repo
  is bound by it - it exists purely because an unsupervised agent will otherwise ship
  3,000 lines nobody can review. **Factory rule.**
- **"Provider X is the only LLM provider."** Looks like a stack line for the
  conventions file. The failure it prevents is scope drift, not inconsistency.
  **Mission invariant.**
- **"Every endpoint stays authenticated."** Genuinely lives in two files, and the
  duplication is deliberate: `MISSION.md` owns it as product truth, `FACTORY_RULES.md`
  restates it as an auto-reject trigger. **The file read at reject time has to contain
  the rule.** Duplication for a mechanical reason is fine; duplication by accident is
  how files drift.

### If a conventions file already exists

It usually does, and it is usually carrying all three jobs at once. **Split it, do not
replace it.** Run the placement test over every line already in there and move the
factory-only rules out into `FACTORY_RULES.md` and the product truths into
`MISSION.md`. What is left is the conventions file, and it will be shorter than it was.

This split is often the most useful single edit made to an existing repo, and it pays
off whether or not the user ever turns the cron on: a conventions file that only holds
conventions is a better conventions file for interactive work too.

### If CI already exists, READ IT before writing the gate

Noticing that `.github/workflows/` exists is not the same as reading it, and only the
first was happening: a test run passed Phase 0 on the strength of "there is CI", protected
`.github/`, and never once opened the file. The CI already asserted something the merge
gate was about to re-implement from scratch, and nobody noticed.

So open it. Two things come out:

- **Commands you do not have to invent.** Whatever CI runs for lint, types and tests is a
  tested answer to `static` and `unit` in `harness.config.json`. Reuse it rather than
  writing a second definition that drifts from the first.
- **Assertions that already exist.** If CI enforces something real - a dependency ban, a
  coverage floor, a schema check - that is a rung you already have. Say so, and spend the
  time on the rungs above the independence line instead.

Then say which one is authoritative. The factory's gate is what decides a merge, so if CI
and the gate disagree the gate wins - but a CI that stays red while the factory merges
happily is a contradiction someone will trip over. Either point CI at
`FACTORY_VALIDATE_CMD` so there is one definition, or write down that CI is advisory here.

---

## The property that matters

> **The agent cannot amend the rules it is judged by.**

All three files go on the protected list. A PR that modifies any of them is
auto-rejected before anything else is evaluated, and the validator reads all three
from the **base branch**, not from the PR under review. Without that ordering, a PR can
weaken its own rulebook and then pass against the weakened version.

This is the single property that turns a thing that writes code into a thing you can
leave alone.

---

## The protected list

Any PR touching these is rejected outright, with no fix attempt, and the underlying
issue escalates - because touching one implies the factory misunderstood the scope.

Seed it with all of these, then ask what else:

- **Governance:** the three files above.
- **CI and repo config:** everything under `.github/`, workflow definitions, issue and
  PR templates, CODEOWNERS.
- **Infrastructure:** Dockerfiles, compose files, anything under `deploy/` or `infra/`,
  systemd units, platform config (`fly.toml`, `render.yaml`, `Procfile`).
- **Secrets and auth:** `.env` and every variant, any agent or tool config file that
  holds a token, anything named like a credential, and the modules that define which
  endpoints are protected.
- **Security invariants:** rate-limit constants and their enforcement path, CORS,
  CSRF, and auth middleware.

### The pre-flight that prevents the worst incident

Before **any** workflow that produces a commit, run:

```bash
git check-ignore -v <every-config-file-that-could-hold-a-token>
```

**Empty output means your next run publishes your key.** A `git add -A` inside a
PR-create step sweeps in whatever was not ignored, and on a public repo that is
publication, not a mistake you can take back. Rotating afterwards is the cleanup, not
the fix.

Add the check as a node in the workflow, not as a line in a checklist a human reads.

---

## Writing `MISSION.md`

### It is derived from the PRD, not written from scratch

`MISSION.md` is the PRD compressed to the part an agent has to obey. Do not start from
a blank file, and do not paste the PRD in whole either. Map it:

| PRD | `MISSION.md` |
|---|---|
| problem, why it matters | the opening paragraph, kept short |
| users | one line, because it is what the E2E path is acted out as |
| MVP scope, capability areas | **In scope** |
| **non-goals** | **Out of scope, forever** (see the sort below) |
| success metrics | what a merged change is ultimately meant to move |
| anything marked TBD | do **not** carry it over as a rule. It becomes an entry in `.factory/decisions.md` - proposed by the factory, held at the merge, and answered ONCE. A blanket `needs-human` trigger here is what makes an honest PRD block every issue downstream of it |

**The sort that matters: "not now" is not "not ever".** A PRD's non-goals are usually
a mix of the two, because a PRD is written to keep a team focused for a quarter and
nobody has to be precise about which is which - a human reading it just knows. An
agent does not. Anything logged as out-of-scope will be rejected at triage forever,
including next quarter when it becomes the roadmap.

Walk the non-goals one at a time and sort them into three piles:

- **Never.** Goes in `MISSION.md`.
- **Not yet.** Goes in the backlog, and must not appear in `MISSION.md` at all.
- **Never, and it is a property rather than a feature.** That is a hard invariant, and
  it belongs in the invariants section below plus `FACTORY_RULES.md`.

If sorting leaves fewer than five items in the first pile, the list is too thin. Go
back to the interview and get more.

### The two sections that do the work

Two sections do the real work, and one of them is the one people skip.

**In scope** - the capability areas the factory may build. Short. Triage accepts
against this.

**Out of scope, forever** - the section that earns its keep. This is how an agent
recognises that a plausible, well-argued, easy-to-implement feature request is *drift*
rather than a good idea. Without it, every request is arguably in scope, because
almost every feature is defensible in isolation.

Aim for at least five, and make them things a reasonable person might ask for:

> No payments or subscriptions. No mobile or desktop apps. No additional content
> sources. No public API for third parties. No social features - no comments, no
> reactions, no sharing. No alternate input modes.

**Hard invariants** are different from out-of-scope items and deserve their own
section. Out-of-scope is *features you will not add*. Invariants are *properties that
cannot be edited*: a rate limit, an auth requirement, a privacy guarantee, a
single-tenant assumption. An issue arguing well for changing one is rejected at triage
as a security concern, not debated.

---

## Writing `FACTORY_RULES.md`

Cover these sections. The templates directory has a fuller skeleton.

1. **Triage rules** - what to accept, reject, or hand to a human. Bias toward reject
   on ambiguity and say so explicitly: a false reject costs one comment, a false
   accept costs a wrong PR and a validation cycle.
2. **Implementation rules** - the absolute prohibitions. Never edit a test to make it
   pass. Never touch a protected file. Never add a dependency without justification in
   the PR body. Never exceed the size cap. Never build beyond what the issue asked.
3. **Quality gates for auto-merge** - the enumerated list of conditions, every one of
   which must be true. Mark which are enforced in code.
4. **Auto-reject triggers** - failures that cannot be fixed incrementally, so the PR
   is closed rather than sent back.
5. **Escalation** - what makes it stop and ask for a human, and how a human clears it.
6. **Cost and throughput limits** - batch sizes, attempt caps, concurrency, priority
   order.
7. **Separation of concerns** - the holdout rule, written out: what the validator may
   read and what it must not.
8. **Communication style** - how the factory writes comments. Lead with the decision,
   cite the rule by section number, stay neutral, leave an appeal path, never promise
   future behaviour.
9. **How this file changes** - human commits only. It is on the protected list.

### Why section numbers matter

Require the factory to **cite the rule that drove a decision, by section number**, in
every comment it posts. Two reasons, both practical:

- A filer who gets a rejection citing a rule can read the rule and appeal against it.
  A rejection with no citation reads as arbitrary.
- You get a usage trace of your own rulebook. Rules that never get cited are either
  never triggered or never read, and both are worth knowing.

The best artifact a factory can produce is not a merged PR. It is an issue where the
system read a bug report, worked out the real cause was outside its own repository,
noticed that fixing it would require touching protected files, cited the two sections
that made that a reject, declined the work, and left an appeal path.

**An autonomous system correctly doing nothing** is what the guidance layer buys.
