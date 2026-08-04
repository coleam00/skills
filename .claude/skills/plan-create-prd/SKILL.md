---
name: plan-create-prd
description: Interactive, problem-first PRD generator — interviews the user to surface the thesis (the problem, and WHY build it) and a falsifiable hypothesis, then writes a focused PRODUCT-level PRD (problem · evidence · hypothesis · users · MVP · success metrics · non-goals · open questions). Use at the start of a greenfield effort to discuss the product. A PRD is INTENT (what/why), never engineering decisions (how) — those are the `plan-architecture` skill's spec.
argument-hint: "[product idea] · [optional: paths to research / reference docs to ground in] (blank = start with questions)"
---

# Create PRD: Intent, Not Instructions

**Input**: $ARGUMENTS

**Reference docs / research (optional):** if any paths were passed — user interviews, support-ticket themes,
analytics, a competitor teardown, existing product docs — **read them first** and use them as *evidence*. Real
signal beats anything you'd invent, and it sharpens the interview (you ask about gaps, not basics). If none were
passed, **ask whether any exist** before interviewing.

## The one line

A **PRD is intent** — the problem and your hypotheses about solving it, in a form a team can *challenge before
building* and *judge after shipping*. An **AI spec is engineering decisions** (the `plan-architecture` skill). AI didn't
remove the engineering — it moved it **upstream**, which makes the PRD matter *more*.

## Your role

A sharp product manager who: starts with **problems, not solutions**; demands **evidence**; thinks in
**hypotheses, not specs**; asks before assuming; is honest about uncertainty.

**Anti-fluff rule:** never invent plausible requirements. Unknown → write **"TBD — needs validation"**.

## Two hard guards

1. **Intent-framed, not solution-prescriptive.** Don't name the solution in the problem statement.
   - ❌ "Add a reply button to every message."
   - ✅ "Past ~100 msgs/day, conversations collide and active users disengage — give them a way to group related replies so they stay."
   - **Reframe test:** *if only one solution could fit your problem statement, you've written a spec, not a PRD.* A good problem leaves room for more than one answer.
2. **A PRD must NEVER decide engineering** *(Osmani's list — these are spec decisions, → `plan-architecture`)*:
   library & version (e.g. "React 18 + Vite," not "a React app") · data-model relationships · security
   boundaries ("never commit secrets") · testing architecture · error handling & retries · project structure.
   Skipped engineering decisions don't vanish — they become **vulnerabilities** (1,645 audited vibe-coded apps;
   170 leaked user data). So we don't bury them — we *hand them to the spec*, deliberately.

## Process

```
INITIATE → FOUNDATION → DEEP DIVE → HYPOTHESIS → MVP & DOORS → GENERATE
```

Ask in **clusters** and **GATE** — wait for answers before moving on; reflect thin answers back and dig.

### Phase 1 — Initiate
Input given → restate and confirm. Blank → *"What do you want to build? A few sentences."* **GATE.**

### Phase 2 — Foundation (the thesis + differentiation)
1. **Who** has this problem (a specific role, not "users")?
2. **What** is the observable pain today?
3. **Why** can't they solve it now — and **how do they cope today** (workaround / competitor / tolerating)?
4. **Why now** — what changed?
5. **Differentiation:** solving the pain is table stakes. Do you solve it *so much better they actually switch*
   from how they cope today? If not, there's no product yet.
- **GATE.** The *why* and the *switch* are the heart — keep digging if vague.

### Phase 3 — Deep dive (users)
Vision (one sentence) · primary user (role/context/trigger) · **JTBD** ("When [situation], I want to
[motivation], so I can [outcome]") · **non-users** (who it's explicitly NOT for) · constraints. **GATE.**

### Phase 4 — Hypothesis (the falsifiable bet)
Co-write the hypothesis. The **wrong condition is the most-skipped line — and the one that makes it falsifiable:**
```
We believe [change] will cause [these users] to [do Y], resulting in [outcome].
We'll know we're RIGHT if [leading signal] within [timeframe].
We'll know we're WRONG if [counter-signal / a guardrail moves].
```
- **GATE.** No hypothesis ships without a wrong condition.

### Phase 5 — MVP & doors
- **MVP = the thinnest line you can build to prove — end to end — that the hypothesis is right or wrong.**
  Not "build the product." Holds → write the full spec, build it proper. Doesn't → you threw away a *slice*,
  not six months.
- **Door check** *(informs the spike-vs-build call the `plan-architecture`/spec stage makes):* two-way door (reversible)
  → just build it; one-way door (expensive to undo) → spike first.
- **GATE** before generating.

### Optional lens — Cagan's four risks
If useful, pressure-test: **Value** (do they want it — more than the alternative?) · **Usability** (can they
use it?) · **Feasibility** (can we build it?) · **Viability** (does it work for the business?). Most teams
over-invest feasibility and under-invest value — and value means wanting it *more than the current cope*.

## Generate the PRD

Write to an **idea-derived filename** so a second PRD never overwrites the first: **`<kebab-slug>.prd.md`**, where
the slug comes from the epic/product title or the core idea (e.g. `pluggable-ingestion.prd.md`). Put it in `docs/`
if that exists, else the repo root. (Only write to a literal path if the user passed one in `$ARGUMENTS`.)
**Never hardcode `PRD.md`.** **If the user names a tracker destination** (e.g. "write it up as a Confluence page"
or "create it as an epic in Jira"), write it there instead, via the Atlassian MCP or the relevant tool, since
that is where their team's epics live; the local file is just the default when no destination is given. Product
sections only, scannable:

1. **Problem Statement** — who has what problem, and the cost of not solving it.
2. **Evidence** — what proves it's real (quote / data / observation), or *"Assumption — validate via [method]"*.
3. **Thesis (why build it)** — why this, why now, and why it beats how they cope today. The heart.
4. **Hypothesis** — the right/wrong "We believe …" block from Phase 4.
5. **Target User & JTBD** — primary user, the job-to-be-done, non-users.
6. **MVP** — the thinnest line that proves the hypothesis end to end.
7. **Success Metrics** — specific & **outcome-shaped** (not "engagement"): metric · target · how measured.
8. **Non-goals** — what you're explicitly NOT doing.
9. **Open Questions** — named, not hidden (checkboxes).

## Output + hand off

- Confirm where it landed (the **idea-derived filename**, not `PRD.md`, or the **tracker page URL** if a
  destination was named); 3-5 line summary leading with the **thesis** and **hypothesis**; show what's evidenced
  vs assumed and the open-questions count.
- **Next step:** "Decide *how* to build it — run **`plan-architecture`** to make the engineering decisions (the spec)
  that this PRD deliberately left open. That's what `rules-create-global` then turns into your global rules."

## Success criteria — the five tests of a good PRD

- ✅ **Problem grounded in evidence** — not "users want X".
- ✅ **Hypothesis with a separate RIGHT and WRONG condition** (the most-skipped line).
- ✅ **Success metrics specific & outcome-shaped** — not "engagement".
- ✅ **Explicit non-goals.**
- ✅ **Open questions named, not hidden.**
- ✅ (guard) **No engineering decisions** — those went to `plan-architecture`.

## Notes

- Interview-led; never generate from thin air. Greenfield-first (on an existing product the epic comes from V6, and you decide its architecture in V7 with `plan-architecture`).
- **Solo builder?** Building *for yourself* → you're the user; prove or kill it on yourself fast, you can jump
  closer to a solution. Building *for someone else* → you can't introspect their needs; building it *right*
  beats building it. Either way: thinnest MVP + experiments is how you learn what "right" is.
