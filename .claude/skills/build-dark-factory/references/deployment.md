# Deployment

Component 3 is the shortest to build and the easiest to skip. Skip it and you have not
built a factory; you have built a PR generator with extra steps.

> **On merge it ships, and real users get the code.**

If merging does not produce a running application, nothing downstream of the merge is
real, and the validation harness has been proving things about software nobody runs.

---

## The trap that silently kills factories

> **GitHub does not trigger workflows on commits made with the default
> `GITHUB_TOKEN`.**

This is documented behaviour, it exists to prevent infinite workflow recursion, and it
is the single most common way an autonomous loop dies quietly:

1. The agent commits and merges, authenticating with the default token.
2. Your deploy workflow has an `on: push` trigger.
3. It never fires.
4. Nothing errors. Nothing logs. No alert. The PRs keep merging and the site keeps
   serving the old build.

Two fixes:

- **Authenticate as a GitHub App** (or use a PAT) for the commits that should trigger
  downstream workflows.
- **Poll instead of pushing.** A deploy process that checks the branch on a timer
  cannot be silently skipped, because nothing had to fire for it to run. Slower to
  react, impossible to miss.

For a factory the polling option is often the better trade: this is a system whose
defining property is that nobody is watching it, so prefer the mechanism that fails
loudly over the one that fails silently.

## Two more from the same docs

- **Scheduled workflows only run from the default branch.** A cron sitting on a
  feature branch does exactly nothing, forever, with no warning.
- **On a public repo, GitHub disables scheduled workflows after 60 days with no
  repository activity.** A factory that goes quiet gets switched off for being quiet -
  and then stays off, which looks identical to "it had nothing to do."

Both are worth a note in `FACTORY.md`, because both present as "the factory stopped
working and I cannot see an error."

---

## Deploy strategies

Pick the simplest one that gives a rollback.

| Strategy | How | Rollback | Good when |
|---|---|---|---|
| **Blue / green** | build the inactive colour, health-check it, flip the proxy upstream, stop the old one | flip back; the old build is still warm | a long-running app you control the host for |
| **Platform deploy** | push to a platform that builds and swaps for you | platform's own rollback | you would rather not own the host |
| **Container tag swap** | build, tag, restart against the new tag | retag the previous image | already containerised |
| **Static publish** | build artefacts, publish to a CDN | republish the previous build | front-end only |

Whatever the choice, it must **no-op safely when nothing changed**. An unattended
deploy loop runs far more often than it deploys, and a deploy path that does work on
every tick will eventually do damage on a tick where nothing happened.

### The health check is part of the deploy, not a nicety

Never swap traffic onto a build that has not answered a health check. In an unattended
system this is the last gate before real users, and it is the only one that runs after
the merge.

---

## Wiring it to the loop

The deploy is downstream of the merge, and it should be observable from the same place
everything else is:

1. Merge happens (squash, so history stays readable and rollback is one revert).
2. Deploy triggers - by App-authenticated push, or by poll.
3. Health check gates the traffic swap.
4. **The result is visible somewhere the factory can read.** A status endpoint, a
   deploy log the scheduled test can check.

That last point matters at level 4. If a scheduled comprehensive test can read the
live health of the deployed app, it can file its own issue when the deployment is
broken - which is how the loop closes without a human noticing first.

---

## What to tell the user

- **The loop is not closed until a stranger can see the change.** Everything before
  that is a PR generator.
- **Prefer the mechanism that fails loudly.** Polling over push triggers, health
  checks over assuming, explicit markers over the absence of errors. This is the same
  principle as *empty is not pass*, applied to infrastructure.
- **Decide the rollback before going unattended.** "I would fix forward" is a valid
  answer, but it has to be an answer, not a discovery made during the incident.
