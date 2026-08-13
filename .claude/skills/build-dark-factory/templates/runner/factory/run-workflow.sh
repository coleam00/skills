#!/usr/bin/env bash
# Run one workflow. The local runner.
#
#   bash factory/run-workflow.sh <workflow> <target>
#
# A target is `gh:issue:<n>` / `gh:pr:<n>` on the GitHub backend, or a path to
# `issues/<id>.md` / `.factory/prs/<id>.md` on the file backend. Which one you are on is
# decided by factory/state.py; this script reads it off the target and otherwise does not
# care, which is the property that let the move to GitHub be a change to two scripts
# rather than to every node.
#
# THIS FILE IS THE ORCHESTRATOR. There is no second definition of the pipeline.
#
# There used to be: factory/workflows/*.yaml described the same DAG for a workflow engine
# that was never wired up. Nothing executed them, so they drifted -- and what they drifted
# into was a `deny_paths: .factory/holdout/**` entry that made the holdout read-block look
# enforced when the only thing enforcing it was a sentence in a prompt. A stale spec that
# invents a safety property is worse than no spec. The YAMLs are deleted and the deny is
# now real, below, via --disallowedTools.

set -euo pipefail

WORKFLOW="${1:?workflow name}"
TARGET="${2:?target: gh:issue:<n>, gh:pr:<n>, or a path}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# See factory/state.py. Every `python` in this script writes text that ends up on a pull
# request or an issue, and the default codepage on Windows mangles it silently.
export PYTHONIOENCODING=utf-8

# Everything project-specific lives in one file. If you are about to hardcode a path or
# a command anywhere below this line, put it in config.sh instead.
# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

# A FALLBACK, because escalate() calls this and an escalation must never be the thing
# that fails. `factory_notify` is defined in config.sh - but config.sh is the file you
# are told to edit, and an older or hand-customised copy will not have it. Observed:
# the runner escalated correctly, then died with `factory_notify: command not found`
# INSIDE the escalation, taking the message with it. A dependency added to the one path
# that runs when everything else has already gone wrong needs a floor under it.
command -v factory_notify >/dev/null 2>&1 || factory_notify() {
  echo "NOT NOTIFIED - factory/config.sh defines no factory_notify (old copy?); recorded in .factory/needs-human.md"
}

AGENT="$FACTORY_AGENT"
MODEL_PREMIUM="$FACTORY_MODEL_PREMIUM"
MODEL_CHEAP="$FACTORY_MODEL_CHEAP"
# Sized from measured laps. The first genuinely
# multi-part issue exhausted 60 turns and escalated having written nothing, AFTER the
# premium plan node had already been paid for. A cap that is too low does not save
# money, it throws away the expensive half of the lap. This is a COST guard and not a
# safety gate: nothing downstream trusts it, and the gate is identical either side of it.
MAX_BUDGET="$FACTORY_MAX_BUDGET_USD"

# --- which backend, read off the target -------------------------------------
# Not from an env var. A workflow handed `gh:pr:4` is working on a pull request whatever
# the environment says, and a mismatch between the two is the kind of thing that only
# shows up as a merge into the wrong place.
case "$TARGET" in
  gh:*) GH=1 ;;
  *)    GH=0 ;;
esac

# The base ref. On GitHub the base is what the REMOTE says main is, not what this
# checkout last fetched -- a stale local main computes the merge base against a commit
# that is no longer the tip and the guard's three-dot diff quietly widens.
if [ "$GH" -eq 1 ]; then
  git fetch --quiet origin main || { echo "cannot fetch origin/main; refusing to run against a stale base"; exit 1; }
  BASE="origin/main"
else
  BASE="main"
fi

RUN="$(date -u +%Y%m%dT%H%M%S)-$WORKFLOW"
# ABSOLUTE, deliberately. Every node cd's into its worktree before running, so a relative
# run directory resolves inside the worktree -- where it does not exist. The first real
# headless lap failed exactly this way: every node's prompt render, stdout capture and
# stderr capture went to a path that was not there, all three nodes "failed", and the
# workflow escalated. It failed closed, which is the right outcome, but the cause was
# eight characters of path.
RUNDIR="$ROOT/.factory/runs/$RUN"
# the prompts already write ".factory/runs/{{run}}/...", so substituting a relative
# prefix here rendered ".factory/runs/.factory/runs/<id>/priming.md". The plan node then
# could not read its priming, produced its plan in the reply instead of writing the file,
# and the implement node correctly refused to invent one and escalated.
mkdir -p "$RUNDIR/nodes"

export FACTORY_RUN_ID="$RUN"

# Token instrumentation is on from the first run, not added later (FACTORY_RULES.md 8) --
# so it has to survive the run failing, which is when you most want to know what it cost.
# The teardown step in the YAML says `always: true`; bash does not honour a YAML comment,
# and the final `cost.py record` line was unreachable on every escalation and every
# blocked gate. A trap is what `always` actually means here.
trap 'python factory/cost.py record "$RUN" >/dev/null 2>&1 || true' EXIT

log() { echo "[$(date -u +%FT%TZ)] [$WORKFLOW/$TARGET] $*"; }

state()   { python factory/state.py "$@"; }
# `|| true`, and it is the difference between an escalation and a silent death.
#
# Under `set -euo pipefail`, a `grep` that matches nothing returns 1, the pipeline
# returns 1, and `set -e` kills the script THERE - before the `[ -n "$BRANCH" ] ||
# escalate` on the next line ever runs. So a PR record missing a field did not escalate,
# did not reach needs-human, did not notify: the workflow exited 1 having printed one
# line, which is indistinguishable from a crash and looks like nothing at all in a log
# nobody is watching.
#
# The check that handles the missing field was written correctly and was unreachable.
# Same shape as a red gate that could never reach the fix node: the error path existed,
# and the language got there first.
read_fm() { python factory/state.py get "$2" 2>/dev/null | grep "^$1=" | head -1 | cut -d= -f2- || true; }
note()    { python factory/state.py comment "$1"; }   # body on stdin

