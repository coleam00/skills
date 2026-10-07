# The reading pass, the digest, delivery

## The reading pass

One LLM call per run over everything the decision pass kept or was unsure about, ranked by
the decision scores (keeps first, then unsure by relevance). Start from
`templates/digest_prompt.md` and fill in the user's focus and format from `PROFILE.md`.

- Give the LLM title, source, url, the first ~300 characters of the body and the category,
  not full pages. If an item needs more, fetch its full text only for the items that made
  it this far.
- The LLM makes the final keep call on unsure items, groups related items (three posts
  about one release become one entry), and writes one or two sentences each.
- **Every link stays.** The digest is a pointer, not a replacement.
- Cap the digest (default ten). If the LLM wants more, it picks the ten.
- Tell it to say plainly when an item is a rumor or a minor change, and never to call a
  changelog entry a launch unless the entry says something launched.

## Format

What R1.3 decided. The default that works for most people:

```markdown
# <Date> - <one line on what mattered today>

## <Group>
- **<Item in plain words>** - one or two sentences on what changed and why it matters to
  you. [source](url)

## Also worth a look
- one-liners with links
```

For someone who creates content, add an ideas section below the digest, generated from the
same items. It is an extension; the digest comes first.

## Delivery

Write `digests/YYYY-MM-DD.md` in the repo every run (the audit trail), then send to where
they read (a notes folder, email, a chat webhook). Delivery failure must not lose the
digest: the file is written first.

## Schedule

- The full run (fetch, filters, decision pass, reading, delivery) once a day, early morning
  local time. Windows Task Scheduler, cron, launchd or a hosted scheduler.
- Free sources can be fetched more often if they want fresher stores; paid sources stay on
  the daily run.
- Log every run: items per source, dropped per filter, decision routes, tokens, cost, wall
  time. The shadow week reads this.

## The weekly roll-up (optional)

Reads the week's stored, kept items, not the seven digests, and writes one short post:
three things that mattered and why, then a few one-liners. Same reading model, once a week.

## The shadow week

Each day the user marks what was missing and what was noise (a reply, a line in a file,
anything quick). At the end:

- **Missing:** was it in the store? If not, add the source. If it was dropped, by which
  stage? Reword the question or loosen that filter.
- **Noise:** which stage let it through? Add a code filter for facts, sharpen the question
  for judgment.

Report the week as counts and the changes made. Then it runs without supervision.
