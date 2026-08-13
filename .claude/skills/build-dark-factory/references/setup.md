# Setup: the machine, the prerequisites, and the schedule

Everything in this file is a thing that broke a real factory. None of it is interesting,
all of it is load-bearing, and it is the half of the project that nobody writes down -
you can have five perfect components and a factory that has never completed a lap because
line endings got rewritten on checkout.

Read this in **Phase 6**, when the trigger goes on. Skim the prerequisites in Phase 0b so
you refuse at the start rather than halfway through.

---

## Prerequisites, before the interview

Check these while inspecting the repo. Each one is a refusal if it is missing and cannot
be arranged.

| | Why it is on the list |
|---|---|
| **A coding agent, authenticated on the machine that will run the factory** | Not the best one. The one that works today. |
| **`gh` authenticated**, if state lives on GitHub | The dispatcher, the gate and the merge all shell out to it. |
| **A machine that stays on** | A factory on a laptop that sleeps is a factory that runs when you happen to be awake, which is the thing you were trying to stop doing. |
| **A way to start the app** | Component 5 has nothing to stand on without it. |
| **A test command that runs** | A dark factory built on zero checks is a machine for merging plausible code. |
| **Somewhere the app can actually run for E2E** | Ephemeral CI runners make long E2E and app-startup awkward. Check before choosing. |

### The credential problem nobody solves for you

**Agent credentials expire, silently, mid-run.** Every agent, no exception. The factory
will present this as a node that failed for an unrelated reason.

- Check the expiry of whatever you authenticated with, and put its renewal in the same
  place you put the cron.
- Have the runner read the agent's own JSON result and report the real terminating
  reason. `node_failure.py` in the runner template does this: budget exhaustion, a tool
  denial, a crash and a refusal are four different things and only three are bugs.
- A node that exits 0 having done nothing is the normal shape of this failure. **Assert
  on the artifact, not the exit code.** A run that produced no commit, no PR and no diff
  did not succeed, whatever it returned.

---

## The platform tax

### Line endings will break every script, on a machine you are not looking at

If the repo is ever checked out on Windows with `core.autocrlf` on, every `*.sh` gets
CRLF, and on the Linux box that runs the factory each one fails with:

```
bad interpreter: /usr/bin/env bash^M
```

which reads as *"the file is missing"*. Pin it, in the repo, so it does not depend on
anyone's git config:

```gitattributes
* text=auto eol=lf
*.sh text eol=lf
```

### Windows path length

`git worktree add` fails with "Filename too long" once a worktree path plus a vendored
file exceeds 260 characters. The validator's worktree path is longer than the
implementer's by exactly the length of the word it adds, so this shows up on validation
and not on implementation, which sends you looking in the wrong place.

```bash
git config core.longpaths true
```

Also key worktree paths on the issue *number*, not the issue slug.

### Encoding, on anything that crosses a process boundary

Windows defaults stdio to the ANSI codepage. A correct rejection comment, piped from one
process to another, arrived on GitHub with every non-ASCII character replaced by U+FFFD -
and nothing noticed, because the only thing checked afterwards was the exit code.

```bash
export PYTHONIOENCODING=utf-8
```

and decode subprocess output explicitly. `subprocess(text=True)` uses the platform
codepage, which means a *verifier* can fail to read an artifact that is perfectly fine and
report it as broken. A false alarm costs exactly as much trust as a missed failure.

---

## Before the first workflow that can commit

Run this. It takes a second and it is the difference between a mistake and a publication:

```bash
git check-ignore -v .env secrets.json credentials.json <every-config-file-with-a-token>
```

**Empty output means your next run publishes your key.** A `git add -A` inside a PR step
sweeps up whatever was not ignored, and on a public repo that is publication - rotating
afterwards is the cleanup, not the fix.

Being unable to *edit* a protected file does not stop `git add -A` from committing one
that appears for the first time. Put the check in the workflow as a node, not in a
checklist a human reads. The runner template does this in its pre-flight.

---

## The schedule

### Cron, on a machine that stays on

```cron
*/30 * * * * cd /path/to/repo && bash factory/orchestrator.sh >> /var/log/factory.log 2>&1
```

**Every 30 minutes. Slower than feels right.** A fast loop multiplies the cost of a
mistake before you have noticed the mistake.

Capture stdout and stderr per run. The first thing you will want, on the morning after
the first unattended night, is the log of a run that did nothing.

### systemd timer, if you want the run not to overlap itself

A timer with `OnUnitInactiveSec` starts counting after the previous run *finishes*, which
a cron does not. Worth it once a lap takes longer than the interval.

### Windows Task Scheduler

Register the task to run at logon with restart-on-failure. Note that it only runs while
someone is logged in unless you configure it otherwise - a detail that presents as "the
factory stopped overnight".

### GitHub Actions, and the two traps

If you schedule in Actions instead:

- **Scheduled workflows only run from the default branch.** A cron sitting on a feature
  branch does exactly nothing, forever, with no warning.