escalate() {            # escalate <reason>
  log "ESCALATE: $*"
  python factory/state.py set "$TARGET" state=needs-human || true
  echo "- $(date -u +%FT%TZ)  $TARGET  ($WORKFLOW)  $*" >> .factory/needs-human.md

  # AND THE ISSUE BEHIND IT. `gate.sh`'s fail() has done this for a while, with a comment
  # explaining why; the other two escalation routes never learned it. So a PR that hit the
  # fix cap went to needs-human while ITS ISSUE stayed `in-progress` - unlabelled, invisible
  # as a problem, and `state.py next` cheerfully moved on to the next issue. The factory
  # carries on while an escalated piece of work sits in a state that means "being worked on"
  # and nothing is. FACTORY_RULES.md 7 says escalation stops activity on that issue AND its
  # PR; one of the three routes implemented it.
  ESC_ISSUE="$(python factory/state.py get "$TARGET" 2>/dev/null | grep '^issue=' | head -1 | cut -d= -f2- || true)"
  if [ -n "${ESC_ISSUE:-}" ] && [ "$ESC_ISSUE" != "$TARGET" ]; then
    python factory/state.py set "$ESC_ISSUE" state=needs-human >/dev/null 2>&1 || true
    echo "- $(date -u +%FT%TZ)  $ESC_ISSUE  ($WORKFLOW)  its PR $TARGET escalated: $*" >> .factory/needs-human.md
  fi

  # THE ONE THING THAT REACHES A HUMAN. Everything else this factory writes waits to be
  # found. `needs-human` is the only state a human must act on, so it is the only state
  # allowed to interrupt one - and if it cannot, "unattended" quietly means "unmonitored".
  #
  # Never fatal: an escalation that fails because a webhook is down must still be an
  # escalation. The file write above already happened.
  log "$(factory_notify "$TARGET" "($WORKFLOW) $*")"
  if [ "$GH" -eq 1 ]; then
    # Assembled in one process, like every other human-facing write. FACTORY_RULES.md 10.1.
    python factory/state.py escalate-note "$TARGET" "$WORKFLOW" "$*" || true
  fi
  exit 3
}

# THE BACKSTOP FOR THE ENTIRE CLASS OF FAILURE DESCRIBED AT read_fm ABOVE.
#
# That comment diagnoses the shape exactly: under `set -euo pipefail` an unguarded
# command returning non-zero kills the script BEFORE the escalate on the next line, and
# the result is indistinguishable from nothing having happened. It was found and fixed
# four separate times by accident -- read_fm, fix-pr, validate-pr, gate.sh -- each time as
# an instance. Auditing every `set -e` script for the shape found three more still live,
# including one on the protected-path guard, so fixing instances was never going to
# converge. Two facts made every one of them invisible rather than merely fatal:
#
#   1. nothing in this script trapped ERR, so a death printed nothing about itself, and
#   2. the orchestrator dispatches this runner into a BACKGROUND subshell and never reads
#      its exit status, so nothing downstream noticed either.
#
# Worked example, the one that was live: an issue with no `title:` line made
#   TITLE="$(grep -m1 '^title:' "$ISSUE_FILE" | ...)"
# return 1, which killed the run at that line. The issue was never moved to `in-progress`
# (that happens further down), so `state.py next` handed the SAME issue back on the next
# tick, and the factory re-dispatched a run that could only die, every tick, forever --
# logging a cheerful DISPATCH line each time. Busy, progressing at zero, notifying nobody.
#
# THIS TRAP CANNOT CHANGE CONTROL FLOW. `set -e` already terminates the script at exactly
# these points; the trap only makes the termination say why and route through escalate(),
# which parks the work and notifies. It converts silent death into a loud stop.
#
# Deliberately NOT `set -E` (errtrace): without it the trap fires for top-level commands
# only, which is where every instance found lives. With it, ERR also fires inside command
# substitutions and subshells, where an escalate() would exit the SUBSHELL and leave the
# parent running -- a duplicate, half-applied escalation that is worse than the disease.
on_unguarded_error() {  # on_unguarded_error <rc> <line> <command>
  trap - ERR            # never recurse: escalate() runs commands of its own
  log "RUNNER_FAULT line $2 exited $1: $3"
  escalate "the runner died at line $2 (exit $1) running: $3 -- this is an unguarded command failure, not a decision about the work"
}
trap 'on_unguarded_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

# --- identifiers -------------------------------------------------------------
# ISSUE_NUM keys the worktree path. Windows MAX_PATH is 260 characters and this repo
# already sits deep under a temp directory; the validator's path is 9 characters longer
# than the implementer's ("validate-"), and that alone pushed a vendored skill file over
# the limit. `git worktree add` then failed with "Filename too long" and the validator
# escalated on a path length. core.longpaths is also set on the repo; this is the belt to
# that pair of braces.
if [ "$GH" -eq 1 ]; then
  ISSUE_NUM="${TARGET##*:}"
  ISSUE_ID="issue-$ISSUE_NUM"
else
  ISSUE_ID="$(basename "$TARGET" .md)"
  ISSUE_NUM="$(printf '%s' "$ISSUE_ID" | grep -oE '^[0-9]+' || printf '%s' "$ISSUE_ID")"
fi

# --- the issue, as a file a node can read ------------------------------------
# THE JOIN FACTORY_RULES.md 11 HAD NO ROW FOR. Every node prompt takes `{{issue}}` and
# opens it. An issue that lives behind an API cannot be opened, so it is rendered here to
# one path, ONCE, before any node runs. Rendering it once is also what keeps every node
# judging the same text: re-fetching per node would let a mid-run edit change what the
# judge thinks was asked for.
materialise() {         # materialise <issue-target>
  ISSUE_FILE="$RUNDIR/issue.md"
  python factory/state.py body "$1" > "$ISSUE_FILE" \
    || { echo "could not read $1"; return 1; }
  log "ISSUE_MATERIALISED $1 -> $ISSUE_FILE ($(wc -l < "$ISSUE_FILE") lines)"
}

