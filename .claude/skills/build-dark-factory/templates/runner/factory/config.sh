#!/usr/bin/env bash
# THE CONFIGURATION SURFACE. This is the file you edit; the rest of factory/ is
# machinery you should be able to leave alone.
#
# Everything project-specific in the runner reads from here. If you find yourself
# editing another script to change a path, a command or a marker name, that is a bug in
# this file and it should grow a variable instead - the point of concentrating it is
# that six months from now you can see your whole factory's configuration on one screen.
#
# Sourced by every script in factory/. Keep it to variable assignments; no side effects,
# nothing that can fail, nothing that prints.

# --- the agent ---------------------------------------------------------------
# Whatever is already authenticated on the machine that will run this. Not the best one.
# The factory shells out to a command and reads an exit code, so this is genuinely
# swappable in an afternoon - see references/automation.md for each agent's flags.
#
# ONE EXECUTABLE, NO ARGUMENTS. `run-workflow.sh` invokes this as "$AGENT" -p ... , so the
# whole value is treated as a single command name. `FACTORY_AGENT="npx some-agent"` or
# `"bash ./my-agent.sh"` fails with `No such file or directory` naming the entire string -
# which reads as "the agent is not installed" for something that runs fine when you type
# it. If you need arguments or a wrapper, write a one-line executable script and point
# this at that:  FACTORY_AGENT="./factory/my-agent.sh"  (with a shebang, and chmod +x).
FACTORY_AGENT="${FACTORY_AGENT:-claude}"

# Two slots decide quality: the one that PLANS and the one that IMPLEMENTS. A premium
# model in ONE of them buys most of the quality of both. Zero premium slots is what
# actually costs you.
FACTORY_MODEL_PREMIUM="${FACTORY_MODEL_PREMIUM:-opus}"
FACTORY_MODEL_CHEAP="${FACTORY_MODEL_CHEAP:-sonnet}"

# A COST guard, not a safety gate. Nothing downstream trusts it and the gate is
# identical either side of it. Set it too low and it does not save money - it throws
# away the expensive planning half of a lap that had already been paid for.
#
# A DOLLAR cap, not a turn cap, and that is not a preference. This was `--max-turns` for
# a while, which does not exist in the Claude Code CLI - the flag was accepted, silently
# ignored, and the run proceeded uncapped while every comment here claimed otherwise.
# VERIFY THE FLAGS OF YOUR AGENT BEFORE TRUSTING A CAP: a guard that silently does not
# apply is worse than no guard, because you stop watching the thing it was guarding.
#
# Measured: a plan node runs ~$1-3, an implement node ~$2-4. This is a ceiling, not a
# budget - it should be high enough that hitting it means something went wrong.
FACTORY_MAX_BUDGET_USD="${FACTORY_MAX_BUDGET_USD:-8}"

# --- the validation harness --------------------------------------------------
# THE MOST IMPORTANT LINE IN THIS FILE.
#
# One command that runs your whole gate and prints the markers below. It is component 5
# and it is the thing this template deliberately does NOT give you: what "working"
# means for your app is the one part nobody can write for you.
#
# It must exit non-zero when the software is broken, and it must print a positive marker
# for every check that RAN. See references/validation-harness.md.
FACTORY_VALIDATE_CMD="${FACTORY_VALIDATE_CMD:-python harness/ci.py}"

# The cheap subset an implementing node may run on itself while it works. Keep it fast;
# the real gate runs independently afterwards regardless of what this said.
FACTORY_VALIDATE_QUICK="${FACTORY_VALIDATE_QUICK:-python harness/ci.py --quick}"

# EMPTY IS NOT PASS, expressed as data.
#
# Every marker named here must appear in the run log or the gate refuses to merge. A
# check that never ran produces no failures, and code that asks "did anything fail?"
# reads that as success - so the gate never asks that question. It asks "did this
# specific thing report that it ran?"
#
# APP_STARTED and E2E_PASSED are not negotiable: they are the two gates that must be
# code in every factory. Add one marker per check family you build.
FACTORY_REQUIRED_MARKERS="${FACTORY_REQUIRED_MARKERS:-APP_STARTED E2E_PASSED PROTECTED_OK GATE_OK}"

# The minimum number of end-to-end steps that must have been ASSERTED, read from a lock
# file so raising it is a deliberate, human, protected edit. Set to 0 to disable.
FACTORY_E2E_FLOOR_FILE="${FACTORY_E2E_FLOOR_FILE:-.factory/locks/floor.json}"
FACTORY_E2E_FLOOR_KEY="${FACTORY_E2E_FLOOR_KEY:-e2e_steps_asserted}"

# --- state -------------------------------------------------------------------
# `github` wherever an origin remote exists, `files` for a local clone with no remote -
# which is what you want while debugging the machinery rather than the work.
FACTORY_BACKEND="${FACTORY_BACKEND:-}"

