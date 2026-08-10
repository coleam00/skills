#!/usr/bin/env bash
# The dispatcher. Deliberately the dumbest thing in the system.
#
# It answers exactly one question - "what, if anything, should run right now?" -
# using a fixed priority order and GitHub labels as the only shared state.
# No model is consulted. A model asked what to dispatch will invent runs for work
# that does not exist, and the factory will then act on that.
#
# Run it from cron. Start at every 30 minutes. Slower than feels right.
#   */30 * * * * /path/to/orchestrator.sh >> /var/log/factory.log 2>&1

set -euo pipefail

REPO="${FACTORY_REPO:?set FACTORY_REPO to owner/name}"
WORKDIR="${FACTORY_WORKDIR:?set FACTORY_WORKDIR to the repo checkout}"
MAX_PARALLEL="${FACTORY_MAX_PARALLEL:-1}"
MAX_FIX_ATTEMPTS="${FACTORY_MAX_FIX_ATTEMPTS:-2}"
KILL_FILE="${FACTORY_KILL_FILE:-$WORKDIR/.factory-stop}"

cd "$WORKDIR"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# --- the stop button ---------------------------------------------------------
# Checked first, every time. Must be trivially usable by a human in a hurry.
if [ -f "$KILL_FILE" ]; then
  log "STOPPED: $KILL_FILE present. Remove it to resume."
  exit 0
fi

# --- concurrency -------------------------------------------------------------
# Count what is already running. Above MAX_PARALLEL=1 a per-target lock is
# mandatory: never dispatch a workflow whose (workflow, target) pair is already
# in flight, or two runs will race on the same PR.
running() { pgrep -fc "$DISPATCH_MARKER" 2>/dev/null || echo 0; }
DISPATCH_MARKER="factory-dispatch"

IN_FLIGHT=$(running)
if [ "$IN_FLIGHT" -ge "$MAX_PARALLEL" ]; then
  log "at capacity ($IN_FLIGHT/$MAX_PARALLEL), nothing dispatched"
  exit 0
fi

target_locked() {   # target_locked <workflow> <target>
  pgrep -f "$DISPATCH_MARKER .*$1 .*#$2\b" >/dev/null 2>&1
}

# --- how a workflow is actually launched -------------------------------------
# Replace the body with the call for the chosen orchestrator. It must be
# fire-and-forget, and the marker must appear in the process arguments so the
# locks above can see it.
dispatch() {        # dispatch <workflow-name> <target-number>
  local wf="$1" target="$2"
  if target_locked "$wf" "$target"; then
    log "SKIP $wf #$target - already in flight"
    return 0
  fi
  log "DISPATCH $wf #$target"
  nohup <YOUR_RUNNER> "$wf" "$target" \
    --marker "$DISPATCH_MARKER $wf #$target" \
    >> "factory-$wf-$target.log" 2>&1 &
}

first_issue() {     # first_issue <label-expr...>
  gh issue list -R "$REPO" "$@" --state open --limit 1 --json number \
    -q '.[0].number // empty'
}
first_pr() {
  gh pr list -R "$REPO" "$@" --state open --limit 1 --json number \
    -q '.[0].number // empty'
}

# =============================================================================
# PRIORITY ORDER. This ordering is load-bearing: finish work already in flight
# before starting new work. Reversed, the factory triages forever while its own
# PRs rot, and throughput looks busy while going to zero.
# =============================================================================

# 1. Fix a PR that needs fixing, under the attempt cap.
PR=$(first_pr --label "factory:needs-fix")
if [ -n "$PR" ]; then
  ATTEMPTS=$(gh pr view "$PR" -R "$REPO" --json labels \
    -q '[.labels[].name | select(startswith("factory:fix-attempt-"))] | length')
  if [ "$ATTEMPTS" -lt "$MAX_FIX_ATTEMPTS" ]; then
    dispatch fix-pr "$PR"; exit 0
  fi
  log "PR #$PR hit the fix cap ($ATTEMPTS); escalating"
  gh pr edit "$PR" -R "$REPO" \
    --remove-label "factory:needs-fix" --add-label "factory:needs-human"
  exit 0
fi

# 2. Validate a PR waiting for review, oldest first.
PR=$(gh pr list -R "$REPO" --label "factory:needs-review" --state open \
      --limit 1 --json number,createdAt \
      -q 'sort_by(.createdAt) | .[0].number // empty')
if [ -n "$PR" ]; then dispatch validate-pr "$PR"; exit 0; fi

# 3. Implement the highest-priority accepted issue not already in progress.
for P in critical high medium low; do
  ISSUE=$(gh issue list -R "$REPO" --state open --limit 1 \
            --label "factory:accepted" --label "priority:$P" --json number,labels \
            -q '[.[] | select([.labels[].name] | index("factory:in-progress") | not)]
                | .[0].number // empty')
  if [ -n "$ISSUE" ]; then dispatch implement-issue "$ISSUE"; exit 0; fi
done

# 4. Triage, last, because PRs rot and untriaged issues do not.
ISSUE=$(gh issue list -R "$REPO" --state open --limit 1 --json number,labels \
  -q '[.[] | select([.labels[].name] | any(startswith("factory:")) | not)]
      | .[0].number // empty')
if [ -n "$ISSUE" ]; then dispatch triage "$ISSUE"; exit 0; fi

log "nothing to do"
