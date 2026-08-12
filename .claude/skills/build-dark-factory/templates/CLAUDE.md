<!--
  THE CONVENTIONS FILE. `CLAUDE.md`, or `AGENTS.md` - the name follows your agent.

  This is the one of the three governance files you would have written anyway, with no
  factory involved, and that is exactly the test for what belongs here:

      Would you write this rule even with a human doing the work?  -> here
      Does it only exist because nobody is watching?               -> FACTORY_RULES.md
      Is it about what the product is and is not?                  -> MISSION.md

  Almost everybody stuffs all three jobs into this one file and then wonders why the
  agent drifts, argues with its own constraints, or edits the rule that was inconvenient.
  Keeping them apart is the teaching, and it pays off whether or not you ever turn a cron
  on: a conventions file that only holds conventions is a better conventions file for
  interactive work too.

  If you already have one, KEEP IT and pull the factory-only rules out of it rather than
  writing a new one over the top. That split is usually the single most useful edit this
  phase makes to an existing repo.

  This file is PROTECTED. The factory cannot edit it - the agent must not be able to
  amend the rules it is judged by. Replace every <angle-bracket> and delete this comment.
-->

# <PROJECT> conventions

## Stack and commands

The commands anyone needs on day one. Exact, copy-pasteable, and correct - a stale
command here is a node that spends its budget discovering the right one.

```bash
<how to install dependencies>
<how to run the app>
<how to run the tests>
<how to run the type-checker / linter>
```

**<Package manager>, not <the other one>.** <One line on why, if there is a reason. A
rule with a reason survives; a rule without one gets argued with at 3am.>

## Where things live

The map someone needs before their first edit. Keep it to the load-bearing directories -
a full tree here goes stale in a week and is worse than nothing.

| path | what belongs there |
|---|---|
| `<src/>` | <the thing itself> |
| `<tests/>` | <all tests. New coverage goes here, never into harness/> |
| `<harness/>` | <the gate. Protected - see FACTORY_RULES.md> |

**<The one architectural rule that matters.>** <e.g. "All SQL lives in repository.py."
"The simulation imports nothing that renders." One or two of these, not ten - the rules
that get cited are the rules that were worth writing.>

## Code style

Only what a reviewer would actually send back:

- <naming convention that is not obvious from the code>
- <error handling: raise or return? logged where?>
- <what goes in a docstring vs a comment>
- <anything your linter does NOT already enforce - if the linter catches it, it does not
  belong here, and repeating it just makes this file longer than it is useful>

## Tests

- <where they live, how they are named>
- <what a new feature must come with>
- **New coverage goes in `<tests/>`, never in the harness.** The harness is protected: it
  is the definition of "working", and a builder that can edit its own judge can make any
  claim true. Growing test coverage is expected and welcome - it just happens over here.

## Dependencies

<Your policy. A real one, because unattended this is where scope creep enters.>

New dependencies require a PR-body section explaining what it does, why the existing ones
do not, and evidence of active maintenance. <Or: "no new dependencies; the standard
library is the dependency policy.">

## What is NOT in this file

- **What the product is, and what it will never be** -> `MISSION.md`
- **How the factory behaves unsupervised** - PR size caps, protected paths, never editing
  a test to make it pass -> `FACTORY_RULES.md`

If you are about to write a rule here that starts "the agent must never...", it almost
certainly belongs in `FACTORY_RULES.md` instead.