# --- the dial ----------------------------------------------------------------
# 0 workflows exist, run by hand   <- where every factory starts, and stays until a lap
#                                     has been proven by hand
# 1 accepted issue -> branch and PR open
# 2 + the validator runs and writes a verdict
# 3 + the validator AUTO-MERGES on green structural gates   <- THE TARGET. Build for this.
# 4 + self-triage, and a scheduled run files its own bugs
# 5 + writes its own issues from the mission
#
# LEVEL 3 IS THE RECOMMENDED DESTINATION and 1 and 2 are the way there, not places to
# stop: at 2 a person still merges every PR, which is the bottleneck the factory was
# built to remove. Everything expensive in this repo - the holdout, the mutation set, the
# ratchet, the two gates that are code - exists to earn 3.
#
# The SHIPPED value is still 0, deliberately. A fresh clone must not auto-merge before a
# single lap has been proven by hand, and `factory_doctor` refuses 3 while there is no
# holdout, so the dial cannot outrun the evidence. Raise it here once it has.
FACTORY_AUTONOMY="${FACTORY_AUTONOMY:-0}"

FACTORY_MAX_PARALLEL="${FACTORY_MAX_PARALLEL:-1}"
FACTORY_MAX_FIX_ATTEMPTS="${FACTORY_MAX_FIX_ATTEMPTS:-2}"

# How long a dispatch lock may outlive the run that took it. Both were already read by
# factory/orchestrator.sh and neither was written down here, so the only way to discover
# the knobs that decide when a wedged factory unwedges itself was to read the dispatcher.
# "The one file you edit" has to actually list them or it is not that file.
#
# A lock is reaped early when its recorded PID is gone (that is the common case: a reboot,
# a closed terminal, a killed run - a trap does not run when a process is KILLED), with
# GRACE minutes of slack so a run that has not yet written its PID is never reaped out
# from under itself. STALE is the fallback for the case where the PID cannot be checked at
# all. Lower STALE and a long legitimate validation gets reaped mid-flight; raise it and a
# genuinely dead lock holds a slot for that much longer.
FACTORY_LOCK_STALE_MINUTES="${FACTORY_LOCK_STALE_MINUTES:-180}"
FACTORY_LOCK_GRACE_MINUTES="${FACTORY_LOCK_GRACE_MINUTES:-5}"

# --- the stop button ---------------------------------------------------------
# Two of them, on purpose, because they fail in different places. The local file works
# with the network down; the remote label is reachable from a phone. The remote half
# FAILS CLOSED - see factory/state.py stop-requested.
FACTORY_STOP_FILE="${FACTORY_STOP_FILE:-.factory/STOP}"
FACTORY_STOP_LABEL="${FACTORY_STOP_LABEL:-factory:stop}"

# --- limits ------------------------------------------------------------------
# Crude and effective. An unsupervised agent will otherwise ship a 3,000-line PR that
# nobody can review, and "nobody can review it" is where a factory stops being auditable
# even in principle.
FACTORY_SIZE_CAP="${FACTORY_SIZE_CAP:-500}"

# The scope leash, and it is a FILE count rather than a line count on purpose. The
# failure it catches is not size: a refactor node with no scope grows a six-file PR into
# eleven and introduces a bug in one of the five it was never asked to touch - while
# staying well under the line cap the whole way. Set to 0 to disable.
FACTORY_FILE_CAP="${FACTORY_FILE_CAP:-12}"

# --- deployment (component 3) ------------------------------------------------
# THE LOOP IS NOT CLOSED UNTIL A STRANGER CAN SEE THE CHANGE. If merging does not put
# code in front of a user, you built a PR generator with extra steps.
#
# `deploy.sh` REFUSES to move the pointer when FACTORY_HEALTH_CMD is empty, on purpose:
# a deploy with no health check is a deploy that cannot fail, and a step that cannot fail
# is a comment. Set both of these before you expect a deploy to do anything.

# What a built snapshot contains. Everything the app needs to run, and nothing else.
FACTORY_BUILD_INCLUDE="${FACTORY_BUILD_INCLUDE:-src app README.md}"

# A command that starts the built snapshot and proves it worked. Run from inside the
# build directory. Not "did the process exit 0" - a process that starts, hangs and
# returns zero is indistinguishable from a healthy one without a positive marker.
FACTORY_HEALTH_CMD="${FACTORY_HEALTH_CMD:-}"

# Extended regexes that must ALL appear in the health output. Assert an outcome a user
# would notice, not a status code.
FACTORY_HEALTH_MARKERS="${FACTORY_HEALTH_MARKERS:-}"

# --- the trigger (component 2) -----------------------------------------------
# Read by factory/install-trigger.sh. Slower than feels right: a fast loop multiplies
# the cost of a mistake before you have noticed the mistake.
FACTORY_INTERVAL_MINUTES="${FACTORY_INTERVAL_MINUTES:-30}"
FACTORY_TASK_NAME="${FACTORY_TASK_NAME:-dark-factory-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo factory)")}"

# What the dispatcher actually launches. Swap this if you drive your nodes with a
# workflow engine instead of the bundled runner.
FACTORY_RUNNER="${FACTORY_RUNNER:-factory/run-workflow.sh}"

