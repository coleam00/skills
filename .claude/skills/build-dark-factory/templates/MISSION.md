# Mission

<!--
  Owner: humans only. This file is on the protected list; the factory cannot edit it.
  Replace every <angle-bracket> placeholder. Delete this comment when you do.
  If a section still contains a placeholder, the factory is not ready to run.

  This file is the PRD compressed to the part the agent has to obey. When the product
  changes, this file has to change in the same commit, or the factory keeps building
  the old scope and nothing warns you.
-->

**Derived from:** <path or URL of the PRD this was compressed from>
**Last reconciled with that PRD:** <YYYY-MM-DD>

## What <PRODUCT> is

<One paragraph, in the language a product manager would use. What it does, for whom,
and what a user gets out of it. Not the architecture.>

<A second short paragraph naming any assumption baked into the design - single tenant,
single channel, one deployment - because those become invariants below.>

## Who it is for

- <the user, and the specific thing they are trying to do>
- <a second, if there genuinely is one>

<PRODUCT> is not <the nearest adjacent thing people will mistake it for>.

## Core capabilities (in scope)

The factory may accept issues in these areas.

**<Capability area>**
- <specific capability>
- <specific capability>

**<Capability area>**
- <specific capability>

## Out of scope (the factory must never build this)

Issues asking for any of these are rejected at triage, even when they are popular,
well argued, and easy to implement. This list is how drift gets recognised as drift.

**Never, not "not yet."** Everything here is rejected forever, including the quarter
it lands on the roadmap. Anything that is merely deferred belongs in the backlog, not
in this list. Copying a PRD's non-goals across without doing that sort is the most
common way this section quietly becomes wrong.

<Aim for at least five, grouped. Suggested categories to consider:
 new data sources · additional providers · monetization · mobile or desktop clients ·
 personalization and theming · social features · public APIs and integrations ·
 alternate input modes>

**<Category>**
- <thing>
- <thing>

**<Category>**
- <thing>

## Hard invariants (not tunable by any issue)

These are not features. They are properties that define what <PRODUCT> is. The factory
cannot modify them even if an issue asks nicely, gives a good reason, or calls it a
bug. Changing one requires a human commit.

1. **<Invariant>.** <Why it exists, in one sentence, so a reader can tell whether an
   edge case is covered.>
2. **<Invariant>.**
3. **The factory cannot modify governance files.** `MISSION.md`, `FACTORY_RULES.md`
   and <conventions file> are the constitution. A PR touching any of them is an
   automatic reject.

## Allowed evolutions

Explicitly in scope, so the factory does not reject them as architectural drift:

- <the one architectural change you are willing to let it make, if any>
- <areas where quality can be improved freely>

## Definition of done

Every change the factory ships clears all three gates. A PR that skips any of them is
not done.

**Gate 1 - static checks and tests pass.** <the exact commands>

**Gate 2 - <the product-level quality bar>.** <e.g. any new user-facing feature is
usable without documentation.>

**Gate 3 - the end-to-end path passes as a real user.**

1. <start the app>
2. <the first user action>
3. <...>
4. <the observable result a user would notice>

This runs on every change that touches runnable code, including ones that "seem
unrelated". It is not optional.

## Non-goals

<PRODUCT> is explicitly not trying to be: <a platform · a multi-tenant SaaS · a
general assistant · a developer tool with an API · ...>.

When in doubt, the answer is "that is out of scope."

## Open questions - decisions nobody has made yet

<!--
  WORD THIS CAREFULLY, because the obvious wording breaks the factory.

  A generated MISSION wrote "Open questions - the factory must never answer these", and
  every rule downstream inherited it: any issue whose resolution touched one became
  needs-human. That directly contradicts FACTORY_RULES.md §7, which says an unspecified
  PRODUCT value is decided by the plan node, recorded, and held at the merge.

  Both files are protected, so the factory cannot reconcile them - and a genuine
  contradiction between two governance statements is itself on the stop list. The
  contradiction escalates the very issues the policy was rewritten to unblock.

  "Open" means I HAVE NOT DECIDED. It does not mean you may not propose.
-->

These are undecided, not forbidden. **The factory may propose an answer to any of them**,
build against it, and record what it assumed - the merge is then held for a human, so
nothing ships on a guess and nothing stops for one. See `FACTORY_RULES.md` §7.

- **Q1** <the question, as a decision rather than a topic>
- **Q2** <...>

**Except these, which do stop the factory** - they are on the irreversible list
(`FACTORY_RULES.md` §7.3) rather than open in the ordinary sense:

- <the one about identity, auth, or who may act as whom>
- <the one about migrating or deleting stored data>

Once answered, an entry moves to `.factory/decisions.md` with its answer and date, and
stops being asked. **A decision is asked once.**

## What the factory does NOT own - permanently human

<!--
  THE FACTORY'S SCOPE IS SMALLER THAN THE PRODUCT'S, and saying so here is what stops a
  green gate being read as "the product is good". It never meant that. It means the layer
  a machine can check is intact.

  These are the things no check will ever see. They are not a backlog and they are not
  "not yet" - they are a different kind of work, and it stays with a person.
-->

- <does it FEEL right - weight, pacing, difficulty, tone>
- <does it LOOK right - layout, hierarchy, whether two states read as different>
- <is it UNDERSTANDABLE - can a first-time user work it out without being told>

The factory owns <the simulation · the domain rules · the data model>: the layer whose
correctness can be asserted. That is usually where most of the risk lives, and it is the
half that can be defended. The list above is reviewed by a human, on purpose, forever.