- **On a public repo, GitHub disables scheduled workflows after 60 days with no
  repository activity.** A factory that goes quiet gets switched off for being quiet, and
  then stays off - which looks identical to "it had nothing to do."

And the one that kills deploys rather than dispatches: **GitHub does not trigger workflows
on commits made with the default `GITHUB_TOKEN`.** See `deployment.md`.

---

## Turning it on

The dial is enforced in code, not documented in a file. `orchestrator.sh` refuses to
dispatch below `FACTORY_AUTONOMY=1` and holds each later action at its own level.

```bash
bash factory/orchestrator.sh --dry-run          # says what it would do, does nothing
FACTORY_AUTONOMY=1 bash factory/orchestrator.sh # one invocation, not persisted
```

Set it in the environment for **one invocation** first, and only put it in the cron once a
full cycle at that level has been watched. Step up 1, then 2, then **3** - watching a cycle
at each is what earns the next, not a reason to stop.

**Level 3 is where this is meant to end up.** Levels 1 and 2 are how you get there safely;
neither is the destination. `factory_doctor` refuses 3 while there is no holdout, so the
dial cannot outrun the evidence.

### The stop button, and testing it on purpose

Two of them, because they fail in different places:

1. **A local kill file.** Works with the network down, which is when you most want it.
2. **A remote label.** Reachable from a phone, which is the entire reason it exists.

**The remote half must fail closed.** "Remove a label to stop" is the obvious design and
it is backwards: an absent label cannot be distinguished from an API call that failed to
return it, so a network blip reads as "carry on". Make it a label you ADD, and treat any
error listing it as stopped.

**Use it once on purpose before going unattended**, and write the date down. A stop button
that has never been used is a stop button nobody knows works.

---

## The first unattended night

- **Instrument tokens on day one, not after the first invoice.** Cost projections for
  this are wrong by 10-20x in the same direction every time. Record the cost inside a
  `trap`, so it survives the run failing - which is exactly when you most want to know
  what it cost.
- **Concurrency starts at one.** Raise it only after the serial version is boring, and add
  a per-target lock when you do, or two runs will operate on the same PR and the second
  will judge a tree the first is still editing.
- **Release the concurrency lock from a trap, not from the next statement.** `set -e` is
  inherited by a background subshell, so a workflow that exits non-zero - an escalation, a
  blocked gate, anything - skips the release and wedges the dispatcher forever. Every
  later run then logs "at capacity, nothing dispatched" and exits 0, which looks exactly
  like a factory with nothing to do.
- **Push before you dispatch.** The factory's view of the world is `origin`. Unpushed
  local work is invisible to it, and it will confidently build against a past that no
  longer exists, with every marker green.
- **Exactly one escalation channel, and keep it quiet.** If everything notifies, you mute
  it, and then nothing notifies.

### Wiring the one channel

`needs-human` is the only state a human must act on, so it is the only one allowed to
interrupt one. Everything else this factory writes waits to be found - and on an
unattended system, "waits to be found" means you learn about it when you next remember to
look. Set `FACTORY_NOTIFY_CMD` in `factory/config.sh`; it receives the reason on stdin and
the target as `$1`, and it is called from all three routes into `needs-human` (the runner,
a blocked gate, and the fix-attempt cap).

**The message arrives on STDIN.** `argv[1]` is only the target, for routing or a
subject line. Every example below reads stdin; if you write your own and reach for
`"$1"` by reflex - a one-line Slack curl is the obvious case - you get an alert whose
whole body is `.factory/prs/0001.md`, which tells you something is wrong and not what.

```bash
# Slack incoming webhook
FACTORY_NOTIFY_CMD='xargs -0 -I{} curl -s -X POST -H "Content-type: application/json" \
  -d "{\"text\":\"{}\"}" "$SLACK_WEBHOOK_URL"'

# ntfy.sh - a phone notification, no app to write
FACTORY_NOTIFY_CMD='curl -s -d @- https://ntfy.sh/my-factory-topic'

# macOS desktop
FACTORY_NOTIFY_CMD='xargs -0 -I{} osascript -e "display notification \"{}\" with title \"factory\""'

# Linux desktop
FACTORY_NOTIFY_CMD='xargs -0 -I{} notify-send "dark factory" "{}"'

# a file you actually watch, if you would rather tail than be pinged
FACTORY_NOTIFY_CMD='tee -a /var/log/factory-escalations.log'
```

**Test it the same way you test the stop button: on purpose, once.** Point the runner at
an issue that does not exist and confirm the message arrives.

```bash
bash factory/run-workflow.sh implement-issue issues/does-not-exist.md
```

Leaving it unset is a legitimate choice while you are still driving laps by hand, and the
runner says so out loud rather than pretending - `NOT NOTIFIED - FACTORY_NOTIFY_CMD
unset; this waits in .factory/needs-human.md`. Do not go to level 3 that way.