# --- escalation --------------------------------------------------------------
# THE ONLY THING THAT REACHES YOU. Everything else is written to disk and waits.
#
# Left empty, a needs-human escalation appends to .factory/needs-human.md and nothing
# else happens - which on an unattended system means you find out when you next remember
# to look. Set this to anything that can reach you: a curl to a Slack webhook, `ntfy`,
# `osascript`, `notify-send`, a msg box. It receives the reason on stdin and the target
# as $1.
#
# Keep it QUIET. If everything notifies you will mute it, and then nothing notifies.
# `needs-human` should be rare enough to be worth reading.
FACTORY_NOTIFY_CMD="${FACTORY_NOTIFY_CMD:-}"

# Defined here, ONCE, because more than one script escalates - the runner, the gate, and
# the dispatcher's fix-cap path all reach this state by different routes. Three copies of
# a notify block is three that drift, and the one that drifts is the one that goes quiet.
#
# Never fatal. An escalation whose webhook is down is still an escalation; the file write
# has already happened by the time this is called.
# THE CONTRACT, because getting it wrong produces a useless notification rather than none:
#
#   STDIN   "<target> needs a human: <reason>"   <- the whole message. Read this.
#   argv[1] "<target>"                           <- for routing or a subject line only
#
# Every example in references/setup.md reads stdin (`xargs`, `curl -d @-`, `tee`) and is
# correct. Somebody writing their own reaches for "$1" by reflex - a one-line Slack curl
# is the obvious case - and gets a 3am alert whose entire body is `.factory/prs/0001.md`:
# it tells you something is wrong and not what, which is close to no notification at all.
# Observed while testing this path. If you write your own, read stdin.
factory_notify() {              # factory_notify <target> <reason...>
  local target="$1"; shift
  if [ -z "${FACTORY_NOTIFY_CMD:-}" ]; then
    echo "NOT NOTIFIED - FACTORY_NOTIFY_CMD unset; this waits in .factory/needs-human.md"
    return 0
  fi
  if printf '%s\n' "$target needs a human: $*" | eval "$FACTORY_NOTIFY_CMD" "$target" \
       >/dev/null 2>&1; then
    echo "NOTIFIED via FACTORY_NOTIFY_CMD"
  else
    echo "NOTIFY_FAILED - the escalation is recorded in .factory/needs-human.md"
  fi
}

# --- paths -------------------------------------------------------------------
# The holdout: assertions the builder is blocked from READING, not merely from editing.
# Enforced with the agent's own deny list, because a sentence in a prompt is not
# enforcement. Move it to a sibling repo when you want this to be strong.
FACTORY_HOLDOUT_DIR="${FACTORY_HOLDOUT_DIR:-.factory/holdout}"

# Config files that must be git-ignored before any node that can commit runs. An empty
# `git check-ignore` result means your next run publishes your key.
FACTORY_SECRET_FILES="${FACTORY_SECRET_FILES:-.env secrets.json credentials.json}"

# --- EXPORT, or half of the above is decoration -----------------------------------
#
# `guard.py` reads FACTORY_SIZE_CAP and FACTORY_FILE_CAP from the PROCESS ENVIRONMENT, and
# `state.py` reads FACTORY_BACKEND the same way. Sourcing this file sets shell variables;
# it does not put them into the environment of a python child. So editing the size cap - a
# SAFETY knob - in "the one file you edit" silently did nothing, while the header above
# promises the opposite: "if you find yourself editing another script to change a value,
# that is a bug in this file". Editing this file not working is worse than that.
#
# Found by a full greenfield build. Exported BY NAME rather than with `set -a`, so adding
# a variable above and forgetting it here is a visible omission rather than a silent one.
export FACTORY_AGENT \
       FACTORY_AUTONOMY \
       FACTORY_BACKEND \
       FACTORY_BUILD_INCLUDE \
       FACTORY_E2E_FLOOR_FILE \
       FACTORY_E2E_FLOOR_KEY \
       FACTORY_FILE_CAP \
       FACTORY_HEALTH_CMD \
       FACTORY_HEALTH_MARKERS \
       FACTORY_HOLDOUT_DIR \
       FACTORY_INTERVAL_MINUTES \
       FACTORY_LOCK_GRACE_MINUTES \
       FACTORY_LOCK_STALE_MINUTES \
       FACTORY_MAX_BUDGET_USD \
       FACTORY_MAX_FIX_ATTEMPTS \
       FACTORY_MAX_PARALLEL \
       FACTORY_MODEL_CHEAP \
       FACTORY_MODEL_PREMIUM \
       FACTORY_NOTIFY_CMD \
       FACTORY_REQUIRED_MARKERS \
       FACTORY_RUNNER \
       FACTORY_SECRET_FILES \
       FACTORY_SIZE_CAP \
       FACTORY_STOP_FILE \
       FACTORY_STOP_LABEL \
       FACTORY_TASK_NAME \
       FACTORY_VALIDATE_CMD \
       FACTORY_VALIDATE_QUICK
