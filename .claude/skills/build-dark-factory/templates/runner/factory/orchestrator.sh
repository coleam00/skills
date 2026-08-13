#!/usr/bin/env bash
# The dispatcher. Component 2, built last on purpose.
#
# It answers exactly one question -- "what, if anything, should run right now?" -- from a
# fixed priority order and the front matter of files on disk. No model is consulted.
#
# That is not a stylistic preference. A model asked "what work is pending?" will invent
# dispatches for issues that were never filed and PRs that do not exist. It is a
# plausible-sounding answer with nothing behind it, and the factory then acts on it. The
# dumbest component in the system is the one where a wrong answer is worse than no answer.
#
#   bash factory/orchestrator.sh              dispatch at most one thing, then exit
#   bash factory/orchestrator.sh --dry-run    say what it would do, do nothing
#
# Work is read through factory/state.py, which is on the GitHub backend wherever there is
# an `origin` remote. Targets are therefore `gh:issue:<n>` / `gh:pr:<n>` rather than
# paths, and this script never learns the difference.
#
# From cron, once the dial is above 0. Slower than feels right:
#   */30 * * * * cd /path/to/repo && bash factory/orchestrator.sh >> factory.log 2>&1

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

# Fallback: an escalation must never be the thing that fails.
command -v factory_notify >/dev/null 2>&1 || factory_notify() {
  echo "NOT NOTIFIED - factory/config.sh defines no factory_notify (old copy?)"
}

STOP_FILE="$FACTORY_STOP_FILE"
MAX_PARALLEL="$FACTORY_MAX_PARALLEL"
AUTONOMY="$FACTORY_AUTONOMY"
RUNNER="${FACTORY_RUNNER:-factory/run-workflow.sh}"
LOCKDIR=".factory/locks-runtime"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# THE SAME BACKSTOP run-workflow.sh CARRIES, one level up, and it matters MORE here.
#
# This script is the scheduled entry point. Nothing supervises it: cron or Task Scheduler
# starts it, it exits, and the exit code goes nowhere anyone looks. So an unguarded command
# failing under `set -e` does not lose one workflow, it loses THE WHOLE TICK -- the reaper,
# the stalled sweep, and every dispatch after the failing line -- and the next tick starts
# from scratch and usually fails at the same place. A factory that has been dead for a week
# looks exactly like a factory with nothing to do.
#
# Found by `scripts/_audit_runner.py` on its first run, in the gap left by fixing the
# runner and not its dispatcher.
#
# It cannot change control flow: `set -e` already ends the tick at exactly these points.
# It makes the ending say why, and tells a human, because a dispatcher that has stopped
# dispatching is the one failure nothing else in this system can report.
on_dispatcher_fault() {   # on_dispatcher_fault <rc> <line> <command>
  trap - ERR
  log "DISPATCHER_FAULT line $2 exited $1: $3"
  log "  The tick ended here. Anything after this line did not run - locks were not"
  log "  reaped, stalls were not swept, and nothing further was dispatched."
  mkdir -p "$(dirname "$FACTORY_STOP_FILE")" 2>/dev/null || true
  echo "- $(date -u +%FT%TZ)  (orchestrator)  dispatcher fault at line $2: $3" \
    >> .factory/needs-human.md 2>/dev/null || true
  log "$(factory_notify "orchestrator" "the dispatcher itself failed at line $2 running: $3")" || true
  exit 1
}
trap 'on_dispatcher_fault "$?" "$LINENO" "$BASH_COMMAND"' ERR

# =============================================================================
# 1. THE STOP BUTTON. Checked first, every time, before anything else is read.
# =============================================================================
if [ -f "$STOP_FILE" ]; then
  log "STOPPED: $STOP_FILE present. Remove it to resume."
  [ -s "$STOP_FILE" ] && log "reason: $(head -1 "$STOP_FILE")"
  exit 0
fi

