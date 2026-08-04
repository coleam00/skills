---
name: <skill-name>
description: <What it does, one phrase>. Use when the user wants to "<trigger 1>", "<trigger 2>", "<trigger 3>", or invokes /<skill-name>.
argument-hint: <optional: expected args, e.g. <path> [--flag]>
---

# <Skill Title>

<One or two sentences: the skill's purpose and the end artifact/output. Imperative voice from here on.>

<!-- The sections below are a STARTING SUGGESTION, not a required shape. Keep, drop, rename, or reorder them to
     fit THIS skill's type (workflow / artifact-generator / knowledge / tool-wrapper). A knowledge skill may have
     no Workflow at all; a tool-wrapper may be mostly a Resources pointer. Decide your content yourself. -->

## When to use
<The situations this applies to. Mirror the description's triggers.>

## Workflow
1. <Verb-first step.> <If a step needs bulk detail, point to a reference, don't inline it: see `references/<x>.md`.>
2. <Verb-first step.>
3. <Step that produces output.> Before producing output, read `templates/<output-format>.md` and follow it exactly.

## Gotchas
- <A non-obvious constraint the agent would otherwise get wrong.>

## Resources
- `references/<x>.md` — <when to read it>
- `templates/<output-format>.md` — <the required output shape>
- `scripts/<y>.py` — <what it does; run it, don't read it>

<!-- Authoring reminders (delete before shipping):
- description: third person + literal trigger phrases + /name. ≤1024 chars.
- body: imperative, lean (1,500–2,000 words). Detail → references/. Output shapes → templates/.
- match the structure to the skill TYPE; don't force a workflow shape onto a knowledge skill.
- context can be bundled, external (a path/URL the body cites), or gathered at runtime — pick per ownership/volatility.
- invocation: omit user-invocable/disable-model-invocation for an open read/plan skill; set disable-model-invocation
  for a distributed, side-effecting one.
- wire every bundled file from Resources. No duplication body<->references. Validate with references/validation.md.
-->