# --- one node ----------------------------------------------------------------
# Each node gets a FRESH agent session. Not a performance choice: a node that inherits
# the previous node's context inherits the previous node's reasoning, and the whole
# holdout argument (FACTORY_RULES.md 9) rests on some nodes not having seen it.
#
# HOLDOUT_DENY is passed to every node. The builder must not READ the assertions it is
# judged against, and until now that was a sentence in a prompt: the deny list lived in
# factory/workflows/*.yaml, which nothing executed. guard.py blocked holdout WRITES on
# the committed diff, so the wall was real in one direction and imaginary in the other.
# A node with Read+Glob+Grep could open .factory/holdout/e2e.py and write code aimed at
# the exact assertions. --disallowedTools is enforced by the agent, not by the prompt.
HOLDOUT_DENY="Read($FACTORY_HOLDOUT_DIR/**) Glob($FACTORY_HOLDOUT_DIR/**) Grep($FACTORY_HOLDOUT_DIR/**)"

node() {                # node <name> <model> <prompt-file> <allowed-tools>
  local name="$1" model="$2" prompt="$3" tools="$4"
  log "NODE $name (model=$model)"

  mkdir -p "$RUNDIR/nodes"
  local rendered="$RUNDIR/nodes/$name.prompt.md"
  if ! sed -e "s|{{issue}}|${ISSUE_FILE:-$TARGET}|g" \
           -e "s|{{issue_id}}|$ISSUE_ID|g" \
           -e "s|{{issue_ref}}|$TARGET|g" \
           -e "s|{{run}}|$RUN|g" \
           -e "s|{{branch}}|${BRANCH:-}|g" \
           -e "s|{{base}}|$BASE|g" \
           -e "s|{{prfile}}|${PRFILE:-}|g" \
           -e "s|{{attempts}}|${ATTEMPTS:-0}|g" \
           -e "s|{{rundir}}|$RUNDIR|g" \
           -e "s|{{findings}}|${FINDINGS:-}|g" \
           -e "s|{{gatelog}}|${FINDINGS_LOG:-}|g" \
           -e "s|{{quick}}|$FACTORY_VALIDATE_QUICK|g" \
           "$prompt" > "$rendered"; then
    log "NODE_FAILED $name -- could not render the prompt to $rendered"
    return 1
  fi

  # AN UNRENDERED PLACEHOLDER IS A PROMPT THAT LIES, and it fails silently in the worst
  # possible way: the node is handed a path like `.factory/runs/{{prev_run}}/verdict.json`,
  # opens nothing, and carries on. It does not crash and it does not refuse - it just works
  # from no evidence, and produces something confident and unfounded.
  #
  # Found on the fix node, which asked for the validator's findings through a placeholder
  # this renderer never substituted. Every fix attempt would have been a guess at what the
  # validator objected to.
  #
  # Fatal, not a warning: a node reasoning from a file that does not exist is worse than a
  # node that did not run.
  if grep -qE '\{\{[a-z_]+\}\}' "$rendered"; then
    log "NODE_FAILED $name -- the rendered prompt still contains $(grep -ohE '\{\{[a-z_]+\}\}' "$rendered" | sort -u | tr '\n' ' ')- the runner does not substitute that. A node cannot read a path that was never filled in."
    return 1
  fi

  # shellcheck disable=SC2086 -- HOLDOUT_DENY is a deliberate word list, not one argument.
  if ! "$AGENT" -p "$(cat "$rendered")" \
        --model "$model" \
        --allowedTools "$tools" \
        --disallowedTools $HOLDOUT_DENY \
        --permission-mode acceptEdits \
        --add-dir "$ROOT" \
        --max-budget-usd "$MAX_BUDGET" \
        --output-format json \
        > "$RUNDIR/nodes/$name.json" 2> "$RUNDIR/nodes/$name.err"; then
    # WHY it failed, not just that it did. The agent records the reason in its own JSON,
    # and running out of turns is a BUDGET the operator set -- a completely different thing
    # from a node that refused, crashed, or was denied a tool it needed. All three used to
    # escalate as "a build node failed", which sends whoever reads it at 3am looking for a
    # bug that is not there. Naming the cause is most of what an escalation is worth.
    #
    # Written to a FILE, not a variable: nodes run inside a subshell, so a variable set
    # here never reaches the escalate() that reports it.
    python factory/node_failure.py "$RUNDIR/nodes/$name.json" "$name" "$MAX_BUDGET" \
      > "$RUNDIR/NODE_FAILURE" 2>/dev/null || echo "$name: reason unavailable" > "$RUNDIR/NODE_FAILURE"
    log "NODE_FAILED $(cat "$RUNDIR/NODE_FAILURE")"
    sed 's/^/    /' "$RUNDIR/nodes/$name.err" | tail -20
    return 1
  fi

  # A node can be DENIED A TOOL and still exit 0. The implement node did exactly that: it
  # asked twice to run a `python -c` its allowlist did not cover, was refused, replied "the
  # command needs approval from you to run", and exited SUCCESSFULLY having changed
  # nothing. The workflow reported "produced no file changes at all" -- true, a good
  # backstop, and the wrong cause.
  #
  # Recorded and printed, but NOT fatal, and that distinction was itself learned here: the
  # plan node is denied tools on almost every run, asks anyway, works around it and writes
  # a good plan. A denial says a node wanted something it could not have. Whether that
  # mattered is decided by whether the node produced anything, which is checked downstream.
  python factory/node_failure.py --denials-only "$RUNDIR/nodes/$name.json" "$name" \
    > "$RUNDIR/nodes/$name.denials" 2>/dev/null || true
  if [ -s "$RUNDIR/nodes/$name.denials" ]; then
    log "NODE_DENIED $(head -c 400 "$RUNDIR/nodes/$name.denials")"
    cat "$RUNDIR/nodes/$name.denials" >> "$RUNDIR/DENIALS"
  fi
  log "NODE_OK $name"
}