# The remote half, added at the GitHub move. Any OPEN issue labelled `factory:stop` halts
# every dispatch. That is the one you can reach from a phone, which is the entire point
# of having it at all.
#
# The polarity is the thing to get right, and "remove a label to stop" is backwards.
# Removing a label cannot be told apart from an API call that failed to list it, so a
# stop button built that way works only while the network does. This one is a label you
# ADD, and it FAILS CLOSED: if the stop state cannot be read, nothing dispatches. An
# unreadable stop button is a stop button you do not have.
STOP_OUT="$(python factory/state.py stop-requested 2>&1)" || {
  log "STOPPED: $STOP_OUT"
  exit 0
}
log "$STOP_OUT"

# =============================================================================
# 1b. RECONCILE ON ENTRY. A sweep, not a dispatch, and it runs on EVERY tick.
# =============================================================================
# A PR in `validating` is owned by a running validation, which holds a lock. With no lock
# the run that owned it is gone -- killed, rebooted, crashed between the tripwire and the
# verdict -- and nothing in the priority order below will ever look at it again.
#
# WHY THIS IS A SWEEP AND NOT A CASE IN THE DISPATCH BELOW. It was one, at the bottom of
# the priority order, and that was wrong in a way only running it showed: `next` answers
# with ONE thing, so a single untriaged issue sitting at a dial below 4 outranked the
# stall forever. The tick then logged `HOLD triage ...` and exited 0 -- nothing
# dispatched, nothing escalated, and a dead PR invisible behind a queue that could not
# move either. Two separate wedges, each hiding the other.
#
# A stalled PR is not work to schedule against other work. It is a fault to report, so it
# is reported unconditionally, before the dial and before the capacity check, and it never
# consumes the tick's one dispatch.

# `reap_stalled <target> <state> <workflow-that-owns-it>`. The message names the ACTUAL
# condition: "left in validating" and "left in in-progress" have different causes and
# different remedies, and one message covering both sends a human to the wrong file.
reap_stalled() {
  local target="$1" st="$2" wf="$3"
  local key; key="$(echo "${wf}-${target}" | tr '/.:' '---')"
  if [ -e "$LOCKDIR/$key.lock" ]; then
    log "IN_FLIGHT $target is '$st' and a $wf run still holds its lock"
    return 1
  fi
  local why
  if [ "$st" = "validating" ]; then
    why="left in 'validating' with no run holding it; a validation died between the tripwire and the verdict"
  else
    why="left in 'in-progress' with no PR record and no run holding it; an implement lap died before it opened one"
  fi
  log "STALLED $target $why"
  python factory/state.py set "$target" state=needs-human || true
  echo "- $(date -u +%FT%TZ)  $target  (orchestrator)  $why" >> .factory/needs-human.md
  log "$(factory_notify "$target" "$why")"
  return 0
}

if [ "$DRY_RUN" -eq 0 ]; then
  while IFS=$'\t' read -r STALL_TARGET _rest; do
    [ -z "${STALL_TARGET:-}" ] && continue
    reap_stalled "$STALL_TARGET" validating validate-pr || true
  done <<EOF
$(python factory/state.py list prs --state validating 2>/dev/null || true)
EOF

  # The ISSUE half. `implement-issue` sets `in-progress` before any node runs, so a lap
  # killed in between strands the issue in a state nothing in the priority order reads.
  # Only issues with NO PR record referencing them are stranded; state.py decides that,
  # because whether a PR references an issue is a question about the queue, not the locks.
  while IFS=$'\t' read -r STALL_TARGET _rest; do
    [ -z "${STALL_TARGET:-}" ] && continue
    case "$STALL_TARGET" in
      *issues*|gh:issue:*) reap_stalled "$STALL_TARGET" in-progress implement-issue || true ;;
    esac
  done <<EOF
$(python factory/state.py next 2>/dev/null | grep '^stalled' | cut -f2 || true)
EOF
fi

mkdir -p "$LOCKDIR"
STALE_MIN="${FACTORY_LOCK_STALE_MINUTES:-180}"
while read -r deadlock; do
  [ -n "${deadlock:-}" ] || continue
  log "LOCK_REAPED $(basename "$deadlock") - older than ${STALE_MIN}m, so its workflow is gone. Held since: $(head -1 "$deadlock" 2>/dev/null)"
  rm -f "$deadlock"
done <<EOF
$(find "$LOCKDIR" -name '*.lock' -mmin "+$STALE_MIN" 2>/dev/null || true)
EOF

