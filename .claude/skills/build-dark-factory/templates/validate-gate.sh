#!/usr/bin/env bash
# The structural gate. This is one of the two places in the whole factory where a
# decision is made by code that a model cannot talk its way past.
#
# It reads the raw output of the validation run and a verdict file produced by the
# reviewers, and it merges only when BOTH agree. If they disagree, the raw output
# wins and the PR escalates - because a model summarising its own run is exactly
# the thing that cannot be trusted at this step.
#
#   ./validate-gate.sh <pr-number> <run-log> <verdict.json>

set -euo pipefail

PR="${1:?pr number}"
LOG="${2:?path to the validation run log}"
VERDICT="${3:?path to verdict.json}"
REPO="${FACTORY_REPO:?set FACTORY_REPO to owner/name}"

# How many steps the end-to-end path is supposed to execute. If the E2E reports
# fewer, something was skipped, and skipped is not passed.
E2E_REQUIRED_STEPS="${FACTORY_E2E_STEPS:-1}"

fail() {
  echo "GATE_FAIL: $*" >&2
  gh pr edit "$PR" -R "$REPO" \
    --remove-label "factory:needs-review" --add-label "factory:needs-human" 2>/dev/null || true
  gh pr comment "$PR" -R "$REPO" --body "$(printf '%s\n' \
    "**Factory Gate**: BLOCKED" "" \
    "The structural gate refused this merge." "" \
    "Reason: $*" "" \
    "This decision was made by \`validate-gate.sh\`, not by a reviewer, and it is not appealable by re-running. Fix the underlying cause.")" 2>/dev/null || true
  exit 1
}

# =============================================================================
# 1. EMPTY IS NOT PASS
# =============================================================================
# Assert POSITIVE markers. Never test for the absence of the word "error".
# A check that never ran produces no failures, and code that asks "did anything
# fail?" reads that as success. A missing env var, a crashed process, a bad path -
# all of them produce a silent, confident pass.

[ -s "$LOG" ] || fail "the run log is empty - the validation run produced no output at all"

grep -q "APP_STARTED" "$LOG" \
  || fail "APP_STARTED marker absent - the application never started, so no end-to-end check can have run against it"

grep -q "E2E_PASSED" "$LOG" \
  || fail "E2E_PASSED marker absent - the end-to-end path never completed"

STEPS=$(grep -oE 'E2E_PASSED steps=[0-9]+' "$LOG" | tail -1 | grep -oE '[0-9]+' || echo 0)
[ "$STEPS" -ge "$E2E_REQUIRED_STEPS" ] \
  || fail "the end-to-end path ran only $STEPS of $E2E_REQUIRED_STEPS steps - the rest were skipped, and skipped is not passed"

# =============================================================================
# 2. PROTECTED FILES
# =============================================================================
# Evaluated before anything else about quality. A PR that can weaken the rulebook
# it is judged by has already invalidated every downstream check.

PROTECTED_RE="${FACTORY_PROTECTED_RE:-^(MISSION\.md|FACTORY_RULES\.md|CLAUDE\.md|AGENTS\.md|\.github/|Dockerfile|docker-compose|deploy/|infra/|\.env)}"
TOUCHED=$(gh pr diff "$PR" -R "$REPO" --name-only | grep -E "$PROTECTED_RE" || true)
[ -z "$TOUCHED" ] \
  || fail "protected files modified, which is an automatic reject: $(echo "$TOUCHED" | tr '\n' ' ')"

# =============================================================================
# 3. THE VERDICT FILE
# =============================================================================

[ -s "$VERDICT" ] || fail "verdict file is empty or missing - a reviewer step failed and produced nothing"
jq -e '.verdict' "$VERDICT" >/dev/null 2>&1 || fail "verdict file is not parseable JSON"

DECISION=$(jq -r '.verdict' "$VERDICT")
SUMMARY=$(jq -r '.summary // "no summary"' "$VERDICT")

case "$DECISION" in
  approve)
    # Both the markers and the reviewers agree. This is the only path that merges.
    echo "GATE_PASS: markers present and verdict=approve"
    gh pr review "$PR" -R "$REPO" --approve --body "$(printf '%s\n' \
      "**Factory Validation**: APPROVED" "" "$SUMMARY" "" \
      "Structural gate: APP_STARTED present, E2E_PASSED with $STEPS steps, no protected files touched." "" \
      "Auto-merging via squash.")" 2>/dev/null || true
    gh pr ready "$PR" -R "$REPO" 2>/dev/null || true
    gh pr merge "$PR" -R "$REPO" --squash \
      || fail "squash merge failed - leaving the PR open for a human"
    gh pr edit "$PR" -R "$REPO" \
      --remove-label "factory:needs-review" --add-label "factory:approved" 2>/dev/null || true
    echo "MERGED pr=$PR"
    ;;

  request_changes)
    gh pr review "$PR" -R "$REPO" --request-changes --body "**Factory Validation**: changes requested

$SUMMARY

$(jq -r '.issues_to_fix // [] | map("- **\(.severity)** [\(.category)]: \(.description)") | join("\n")' "$VERDICT")"
    gh pr edit "$PR" -R "$REPO" \
      --remove-label "factory:needs-review" --add-label "factory:needs-fix"
    echo "CHANGES_REQUESTED pr=$PR"
    ;;

  reject)
    gh pr review "$PR" -R "$REPO" --request-changes --body "**Factory Validation**: REJECTED

$SUMMARY

This PR cannot be fixed incrementally and is being closed. The issue is re-queued."
    gh pr close "$PR" -R "$REPO"
    ISSUE=$(gh pr view "$PR" -R "$REPO" --json body -q '.body' \
      | grep -oiE '(fixes|closes|resolves) #[0-9]+' | grep -oE '[0-9]+' | head -1 || true)
    if [ -n "$ISSUE" ]; then
      gh issue reopen "$ISSUE" -R "$REPO" 2>/dev/null || true
      gh issue edit "$ISSUE" -R "$REPO" \
        --add-label "factory:accepted" --remove-label "factory:in-progress" 2>/dev/null || true
    fi
    echo "REJECTED pr=$PR"
    ;;

  *)
    fail "unknown verdict '$DECISION'"
    ;;
esac