# Make a worktree path usable, whatever state a previous run left it in.
#
# `git worktree remove --force` can drop git's record and still leave the directory on
# disk -- routine on Windows, where an agent process may still hold a handle when the
# teardown runs. The next run then fails at `worktree add` and escalates, and the factory
# is wedged on a directory rather than on anything real. An unattended system has to be
# able to start from the mess its previous self left.
prepare_worktree_path() {   # prepare_worktree_path <path>
  local wt="$1"
  git worktree remove "$wt" --force >/dev/null 2>&1 || true
  git worktree prune >/dev/null 2>&1 || true
  [ -e "$wt" ] && rm -rf "$wt"
  return 0
}

# --- the per-target lock, for runs started BY HAND ---------------------------
#
# THE HOLE THIS CLOSES. The lock lived entirely in orchestrator.sh, so it protected two
# dispatchers from each other and nothing else. But Phase 7 of the skill tells you to
# "run the walking skeleton by hand: one real issue, all the way to a PR you merge
# yourself" - and a hand-run invokes THIS script directly, taking no lock at all.
#
# So the documented human workflow bypassed the one mechanism that stops two runs
# operating on the same target. Observed: a cron tick dispatched `triage issues/0011`
# seventeen seconds before a hand-driven run of the same workflow on the same repo. The
# second judges a tree the first is still writing, which is exactly what the lock exists
# to prevent.
#
# When the orchestrator dispatched us it exports FACTORY_LOCK_HELD and we trust it - it
# already holds the lock and releases it on its own trap. Otherwise we take one, with the
# same key and the same atomic O_EXCL create, and release it on exit.
if [ -z "${FACTORY_LOCK_HELD:-}" ]; then
  SELF_LOCKDIR=".factory/locks-runtime"
  mkdir -p "$SELF_LOCKDIR"
  SELF_KEY="$(echo "${WORKFLOW}-${TARGET}" | tr '/.:' '---')"
  SELF_LOCK="$SELF_LOCKDIR/$SELF_KEY.lock"
  set -C
  if ! echo "$$ $(date -u +%FT%TZ) hand-run" > "$SELF_LOCK" 2>/dev/null; then
    set +C
    echo "REFUSED: $WORKFLOW $TARGET is already in flight ($SELF_LOCK)."
    echo "  Another run - a cron tick, or another terminal - holds this target. Two runs on"
    echo "  one target means the second judges a tree the first is still editing."
    echo "  Wait for it, or remove the lock if you know its process is gone."
    exit 4
  fi
  set +C
  trap 'rm -f "$SELF_LOCK"' EXIT INT TERM
  log "LOCK_TAKEN $SELF_LOCK (hand-run)"
fi

# --- pre-flight, before anything that could commit ---------------------------
# FACTORY_RULES.md 5.2. It mattered when this repo was local-only and it matters more
# now: a `git add -A` that sweeps up a token no longer publishes it to a disk, it
# publishes it to a remote, and the remote keeps it after the delete.
for f in $FACTORY_SECRET_FILES; do
  git check-ignore -q "$f" || escalate "PREFLIGHT: $f is not gitignored; a git add -A would publish it"
done
log "PREFLIGHT_OK backend=$([ "$GH" -eq 1 ] && echo github || echo files) base=$BASE"