# --- the faster reap: the owning PROCESS is already gone ----------------------
#
# Age alone is too slow for the common case. The release is a trap, and a trap does not
# run when the process is killed rather than exited - close the terminal, reboot, or let
# a parent shell exit and take its detached child with it, which is exactly how a
# hand-driven queue loop leaves locks behind. The target is then blocked for the full
# STALE_MIN (three hours by default) for a workflow that died seconds ago.
#
# The PID was already being written into the lock and nothing read it. Reading it needs a
# guard against PID REUSE, so BOTH must hold: the process is not alive, AND the lock has
# had time to be real (GRACE_MIN, default 5). A live long lap is never touched, because
# its PID is alive - that is the check that matters, and age is only the tiebreaker.
GRACE_MIN="${FACTORY_LOCK_GRACE_MINUTES:-5}"
while read -r maybe; do
  [ -n "${maybe:-}" ] || continue
  lpid="$(head -1 "$maybe" 2>/dev/null | cut -d' ' -f1)"
  case "$lpid" in ''|*[!0-9]*) continue ;; esac      # no readable pid: leave it to age
  if kill -0 "$lpid" 2>/dev/null; then
    continue                                          # owner alive - a real run in flight
  fi
  log "LOCK_REAPED $(basename "$maybe") - its process ($lpid) is gone and the lock is over ${GRACE_MIN}m old"
  rm -f "$maybe"
done <<EOF
$(find "$LOCKDIR" -name '*.lock' -mmin "+$GRACE_MIN" 2>/dev/null || true)
EOF


# =============================================================================
# 2. THE AUTONOMY DIAL. The factory does only what the dial permits.
# =============================================================================
# 0  workflows exist, run them by hand           <- where this repo starts
# 1  accepted issue -> branch + PR record opens
# 2  + the validator runs and writes a verdict
# 3  + the validator AUTO-MERGES when every structural gate is green
# 4  + it triages its own issues, and a scheduled soak files its own bugs
# 5  + it writes its own issues from the mission
if [ "$AUTONOMY" -lt 1 ]; then
  log "AUTONOMY=0: nothing dispatches. Set FACTORY_AUTONOMY=1 when a lap has been proven by hand."
  log "would run: $(python factory/state.py next | tr '\t' ' ')"
  exit 0
fi

# =============================================================================
# 3. CONCURRENCY. Starts at one. A per-target lock is mandatory above that.
# =============================================================================
mkdir -p "$LOCKDIR"

# --- reap dead locks BEFORE counting capacity --------------------------------
#
# THE WEDGE THIS REMOVES, and it is the most likely one on a real machine. The lock is
# released by a trap, which covers a workflow that exits non-zero. It does NOT cover the
# process being killed: a reboot, the machine sleeping, a power cut, someone closing the
# terminal, the OOM killer. The lock file then survives its owner, is counted toward
# capacity forever, and every subsequent tick logs `at capacity (1/1), nothing dispatched`
# and exits 0 -- indistinguishable from a factory with nothing to do, which is the one
# failure mode this whole system exists to avoid.
#
# The PID was already being written into the lock and NOTHING read it. Age is the portable
# test and the safe one: PIDs are reused, and a liveness check that gets it wrong kills a
# running lap. A lock older than the cap cannot belong to a live workflow -- measured laps
# run 6 to 20 minutes and the cost cap bounds them well below three hours.
IN_FLIGHT=$(find "$LOCKDIR" -name '*.lock' 2>/dev/null | wc -l | tr -d ' ')
if [ "$IN_FLIGHT" -ge "$MAX_PARALLEL" ]; then
  log "at capacity ($IN_FLIGHT/$MAX_PARALLEL), nothing dispatched"
  [ "$IN_FLIGHT" -gt 0 ] && log "  held by: $(find "$LOCKDIR" -name '*.lock' -exec basename {} \; 2>/dev/null | tr '\n' ' ')"
  log "  a lock with no running workflow is reaped after ${STALE_MIN}m (FACTORY_LOCK_STALE_MINUTES)"
  exit 0
fi

