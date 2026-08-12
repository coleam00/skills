---
id: 0001
title: A one-line statement of the problem, written as what a user sees
state: accepted
priority: high
area: <one of your MISSION.md capability areas>
filed-by: <you>
opened: 2026-01-01
---

<!--
  THE INPUT TO THE FACTORY. Delete this file once you have written a real one.

  This front matter IS the state machine on the file backend. `factory/state.py` parses
  it, the dispatcher reads `state` and `priority` to decide what runs next, and every
  transition is checked against a table that refuses illegal moves. It is flat
  `key: value` on purpose - a parser that cannot express anything clever cannot be
  talked into expressing something clever.

  FIELDS
    id         matches the filename prefix. Keys the branch and the worktree path.
    title      one line. Becomes the commit subject, so write it as the fix.
    state      untriaged -> accepted | deferred | rejected | needs-human
               accepted  -> in-progress -> (PR opens)
               Start at `untriaged` to exercise triage; `accepted` to skip straight
               to a build.
    priority   critical | high | medium | low. The dispatcher takes the highest first.
    area       one of your MISSION.md capability areas. Triage rejects anything that
               is not in one.

  ON GITHUB there is no front matter: the `factory:*` labels are the state and the
  issue body is this body. Run `bash factory/init-labels.sh` once to create the label
  vocabulary. Nothing else changes - the runner reads `gh:issue:<n>` targets and never
  learns which backend it is on.

  WRITING ONE WELL. The factory reads this and nothing else. It cannot ask you what you
  meant, so the two sections below are not a formality:
    - a REPRODUCTION a check could be written from
    - an EXPECTED result that is observable, not a feeling

  An issue that cannot be turned into an assertion cannot be validated, and triage is
  told to reject on ambiguity because a false reject costs one comment while a false
  accept costs a wrong PR and a validation cycle.
-->

## What happens

Steps someone can follow, and what they see at the end of them.

1. Start the app.
2. Do the thing.
3. Observe the wrong result.

## What should happen

The observable difference. Not "it should work" - what a person would see instead.

## Why it matters

One line. Ties back to a capability area in `MISSION.md`, or to a property in its hard
invariants. If you cannot write this line, the issue may be out of scope, and triage
will say so.

## Out of scope for this issue

Anything a reasonable reader might assume is included and is not. Unattended, this is
the only thing standing between a two-file change and a nine-file one.