case "$WORKFLOW" in

  implement-issue)
    materialise "$TARGET" || escalate "could not read the issue"
    # `|| true` for the read_fm reason, and this one was LIVE. An issue file with no
    # `title:` line made this grep return 1 and killed the run right here -- before the
    # issue was moved to `in-progress`, so the dispatcher handed the same issue back every
    # tick and re-ran a workflow that could only die. Nothing else in this system requires
    # a title: state.py prints `i.get('title', i.get('issue',''))` and factory_doctor does
    # not check for one, so an untitled issue is a supported input everywhere except the
    # one line that read it. On the GitHub backend `state.py body` always emits a title,
    # which is why this only ever bit the file backend -- the one a local factory uses.
    TITLE="$(grep -m1 '^title:' "$ISSUE_FILE" | cut -d: -f2- | sed 's/^ *//' || true)"
    [ -n "$TITLE" ] || TITLE="$(basename "$ISSUE_FILE" .md)"

    if [ "$GH" -eq 1 ]; then
      BRANCH="factory/issue-$ISSUE_NUM"
      PRFILE="$RUNDIR/pr.md"
    else
      BRANCH="factory/$ISSUE_ID"
      PRFILE=".factory/prs/$ISSUE_ID.md"
    fi
    WT=".worktrees/i$ISSUE_NUM"

    prepare_worktree_path "$WT"
    git rev-parse --verify --quiet "$BRANCH" >/dev/null && git branch -D "$BRANCH" >/dev/null 2>&1 || true
    git worktree add "$WT" -b "$BRANCH" "$BASE" >/dev/null 2>&1 || escalate "could not create worktree $WT"
    python factory/state.py set "$TARGET" state=in-progress || escalate "illegal state transition"

    (
      cd "$WT"
      node prime     "$MODEL_CHEAP"   "$ROOT/factory/prompts/prime.md" \
           "Read,Glob,Grep,Bash(git log:*),Bash(git ls-files:*)"
      node plan      "$MODEL_PREMIUM" "$ROOT/factory/prompts/plan.md" \
           "Read,Glob,Grep,Write"
      # `Bash(python -c:*)` added 2026-08-10. The node could previously execute exactly one
      # command -- the quick gate -- so it could not measure anything, and it was handed an
      # issue that is entirely about counting things on a screen. It asked to run a
      # one-liner, was refused, and stopped to ask a human who was not there.
      #
      # This does weaken the `--quick`-only leash, and the leash was never what enforced
      # the property anyway. What stops a builder tuning against the gate is that the
      # VALIDATOR re-runs everything independently, that 22 mutations must all be caught,
      # and that the ratchet refuses a quieter harness. Tool scoping was a nudge, and
      # keeping a nudge that costs a whole lap is not a trade worth making.
      node implement "$MODEL_CHEAP"   "$ROOT/factory/prompts/implement.md" \
           "Read,Glob,Grep,Edit,Write,Bash(python -c:*),Bash($FACTORY_VALIDATE_QUICK)"
    ) || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "$(cat "$RUNDIR/NODE_FAILURE" 2>/dev/null || echo 'a build node failed, reason not recorded')"; }

    # An explicit escalation file beats a silent no-op. The plan node stops only for the
    # short list in prompts/plan.md; when it does, it says so here, and this is the only
    # path that turns that into a state change.
    if [ -s "$RUNDIR/ESCALATE" ]; then
      git worktree remove "$WT" --force >/dev/null 2>&1 || true
      escalate "$(head -c 800 "$RUNDIR/ESCALATE")"
    fi

    # ASSUMPTIONS ARE NOT ESCALATIONS. They ride through the build and hold the MERGE.
    #
    # THE FAILURE THIS REPLACES. The plan node used to be told to stop for "an answer to
    # any other MISSION open question", so one unmade product decision blocked every issue
    # downstream of it. Four issues filed against one game produced four escalations, zero
    # PRs, and the SAME question asked four times - because an open question in a PRD was
    # being read as "you may not propose" when the author meant "I have not decided". The
    # more honest the PRD, the less the factory could do.
    #
    # Now the node decides, records what it assumed, and builds. The assumption travels
    # into the PR record and `gate.sh` refuses the AUTO-merge on it - the same mechanism
    # that already holds a merge on an uncalibrated threshold. So the work is built,
    # validated, and waiting with the reasoning at the top, and the human answers a
    # concrete question about a running thing rather than an abstract one in the dark.
    if [ -s "$RUNDIR/ASSUMPTIONS" ]; then
      mkdir -p .factory/assumptions
      cp "$RUNDIR/ASSUMPTIONS" ".factory/assumptions/$ISSUE_ID.txt" 2>/dev/null || true
      log "ASSUMPTIONS_RECORDED $(grep -c . "$RUNDIR/ASSUMPTIONS" 2>/dev/null || echo 0) - the build continues; the MERGE will be held"
      sed 's/^/    /' "$RUNDIR/ASSUMPTIONS" | head -20
    fi

    # A follow-up the node could not build, from an issue it mostly could. Recorded rather
    # than lost: partially building an issue is right, silently dropping the rest is not.
    if [ -s "$RUNDIR/FOLLOWUP" ]; then
      mkdir -p .factory/followups
      cp "$RUNDIR/FOLLOWUP" ".factory/followups/$ISSUE_ID.md" 2>/dev/null || true
      log "FOLLOWUP_RECORDED .factory/followups/$ISSUE_ID.md - part of this issue was deliberately left"
    fi

    # COMMIT. Without this the whole lap is theatre: the implement node edits files in
    # the worktree, nothing records them, and `git worktree remove --force` discards the
    # work. The first real headless lap did exactly that -- every node reported OK, the
    # guard correctly saw 2 files and 30 lines, and the branch ended up empty. Driving the
    # lap by hand had hidden it, because a human commits without being told to.
    if [ -z "$(git -C "$WT" status --porcelain)" ]; then
      git worktree remove "$WT" --force >/dev/null 2>&1 || true
      # Denials are the usual CAUSE of an empty diff, so they are reported alongside it
      # rather than left in a log for somebody to correlate an hour later.
      DENIED=""
      [ -s "$RUNDIR/DENIALS" ] && DENIED=" It was denied tools: $(head -c 500 "$RUNDIR/DENIALS")"
      escalate "the implement node produced no file changes at all -- nothing to validate.$DENIED"
    fi
    git -C "$WT" add -A
    git -C "$WT" commit -q -m "$(printf '%.68s' "$TITLE") (#$ISSUE_NUM)" \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "could not commit the implement node's work"; }
    log "COMMITTED $(git -C "$WT" rev-parse --short HEAD)"

    # Node 4: validate. NOT a model. Guard first -- a change that touched a protected
    # file has already invalidated everything downstream of it.
    log "NODE validate (no model)"
    python factory/guard.py --base "$BASE" --head "$BRANCH" \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "protected-path guard failed (FACTORY_RULES.md 6.1) - auto-reject, no fix attempt"; }

    if ! ( cd "$WT" && $FACTORY_VALIDATE_CMD > "$RUNDIR/gate.log" 2>&1 ); then
      log "GATE_RED - the independent validator gets it anyway; the fix node works from its findings"
      tail -20 "$RUNDIR/gate.log" | sed 's/^/    /'
    fi

    git worktree remove "$WT" --force >/dev/null 2>&1 || true

    # Node 5 runs from the ROOT checkout, not the worktree. The PR record is shared
    # factory state and has to survive the worktree being torn down -- written inside it,
    # it went to the bin along with the branch's only copy of the work.
    # `git show` and `git log` are on the list because the review node runs from the ROOT
    # checkout, where the branch's files are not on disk -- `git diff` alone lets it see
    # what changed and not what the changed file now says. It asked for `git show` on all
    # three dispatches of 2026-08-11, was refused each time, and on the third it stopped
    # to ask a human who was not there and wrote no PR record at all. The workflow caught
    # that (the `-s "$PRFILE"` check below), but a node starved of a read-only command it
    # needs fails somewhere downstream of the denial, and the escalation names the
    # symptom. `git fetch` is deliberately NOT here: it mutates refs.
    node review "$MODEL_CHEAP" "$ROOT/factory/prompts/review.md" \
        "Read,Glob,Grep,Bash(git diff:*),Bash(git show:*),Bash(git log:*),Bash(git status:*),Write" \
        || escalate "review node failed"
    [ -s "$PRFILE" ] || escalate "the review node wrote no PR record at $PRFILE"

    # ASSERT THE SHAPE, not just the presence. `-s` only proves the node wrote SOMETHING.
    #
    # The prompts are the one part of this runner you are told to rewrite, and a rewrite
    # can silently drop a field the machinery depends on. Observed exactly once and it
    # cost the whole second half of the loop: a rewritten `review.md` produced a perfectly
    # good human-readable PR record with no front matter, so `state.py` read nothing from
    # it, and `validate-pr` had no branch to check out. The implement lap looked like a
    # complete success and the PR could never be validated by anything.
    #
    # Fail HERE, naming the missing field, rather than three steps later as "no branch".
    for key in issue title state branch; do
      grep -qE "^${key}:[[:space:]]*[^[:space:]]" "$PRFILE" \
        || escalate "the PR record at $PRFILE has no '$key:' in its front matter. The review prompt must emit the full front-matter block (issue/title/state/branch/attempts) - without it the independent validator cannot find the branch and this PR can never be validated."
    done
    log "PR_RECORD_OK front matter complete"

    if [ "$GH" -eq 1 ]; then
      # THE PUSH AND THE PR. Done by the script, from the review node's file -- not by
      # the model. Same rule as the merge: a model's only output is a record, and code
      # decides what happens to it. A node holding `gh pr create` is a node that can open
      # a PR against any branch it likes, including one nothing validated.
      git push -q -u origin "$BRANCH" || escalate "could not push $BRANCH to origin"

      # The `|| true` is what makes the fallback on the next line reachable. Without it a
      # PR record with no `title:` killed the run HERE, one line above the check written
      # to handle exactly that -- the error path existed and the language got there first.
      PR_TITLE="$(grep -m1 '^title:' "$PRFILE" | cut -d: -f2- | sed 's/^ *//' || true)"
      [ -n "$PR_TITLE" ] || PR_TITLE="$TITLE"
      # Body is everything after the front matter, plus the link GitHub acts on.
      python -c "import io,sys;t=io.open(sys.argv[1],encoding='utf-8').read();print(t.split('---',2)[2].lstrip() if t.startswith('---') else t)"         "$PRFILE" > "$RUNDIR/pr.body.md"
      printf '\n---\nCloses #%s\n\nOpened by `factory/run-workflow.sh` (implement-issue, run `%s`). No human read this diff.\n' \
        "$ISSUE_NUM" "$RUN" >> "$RUNDIR/pr.body.md"

      # Through the helper, which reads the PR back and asserts GitHub stored the body
      # that was sent. A PR body is a human-facing write like any other, and the one
      # human-facing write this factory has already got wrong went out through a
      # hand-rolled `gh` call. FACTORY_RULES.md 10.1.
      PR_OUT="$(python factory/state.py create-pr "$PR_TITLE" main "$BRANCH" \
                  < "$RUNDIR/pr.body.md")" \
        || escalate "could not open the pull request, or its body did not survive the round trip"
      printf '%s\n' "$PR_OUT"
      PR_NUM="$(printf '%s' "$PR_OUT" | grep '^PR_NUMBER=' | cut -d= -f2 || true)"
      PR_URL="$(printf '%s' "$PR_OUT" | grep '^PR_URL=' | cut -d= -f2- || true)"
      log "PR_OPENED $PR_URL"

      python factory/state.py set "gh:pr:$PR_NUM" state=open \
        || escalate "could not label the new PR"
      echo "$PR_URL" > "$RUNDIR/pr.url"
    fi

    log "PR record written; state=open hands it to the independent validator"
    ;;

  validate-pr)
    BRANCH="$(read_fm branch "$TARGET")"
    [ -n "$BRANCH" ] || escalate "no branch on $TARGET"
    ISSUE_REF="$(read_fm issue "$TARGET")"
    WT=".worktrees/v$ISSUE_NUM"

    if [ "$GH" -eq 1 ]; then
      [ -n "$ISSUE_REF" ] || escalate "the PR does not say which issue it closes; the judge has nothing to judge against"
      materialise "$ISSUE_REF" || escalate "could not read $ISSUE_REF"
      git fetch --quiet origin "$BRANCH:refs/remotes/origin/$BRANCH" 2>/dev/null || true
      CHECKOUT="origin/$BRANCH"
      git rev-parse --verify --quiet "$CHECKOUT" >/dev/null || CHECKOUT="$BRANCH"
    else
      ISSUE_REF="$(read_fm issue "$TARGET")"
      ISSUE_FILE="$ISSUE_REF"
      CHECKOUT="$BRANCH"
    fi

    # --- rebase BEFORE validating, not after being refused ----------------------
    #
    # THE DEADLOCK THIS REMOVES. `merge.sh` refuses a branch that is behind the base, and
    # it is right to: squashing a stale branch silently drops whatever landed while it was
    # in flight. But the designed remedy - "rebase and re-validate" - was unreachable. The
    # gate had already set the PR to `passed`, the refusal then sent it to `needs-human`,
    # and `needs-human` is terminal for nodes. So a branch that went stale for the most
    # ordinary reason in the world (someone pushed to main while a lap was running) parked
    # forever and needed a human to hand-edit a file.
    #
    # On a repo with any commit velocity that is not an edge case, it is Tuesday.
    #
    # Rebasing HERE is safe in a way that rebasing after a verdict is not: nothing has been
    # judged yet. Everything downstream - the guard, the full gate, the judge - then runs
    # against the rebased tree, so the verdict describes the thing that will actually be
    # merged. A conflict is a genuine human problem and escalates.
    if git merge-base --is-ancestor "$BASE" "$CHECKOUT" 2>/dev/null; then
      log "REBASE_NOT_NEEDED $CHECKOUT already contains $BASE"
    else
      log "REBASE_REQUIRED $CHECKOUT is behind $BASE - rebasing before validation"
      if git rebase "$BASE" "$BRANCH" >/dev/null 2>&1; then
        git checkout -q - 2>/dev/null || git checkout -q main 2>/dev/null || true
        log "REBASED $BRANCH onto $BASE; everything below judges the rebased tree"
        [ "$GH" -eq 1 ] && { git push -q --force-with-lease origin "$BRANCH" || log "REBASE_PUSH_FAILED (validating locally)"; }
        CHECKOUT="$BRANCH"
      else
        git rebase --abort >/dev/null 2>&1 || true
        escalate "$BRANCH conflicts with $BASE and cannot be rebased automatically. A human has to resolve the conflict; the factory will not guess at a merge."
      fi
    fi

    prepare_worktree_path "$WT"
    git worktree add --detach "$WT" "$CHECKOUT" >/dev/null 2>&1 || escalate "could not check out $CHECKOUT"

    # Governance from the BASE branch, before the branch under review is read. On GitHub
    # that is origin/main and not the local main -- reading the local copy would judge the
    # branch against whatever this checkout happened to have fetched, which is a rulebook
    # nobody published.
    git show "$BASE:MISSION.md"       > "$RUNDIR/MISSION.base.md"
    git show "$BASE:FACTORY_RULES.md" > "$RUNDIR/FACTORY_RULES.base.md"
    git show "$BASE:CLAUDE.md"        > "$RUNDIR/CLAUDE.base.md"

    python factory/tripwire.py "$WT" \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "TRIPWIRE: a builder artifact is in the validator's tree; its verdict is not independent"; }

    # Guarded, like every other state write here. Unguarded, a refusal exits this script
    # on the spot with `set -e` and no escalation -- the same silent shape that made the
    # fix loop unreachable. This is also the write that CLAIMS the PR: everything below
    # assumes a validation owns it.
    python factory/state.py set "$TARGET" state=validating \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "could not move $TARGET to 'validating'; the validation cannot claim a PR it is not allowed to hold"; }

    # The guard runs from the ROOT checkout against the branch -- NOT from inside the
    # worktree. Running it in the worktree executes the BRANCH's copy of the enforcement
    # code, so a PR supplies the guard that judges it. factory/** is protected, so a PR
    # cannot deliberately weaken it -- but a branch cut before a guard fix silently runs
    # the old, broken guard, which is exactly how this was found. Same principle as
    # reading governance from the base branch (FACTORY_RULES.md 9), applied to the code
    # that does the enforcing rather than the rules it enforces.
    python factory/guard.py --base "$BASE" --head "$CHECKOUT" > "$RUNDIR/gate.log" 2>&1 \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           # `|| true`, because a command inside a `|| { ... }` block does NOT chain: under
           # set -e a failure here aborts the whole block, so `escalate` on the next line
           # never runs. Verified: `false || { false; echo B; }` never prints B and exits 1.
           # That would turn a protected-path guard failure -- a PR touching factory/** --
           # into an exit 1 with no escalation and no notification, on the one path whose
           # entire job is to stop a branch from rewriting its own enforcement code.
           python factory/state.py set "$TARGET" state=rejected || true
           escalate "protected-path guard failed on the branch under review"; }

    ( cd "$WT" && $FACTORY_VALIDATE_CMD ) >> "$RUNDIR/gate.log" 2>&1 || log "GATE_RED"

    git diff "$BASE...$CHECKOUT" > "$RUNDIR/diff.patch"
    git log --format='%h %s' "$BASE..$CHECKOUT" > "$RUNDIR/commits.txt"
    log "DIFF_RENDERED $(wc -l < "$RUNDIR/diff.patch") lines -> $RUNDIR/diff.patch"

    ( cd "$WT" && node judge "$MODEL_CHEAP" "$ROOT/factory/prompts/judge.md" \
        "Read,Bash(git diff:*),Write" ) || escalate "judge node failed"

    # The verdict must exist before the worktree goes. It is written to the absolute run
    # dir for the same reason the plan is: a path relative to the judge's cwd lands inside
    # the worktree and dies with it. gate.sh did correctly refuse to read a missing verdict
    # as an approval -- but the last backstop should not be the thing that catches this.
    [ -s "$RUNDIR/verdict.json" ] \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true
           escalate "the judge node produced no verdict at $RUNDIR/verdict.json"; }

    git worktree remove "$WT" --force >/dev/null 2>&1 || true

    bash factory/gate.sh "$TARGET" "$RUNDIR/gate.log" "$RUNDIR/verdict.json"
    ;;

  fix-pr)
    ATTEMPTS="$(read_fm attempts "$TARGET")"
    [ "${ATTEMPTS:-0}" -lt 2 ] || escalate "fix-attempt cap reached (FACTORY_RULES.md 8)"

    # THE FINDINGS, written by gate.sh when it recorded `request_changes`. ABSOLUTE,
    # because the fix node cd's into its worktree and a relative path resolves there.
    #
    # Asserted, not assumed. A fix node with no findings does not fail - it re-reads the
    # diff and invents an objection, which is how you get a confident commit that
    # addresses nothing and burns one of two attempts. Missing findings mean the gate
    # never recorded them, which is a machinery fault and belongs in front of a human.
    FINDINGS_KEY="$(printf '%s' "$TARGET" | tr '/.:\\' '----')"
    FINDINGS="$ROOT/.factory/findings/$FINDINGS_KEY.json"
    FINDINGS_LOG="$ROOT/.factory/findings/$FINDINGS_KEY.gate.log"
    [ -s "$FINDINGS" ] || escalate "no validator findings at $FINDINGS - gate.sh records them when it returns request_changes, so this PR reached the fix loop without a recorded objection. A fix node with nothing to read would invent one."
    log "FINDINGS $FINDINGS ($(wc -c < "$FINDINGS") bytes)"

    BRANCH="$(read_fm branch "$TARGET")"
    ISSUE_REF="$(read_fm issue "$TARGET")"
    [ "$GH" -eq 1 ] && { materialise "$ISSUE_REF" || escalate "could not read $ISSUE_REF"; } \
                    || ISSUE_FILE="$ISSUE_REF"
    WT=".worktrees/f$ISSUE_NUM"
    prepare_worktree_path "$WT"
    git worktree add "$WT" "$BRANCH" >/dev/null 2>&1 || escalate "could not check out $BRANCH"

    ( cd "$WT" && node fix "$MODEL_CHEAP" "$ROOT/factory/prompts/fix.md" \
        "Read,Glob,Grep,Edit,Write,Bash($FACTORY_VALIDATE_QUICK)" ) \
      || { git worktree remove "$WT" --force >/dev/null 2>&1 || true; escalate "fix node failed"; }

    if [ -z "$(git -C "$WT" status --porcelain)" ]; then
      git worktree remove "$WT" --force >/dev/null 2>&1 || true
      escalate "the fix node changed nothing; the finding is not addressed by an empty diff"
    fi
    git -C "$WT" add -A
    git -C "$WT" commit -q -m "fix: address validator findings (attempt $((ATTEMPTS + 1))) (#$ISSUE_NUM)"
    if [ "$GH" -eq 1 ]; then
      git -C "$WT" push -q origin "HEAD:$BRANCH" || escalate "could not push the fix"
    fi

    git worktree remove "$WT" --force >/dev/null 2>&1 || true
    python factory/state.py bump-attempt "$TARGET" \
      || escalate "the fix is committed but the attempt counter did not move; another fix would not be counted and the cap would never be reached"

    # ONE transition, to `open`, and it used to be two: `validating` then `open`. The
    # second was illegal (validating cannot reach open), returned 1, and `set -e` killed
    # this workflow on that line -- before the escalate below could exist, before
    # needs-human, before any notification. The PR stayed `validating`, `next` did not
    # look at that state, and the dispatcher answered `idle` from then on. The fix was
    # committed and the loop simply stopped, silently, on the one workflow that had never
    # been run.
    #
    # `open` is the right target on its own: a fixed PR is a PR waiting to be validated.
    # The dispatcher picks it up and validate-pr sets `validating` itself after the
    # tripwire, which is the only place allowed to.
    python factory/state.py set "$TARGET" state=open \
      || escalate "the fix is committed on $BRANCH but the PR could not be returned to 'open' for re-validation; it would otherwise sit in a state the dispatcher does not look at"
    log "fixed; back to the independent validator (attempt $((ATTEMPTS + 1))/2)"
    ;;

  triage)
    materialise "$TARGET" || escalate "could not read the issue"

    node sort "$MODEL_CHEAP" "$ROOT/factory/prompts/triage.md" \
      "Read,Glob,Grep,Write" \
      || escalate "triage node failed"

    # THE DECISION IS APPLIED BY CODE, NOT BY THE MODEL. The triage node writes a
    # disposition file and nothing else; this applies it through state.py, which refuses
    # an illegal transition. Before the move the node edited the issue's front matter
    # directly -- so it could write ANY state, including one the transition table forbids,
    # and the table was never consulted. That hole existed on the file backend too; the
    # GitHub move is only what made it visible, because there is no front matter to edit.
    DEC="$RUNDIR/triage.json"
    [ -s "$DEC" ] || escalate "the triage node wrote no decision at $DEC"
    python - "$DEC" <<'PY' > "$RUNDIR/triage.env" || escalate "triage decision is not readable JSON"