dispatch() {            # dispatch <workflow> <target-file>
  local wf="$1" target="$2"
  # Colons too, since the move: a target is `gh:pr:4`, and a colon is a legal character
  # in a path on Linux and an illegal one on Windows. The lock file and the log both take
  # their name from this, so on Windows the dispatch failed at the redirect -- before the
  # workflow ran, with the lock already taken.
  local key; key="$(echo "${wf}-${target}" | tr '/.:' '---')"
  local lock="$LOCKDIR/$key.lock"

  if [ "$DRY_RUN" -eq 1 ]; then
    [ -e "$lock" ] && { log "DRY-RUN would SKIP $wf $target - already in flight"; return 1; }
    log "DRY-RUN would dispatch: $wf $target"
    return 0
  fi

  # ACQUIRE THE LOCK ATOMICALLY. `[ -e "$lock" ]` followed by `echo > "$lock"` is a
  # time-of-check-to-time-of-use race, and it is not theoretical: two orchestrators started
  # in the same second BOTH passed the test and BOTH dispatched validate-pr on the same PR,
  # so two runs edited one worktree and the second judged a tree the first was still
  # writing. Reachable whenever a tick outlives the cron interval, or a human runs the
  # dispatcher while cron fires.
  #
  # `set -C` makes the redirect O_EXCL: exactly one of the racers creates the file and the
  # other fails. `set +C` immediately after, because noclobber would otherwise break every
  # later `>` in this script.
  set -C
  if ! echo "$$ $(date -u +%FT%TZ)" > "$lock" 2>/dev/null; then
    set +C
    log "SKIP $wf $target - already in flight"
    return 1
  fi
  set +C

  log "DISPATCH $wf $target"
  # The lock is released by a trap, not by the next statement. `set -e` is inherited by
  # this background subshell, so a workflow that exits non-zero -- an escalation, a
  # blocked gate, anything at all -- skipped the release entirely. The dispatcher was
  # then at capacity forever: every later run logged "at capacity (1/1), nothing
  # dispatched" and exited 0. A factory wedged that way looks exactly like a factory with
  # nothing to do, which is the one failure mode this whole system exists to avoid.
  # FACTORY_LOCK_HELD tells run-workflow.sh that its lock is already held by us, so it
  # does not try to take a second one. A run started BY HAND has no such variable and
  # acquires its own - see the block at the top of run-workflow.sh.
  #
  # THE RUNNER'S EXIT STATUS USED TO BE DISCARDED ENTIRELY. It is dispatched into a
  # background subshell and nothing ever read `$?`, so a runner that died on an unguarded
  # command -- the failure class documented at the top of run-workflow.sh -- left no trace
  # anywhere the dispatcher could see. run-workflow.sh now traps ERR and escalates, which
  # is the real fix; this is the backstop for the case where it dies before that trap is
  # installed, or is replaced by a hand-edited copy that never had it. `|| rc=$?` rather
  # than a bare call because `set -e` is inherited here and would otherwise kill the
  # subshell before the line that reports the death.
  #   rc=3 is an ordinary escalation and already reached a human.
  #   anything else non-zero is a FAULT in the runner itself.
  ( trap 'rm -f "$lock"' EXIT INT TERM
    rc=0
    FACTORY_LOCK_HELD="$lock" bash "$RUNNER" "$wf" "$target" || rc=$?
    case "$rc" in
      0|3) : ;;
      *) echo "[$(date -u +%FT%TZ)] RUNNER_FAULT $wf $target exited $rc with no escalation" \
           " - the runner stopped without parking the work; $target keeps its current" \
           " state and WILL be dispatched again. See the log above for the last line it reached." ;;
    esac ) \
    >> "factory-$key.log" 2>&1 &
}

# =============================================================================
# 4. PRIORITY ORDER. Load-bearing: finish in-flight work before starting new work.
# =============================================================================
# Reversed, the factory triages forever while its own branches rot, and throughput looks
# busy while going to zero. The order lives in factory/state.py so that the dispatcher
# and every workflow read the same answer from the same place.
#
# THE LOOP EXISTS SO `FACTORY_MAX_PARALLEL` MEANS SOMETHING. `next` names ONE thing, and
# a target already in flight used to consume the whole tick: ask, get the head of the
# queue, find its lock taken, stop. Measured with MAX_PARALLEL=3 and three open PRs, the
# second tick dispatched nothing at all. So the knob was inert - and a knob that silently
# does nothing is worse than one that is not offered.
#
# Targets that could not be locked are EXCLUDED and the question is asked again, so the
# priority order still lives entirely in state.py. The dispatcher contributes only the one
# fact it owns: which targets it already holds.
EXCLUDE=""
SLOTS=$((MAX_PARALLEL - IN_FLIGHT))
[ "$SLOTS" -lt 1 ] && SLOTS=1

