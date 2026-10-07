# The decision pass

The decision pass is what lets the engine read thousands of items: a quick, typed call on
every item, so the LLM only reads what survives. It is also where the user's filter lives,
in the words of one or two questions.

## Write the question from their examples

Start from R1.1 (what they would act on) and the keep/drop examples from R2.3. The question
must separate those examples. Read it against each one before running anything.

**One thing per question.** "Is this a new and relevant release?" is two questions in one,
and the answer is a blur. Split it.

A good starting set for keeping up with a field:

- **Relevance**, as a score on levels you write in their words. Level 1 is "not about my
  area", the top level is "directly changes how I work". Say that an unfamiliar product or
  model name is not a reason to score lower, or every brand-new launch gets buried.
- **Reports something new and concrete:** yes or no. A release, a feature, a tool, a
  measured result, a technique, a documented incident. Opinions, questions, complaints,
  jokes, reactions and rumors are "no", even when they mention a real product.

Taste questions ("is this a toy project", "would I enjoy this", "is it high quality") are
useful for ranking and for the reading pass. They are never a reason to drop.

**Keep numbers out of the question.** Upvotes, dates, counts and comparisons are code.
Decision models and LLMs are both unreliable at arithmetic and dates.

**Send only the fields the decision needs:** title, the first few hundred characters of the
body, and the source domain. Unrelated text lowers accuracy.

## Route in code

```
drop    relevance below the floor, OR clearly reports nothing new
keep    relevance high AND clearly new AND not a toy
unsure  everything else
```

Starting thresholds when using probabilities: drop on relevance under 0.4 or "new" at or
under 0.1; keep on relevance 0.5+ and "new" 0.6+. Only `drop` changes what happens; `keep`
and `unsure` both go to the reading pass, where the LLM makes the final call and can rank
keeps first.

**Why these and not tighter:** in testing on a real day of 155 items, adding a toy-project
drop at 0.8 cut 7 personal builds the LLM kept (a book-to-course skill, a model trained from
scratch), and a "new" cut at 0.15 dropped a conference talk. Tighter bands save more and
lose real finds. Let the user choose that trade with R2.5.

## Run it in parallel

Ask all questions about one item in one request, and run all items concurrently with a
small cap (8 to 16). A sequential LLM loop over a few hundred items takes many minutes; a
parallel decision pass over 864 items took 17 seconds in testing.

If a call fails or times out, the item gets no verdict and goes on to the reading pass as
if the decision pass did not exist. The decision pass must never be a single point of
failure.

## Prove it on their examples

Before trusting it:

1. Score every keep/drop example from `PROFILE.md`. Print each with its answers and route.
2. Take a real sample from today's run (50-150 items), have the user sort it in one
   multi-select call (or sort it with them), and score that too.
3. Report: how many dropped, how many kept, and every item they wanted that was dropped.

Fix misses by rewording the question first. Thresholds second. A miss that is really a
policy disagreement ("it dropped consumer app features because my relevance question is
about developers") is a decision for the user, not a bug: offer to widen the question.

## Measure it honestly

Run the same stored items through the rest of the pipeline twice, once with the decision
pass off and once on, against a throwaway database. Report items the LLM read, tokens, wall
time, and the items the LLM kept with the pass off that the pass dropped. Expect the LLM to
vary between the two runs on its own; do not count those rows against the decision pass.

For the per-decision receipt, run the decision pass and a small LLM over the same items
with the same questions and compare time and cost. Say which is which: the decision pass
saves on reading, never on the cost of fetching the data.

## Where to use which model

| Job | Model |
|---|---|
| The decision on every item | a decision model with typed answers (TypeSafe's Jev via OpenRouter is the reference), or the smallest LLM that returns structured output reliably |
| Reading and writing the digest | a mid-tier LLM, once per run |
| Content ideas, weekly roll-up (optional) | the same or a stronger model, once per run or week |

## Calling Jev (TypeSafe's decision model on OpenRouter)

One POST per item, with the user's OpenRouter key as a Bearer token:

```
POST https://openrouter.ai/api/alpha/decisions
{"model": "typesafe/jev-1.13",
 "state": "<title + first ~1,500 chars of the body + url>",
 "questions": {
   "relevance": {"type": "score", "instructions": "<the relevance question>",
                 "criteria": ["<level 0>", "<level 1>", "...up to 10 levels"]},
   "new":       {"type": "noul", "instructions": "<the 'something new' question>",
                 "criteria": {"true": "<what yes means>", "false": "<what no means>"}}}}
```

The response has `answers`: a `noul` comes back as `{"noul": <probability of yes>}`, a
`score` as `{"score": <weighted level, 0 to levels-1>, "probabilities": {...}}`; divide the
score by `levels - 1` for a 0-1 number. A `choice` question takes a dict of option names to
descriptions and returns `{"choice": ..., "probabilities": {...}}`. Each call is a few
hundred milliseconds and a fraction of a cent, so send every item in parallel (8-16 at a
time), with a 2-second timeout and a retry on 429 and 5xx. One item per request: putting
several items in one state makes them interact. If a call fails, the item gets no verdict
and goes to the reading pass, never dropped.