import json, sys, shlex
d = json.load(open(sys.argv[1], encoding="utf-8"))
st = d.get("state", "")
if st not in {"accepted", "deferred", "rejected", "needs-human"}:
    raise SystemExit(f"triage returned an unknown disposition: {st!r}")
print(f"DEC_STATE={shlex.quote(st)}")
print(f"DEC_PRIORITY={shlex.quote(d.get('priority') or '')}")
print(f"DEC_AREA={shlex.quote(d.get('area') or '')}")
PY
    . "$RUNDIR/triage.env"

    # ONE process, one string, one verified write. The pipeline this replaces echoed a
    # header, piped a `python -c` through the platform codepage, and handed the result to
    # a `gh` flag that does not read files -- so the correct rejection on issue #3 reached
    # GitHub as the two characters `@-`, and nothing noticed, because the only thing
    # checked afterwards was the exit code. FACTORY_RULES.md 10.1.
    python factory/state.py triage-note "$TARGET" "$DEC"       || escalate "the decision was made but could not be published; a verdict the filer cannot read is not a verdict"

    if [ -n "$DEC_PRIORITY" ]; then
      python factory/state.py set "$TARGET" "priority=$DEC_PRIORITY" || true
    fi
    python factory/state.py set "$TARGET" "state=$DEC_STATE" \
      || escalate "triage proposed an illegal transition to '$DEC_STATE'"
    log "TRIAGED $TARGET -> $DEC_STATE"

    # A TRIAGE THAT DECIDES `needs-human` MUST REACH A HUMAN.
    #
    # This wrote the ledger line inline and stopped there, so `factory_notify` was never
    # called: the notifier is reached only from `escalate()`, and `escalate()` fires on
    # runner FAULTS - a node that crashed, unreadable JSON, an illegal transition. A
    # successful triage that correctly decides "a human must look at this" is not a fault,
    # so it took the one path that skips the alarm.
    #
    # Measured: seven probe issues, two correct `needs-human` decisions, **zero
    # notifications** - the directory was never even created. The stop list worked
    # perfectly and nobody was told. That is precisely what the comment on escalate()
    # warns about: "if it cannot interrupt a human, unattended quietly means unmonitored".
    #
    # Not routed through `escalate()` itself, because that also flips the issue to
    # `needs-human` (already done, through the transition table) and exits 3, which would
    # turn a correct triage into a failed workflow. The notification is the only missing
    # half, so that is the half added.
    if [ "$DEC_STATE" = "needs-human" ]; then
      TRIAGE_WHY="$(python -c "import json,sys;print((json.load(open(sys.argv[1],encoding='utf-8')).get('note') or 'escalated at triage').strip().replace(chr(10),' ')[:300])" "$DEC" 2>/dev/null || echo "escalated at triage")"
      echo "- $(date -u +%FT%TZ)  $TARGET  (triage)  $TRIAGE_WHY" >> .factory/needs-human.md
      log "$(factory_notify "$TARGET" "(triage) $TRIAGE_WHY")"
    fi
    ;;

  *)
    echo "unknown workflow '$WORKFLOW'" >&2
    exit 1 ;;
esac

log "WORKFLOW_DONE $WORKFLOW"