while [ "$SLOTS" -gt 0 ]; do
  SLOTS=$((SLOTS - 1))
  if [ -n "$EXCLUDE" ]; then
    NEXT="$(python factory/state.py next --exclude "$EXCLUDE")"
  else
    NEXT="$(python factory/state.py next)"
  fi
  ACTION="$(echo "$NEXT" | cut -f1)"
  TARGET="$(echo "$NEXT" | cut -f2)"

  # Only a dispatch can usefully repeat. Everything else - a merge, an escalation, idle,
  # a stall - is a decision about the whole queue and is made once.
  case "$ACTION" in
    fix-pr|validate-pr|implement-issue|triage) : ;;
    *) SLOTS=0 ;;
  esac

  case "$ACTION" in

  fix-pr)
    dispatch fix-pr "$TARGET" || true
    EXCLUDE="${EXCLUDE:+$EXCLUDE,}$TARGET" ;;

  escalate)
    # Hit the fix cap. Not a dispatch: a stop.
    log "ESCALATE $TARGET hit the fix-attempt cap (FACTORY_RULES.md 8)"
    [ "$DRY_RUN" -eq 0 ] && {
      # `|| true`, and it is load-bearing. A command inside a `[ cond ] && { ... }` block
      # does not chain under set -e: verified that `[ 1 -eq 1 ] && { false; echo B; }`
      # never prints B and exits 1. So ANY failure of this one write silently skipped the
      # ledger line below, the parent-issue labelling and the NOTIFICATION, and killed the
      # tick with the rest of the queue undispatched. The escalation with the most reason
      # to be seen was the one most exposed to a silent skip.
      #
      # It is not hypothetical: `merged` has an EMPTY transition set, so a PR that reached
      # `merged` and then somehow arrives here fails this write outright. (A repeat pass
      # over an already-escalated PR does NOT -- `cmd_set` returns 0 early when the new
      # state equals the old one, so `needs-human` -> `needs-human` is a no-op, not an
      # error. Checked, because the opposite is the obvious assumption and it is wrong.)
      python factory/state.py set "$TARGET" state=needs-human || true
      { echo "- $(date -u +%FT%TZ)  $TARGET  fix-attempt cap reached (FACTORY_RULES.md 8)"; } \
        >> .factory/needs-human.md
      # AND THE ISSUE BEHIND IT, for the reason gate.sh's fail() already does it: a PR
      # parked at needs-human whose issue still reads `in-progress` is an escalation
      # nothing can see. Observed: the cap fired, the PR was labelled, the issue was not,
      # and the very next `state.py next` moved on to unrelated work while the escalated
      # issue sat in a state that means "being worked on" with nothing working on it.
      CAP_ISSUE="$(python factory/state.py get "$TARGET" 2>/dev/null | grep '^issue=' | head -1 | cut -d= -f2- || true)"
      if [ -n "${CAP_ISSUE:-}" ]; then
        python factory/state.py set "$CAP_ISSUE" state=needs-human >/dev/null 2>&1 || true
        echo "- $(date -u +%FT%TZ)  $CAP_ISSUE  its PR $TARGET hit the fix-attempt cap" >> .factory/needs-human.md
      fi
      # The third route into needs-human, and the quietest: nothing failed, a PR simply
      # stopped being worked on. Without this it is the escalation you notice last.
      log "$(factory_notify "$TARGET" "fix-attempt cap reached; no further attempts")"
    } ;;

  validate-pr)
    if [ "$AUTONOMY" -lt 2 ]; then
      log "HOLD validate-pr $TARGET - requires AUTONOMY>=2, currently $AUTONOMY"
      break
    fi
    dispatch validate-pr "$TARGET" || true
    EXCLUDE="${EXCLUDE:+$EXCLUDE,}$TARGET" ;;

  merge)
    if [ "$AUTONOMY" -lt 3 ]; then
      log "HOLD merge $TARGET - requires AUTONOMY>=3, currently $AUTONOMY."
      log "The PR passed every gate and is waiting for a human. This is level 2 working."
      break
    fi
    log "MERGE $TARGET"
    # THE THIRD ROUTE THAT NEVER LEARNED TO ESCALATE. `merge.sh` reached from gate.sh is
    # called as `|| fail`, and fail() parks the PR, writes the ledger and notifies. Reached
    # from HERE -- the route `next` uses for an already-`passed` PR -- a merge failure was
    # simply an unguarded non-zero at the end of a case branch: set -e killed the whole
    # orchestrator tick, abandoning the rest of the dispatch loop, and merge.sh contains no
    # factory_notify of its own. So the two ways of arriving at the same merge behaved
    # completely differently, and the quieter one was the one that runs unattended.
    #
    # A failed merge is not a fault to retry: `passed` -> `open` requeues for revalidation
    # (see state.py), which is what the PR needs after a rebase, and anything else needs a
    # human. Escalating is the honest move because merge.sh has already printed the reason.
    if [ "$DRY_RUN" -eq 0 ]; then
      if bash factory/merge.sh "$TARGET"; then
        bash factory/deploy.sh || log "DEPLOY_FAILED after merging $TARGET - the merge stands; see the log above"
      else
        log "MERGE_FAILED $TARGET - parking it; merge.sh printed the reason above"
        python factory/state.py set "$TARGET" state=needs-human || true
        echo "- $(date -u +%FT%TZ)  $TARGET  (orchestrator)  merge refused; see factory/merge.sh output" \
          >> .factory/needs-human.md
        log "$(factory_notify "$TARGET" "merge refused for a PR that passed every gate")"
      fi
    fi ;;

  implement-issue)
    dispatch implement-issue "$TARGET" || true
    EXCLUDE="${EXCLUDE:+$EXCLUDE,}$TARGET" ;;

  triage)
    if [ "$AUTONOMY" -lt 4 ]; then
      log "HOLD triage $TARGET - requires AUTONOMY>=4, currently $AUTONOMY"
      break
    fi
    dispatch triage "$TARGET" || true
    EXCLUDE="${EXCLUDE:+$EXCLUDE,}$TARGET" ;;

  stalled)
    # A PR sitting in `validating`. While a validation is genuinely running that is
    # correct and this branch must stay quiet -- the run holds a lock, and with
    # MAX_PARALLEL=1 the capacity check above has usually already exited.
    #
    # With no lock, the run that owned it is gone: killed, rebooted, crashed between the
    # tripwire and the verdict. Nothing else in the priority order looks at `validating`,
    # so before this existed such a PR was reported as `idle` and never mentioned again.
    # The lock is the only thing that separates the two, and it lives here, which is why
    # state.py reports this rather than acting on it.
    STALL_KEY="$(echo "validate-pr-${TARGET}" | tr '/.:' '---')"
    if [ -e "$LOCKDIR/$STALL_KEY.lock" ]; then
      log "IN_FLIGHT $TARGET is validating and a run still holds its lock - nothing to do"
      break
    fi
    log "STALLED $TARGET is 'validating' but no run holds its lock; the validation that claimed it never finished"
    [ "$DRY_RUN" -eq 0 ] && {
      python factory/state.py set "$TARGET" state=needs-human || true
      echo "- $(date -u +%FT%TZ)  $TARGET  (orchestrator)  left in 'validating' with no run holding it; a validation died mid-flight" \
        >> .factory/needs-human.md
      log "$(factory_notify "$TARGET" "validation died mid-flight; PR left in 'validating'")"
    } ;;

  idle)
    # Nothing to build. Still make sure what merged is playable: a deploy that only runs
    # after a merge never notices that the last one silently stopped working.
    log "nothing to do"
    [ "$DRY_RUN" -eq 0 ] && [ "$AUTONOMY" -ge 3 ] && bash factory/deploy.sh || true ;;

  *)
    log "UNKNOWN action '$ACTION' from state.py - refusing to guess"
    exit 1 ;;
  esac
done
