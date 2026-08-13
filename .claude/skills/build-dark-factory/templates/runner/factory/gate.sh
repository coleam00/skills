#!/usr/bin/env bash
# The structural gate. One of the two places in the factory where a decision is made by
# code a model cannot talk its way past.
#
#   bash factory/gate.sh <pr-file> <gate-log> <verdict.json>
#
# It reads the RAW output of the validation run and the verdict the judge wrote, and it
# merges only when both agree. When they disagree, the raw output wins and the PR
# escalates -- because a model summarising its own run is precisely what cannot be
# trusted at this step.
#
# Every check below is a positive assertion. None of them test for the absence of the
# word "error". A check that never ran produces no failures, and "did anything fail?"
# reads that as success.

set -euo pipefail

PR_FILE="${1:?a PR target: gh:pr:<n> or .factory/prs/<id>.md}"
LOG="${2:?path to the gate log}"
VERDICT="${3:?path to verdict.json}"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

# Fallback: an escalation must never be the thing that fails.
command -v factory_notify >/dev/null 2>&1 || factory_notify() {
  echo "NOT NOTIFIED - factory/config.sh defines no factory_notify (old copy?)"
}

# Everything this script says about a PR goes through state.py, which appends to the
# record on the file backend and posts a comment on the GitHub one. The gate's reasoning
# has to land somewhere a human will actually look, and on GitHub that is the PR, not a
# file in .factory that nobody opens.
note() { python factory/state.py comment "$PR_FILE"; }

fail() {
  echo "GATE_FAIL: $*" >&2
  python factory/state.py set "$PR_FILE" state=needs-human >/dev/null 2>&1 || true

  # FACTORY_RULES.md 7: escalation stops factory activity on that PR **and its issue**,
  # and it is written to .factory/needs-human.md. Neither happened. This script escalated
  # the PR, exited 1, and the caller's escalate() -- which is the thing that writes that
  # file -- was never reached. So the one channel that is supposed to reach a human got
  # nothing, while the issue sat `in-progress` with a dead PR attached and no label saying
  # so. Both halves are done here now, by the script that made the decision.
  echo "- $(date -u +%FT%TZ)  $PR_FILE  (gate)  $*" >> .factory/needs-human.md
  # A blocked gate is the single most important thing a human can be told, and for a
  # while this path wrote a file and stopped there.
  factory_notify "$PR_FILE" "(gate) $*"
  ISSUE_REF="$(python factory/state.py get "$PR_FILE" 2>/dev/null | grep '^issue=' | head -1 | cut -d= -f2- || true)"
  if [ -n "${ISSUE_REF:-}" ]; then
    python factory/state.py set "$ISSUE_REF" state=needs-human >/dev/null 2>&1 || true
    echo "- $(date -u +%FT%TZ)  $ISSUE_REF  (gate)  its PR $PR_FILE was blocked: $*" >> .factory/needs-human.md
  fi
  {
    echo ""
    echo "## Factory Gate: BLOCKED"
    echo ""
    echo "Reason: $*"
    echo ""
    echo "Decided by \`factory/gate.sh\`, not by a reviewer. Not appealable by re-running;"
    echo "fix the underlying cause."
  } | note || true
  exit 1
}

# --- 0. precondition ---------------------------------------------------------
# The PR must already be `validating`, which the validate-pr workflow sets after the
# tripwire clears and before any check runs. Asserted rather than assumed: if this can be
# called on an `open` PR, then it can be called on a PR nobody independently validated,
# and the state machine is the only thing that knows the difference.
PR_STATE="$(python factory/state.py get "$PR_FILE" | grep '^state=' | cut -d= -f2)"
if [ "$PR_STATE" != "validating" ]; then
  echo "GATE_REFUSED: $PR_FILE is '$PR_STATE', expected 'validating'." >&2
  echo "  The gate runs INSIDE the validate-pr workflow, after the tripwire and after" >&2
  echo "  state=validating. Reaching it from '$PR_STATE' means the independent" >&2
  echo "  validation was skipped, so there is nothing here to gate on." >&2
  exit 2
fi

# --- 1. empty is not pass ----------------------------------------------------
[ -s "$LOG" ] || fail "the gate log is empty - the validation run produced no output at all"

# WHICH step stopped the run, if one did. The marker assertions below run in a fixed
# order and not in run order, so a suite that died at an early step was reported as
# "APP_STARTED absent - the app never started": true, and about four steps downstream of
# the cause. An unattended system that misnames its own failure sends whoever reads the
# log at 3am to the wrong file, and that is most of the cost of a failure nobody watched.
FAILED_STEP="$(grep -oE 'GATE_FAILED: [a-z0-9_]+' "$LOG" | tail -1 | cut -d' ' -f2 || true)"
if [ -n "${FAILED_STEP:-}" ]; then
  fail "the suite stopped at the '$FAILED_STEP' step, so every check after it never ran. $(grep -m1 -B1 "GATE_FAILED: $FAILED_STEP" "$LOG" | head -1 | head -c 300)"
fi

# The marker list is DATA, in factory/config.sh, not a hand-maintained block of greps.
# One marker per check family, and every one of them must have reported that it ran.
#
# Nothing here tests for the absence of the word "error". A check that never ran produces
# no failures, and code that asks "did anything fail?" reads that as success - so the
# question is never asked. The question is always "did this specific thing say it ran?"
MISSING=""
for MARKER in $FACTORY_REQUIRED_MARKERS; do
  grep -q "$MARKER" "$LOG" || MISSING="$MISSING $MARKER"
done
if [ -n "$MISSING" ]; then
  fail "required marker(s) absent from the run log:$MISSING. A check that did not report that it ran is not a check that passed. If you deleted a check, delete its marker from FACTORY_REQUIRED_MARKERS in the same human commit."
fi
echo "MARKERS_OK checked=$(echo "$FACTORY_REQUIRED_MARKERS" | wc -w | tr -d ' ')"

# --- 2. counts, not vibes ----------------------------------------------------
# A floor lives in a PROTECTED lock file so raising it is a deliberate human edit. Read
# the value; if the file is missing the floor is 0 and the count check is off, which is a
# legitimate starting configuration and not a silent one - it is reported below.
FLOOR=0
if [ -f "$FACTORY_E2E_FLOOR_FILE" ]; then
  FLOOR=$(python -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],0))" \
            "$FACTORY_E2E_FLOOR_FILE" "$FACTORY_E2E_FLOOR_KEY" 2>/dev/null || echo 0)
fi
STEPS=$(grep -oE 'E2E_PASSED steps=[0-9]+' "$LOG" | tail -1 | grep -oE '[0-9]+$' || echo 0)
if [ "$FLOOR" -gt 0 ]; then
  [ "$STEPS" -ge "$FLOOR" ] || fail "the end-to-end path asserted only $STEPS of $FLOOR steps - the rest were skipped, and skipped is not passed"
else
  echo "GATE_NOTE: no e2e floor set ($FACTORY_E2E_FLOOR_FILE). Steps are counted but not enforced."
fi

# Deliberate defects, if you have built a mutation set. All must be caught or nothing
# merges: every miss is a class of bug that can currently merge unreviewed.
MT=$(grep -oE 'MUTATIONS_TOTAL=[0-9]+'  "$LOG" | tail -1 | grep -oE '[0-9]+$' || echo 0)
MC=$(grep -oE 'MUTATIONS_CAUGHT=[0-9]+' "$LOG" | tail -1 | grep -oE '[0-9]+$' || echo -1)
if grep -q "MUTATIONS_TOTAL" "$LOG"; then
  [ "$MT" -gt 0 ]     || fail "zero deliberate defects were injected - a gate that has never failed is a gate nobody has tested"
  [ "$MC" -eq "$MT" ] || fail "the gate caught $MC of $MT deliberate defects; every miss is a class of bug that can currently merge unreviewed"
fi

# --- 3. calibration caps autonomy -------------------------------------------
# The judgement/measurement split, and it is the most transferable idea in this file.
#
# Some claims are ORDINAL and need no number - "reward rises with tier", "the p95 is
# lower than last release". Those gate today. Others are MARGIN claims and need a
# threshold somebody chose - "no tier dominates by more than X". A factory that invents
# X to turn a gate green is authoring taste in a config file, and it is the most tempting
# shortcut there is, because the number is right there in the output and one of them
# would make the red go away.
#
# So: any check that has a threshold nobody has set emits `<NAME>_UNCALIBRATED=<n>`. That
# does NOT fail the gate - it refuses the AUTO-merge and says so. The work still gets
# built and can still be merged by a human at level 2.
#
# Summed by PATTERN, not by an enumerated list of names. The version this was lifted from
# named three markers and carried a comment warning that a fourth would silently stop
# capping autonomy - the gate would go green and auto-merge against thresholds nobody had
# ever set. A rule whose correctness depends on remembering to update a list is a rule
# with an expiry date on it.
UNCAL=0
UNCAL_DETAIL=""
while read -r m; do
  [ -z "$m" ] && continue
  n="${m##*=}"
  UNCAL=$((UNCAL + n))
  UNCAL_DETAIL="$UNCAL_DETAIL ${m%%_UNCALIBRATED=*}:$n"
done <<EOF
$(grep -oE '[A-Z][A-Z0-9_]*_UNCALIBRATED=[0-9]+' "$LOG" | sort -u)
EOF

AUTOMERGE_ALLOWED=1
if [ "$UNCAL" -gt 0 ]; then
  AUTOMERGE_ALLOWED=0
  echo "GATE_NOTE: $UNCAL claim(s) have no calibrated threshold -$UNCAL_DETAIL"
  echo "GATE_NOTE: autonomy is capped at level 2 - verdict recorded, auto-merge refused."
fi

# --- 3b. an assumption holds the MERGE, it does not stop the WORK -------------
#
# The same mechanism as above, pointed at the other thing a factory should not decide
# alone. The plan node is told to choose unspecified PRODUCT values rather than stop -
# a price, a rate, a default - and to write what it chose to ASSUMPTIONS. That file
# arrives here, and the only consequence is that this particular PR waits for a human.
#
# Why hold rather than escalate: the work is built, validated and readable, so the human
# is answering "is 1.5 the right multiplier, here is what it does" instead of "what should
# the multiplier be" with nothing in front of them. Everything WITHOUT an assumption still
# auto-merges at level 3, so one open product question no longer stops the queue.
#
# JUDGEMENT values are not covered by this and never will be: a lock, a floor, a
# tolerance, a sample size, a mutation. Choosing one of those is tuning the judge, and the
# plan node escalates instead. That distinction is the whole safety argument.
ASSUMPTION_FILE=".factory/assumptions/$(basename "${PR_FILE%.md}" | sed 's/^gh-pr-//').txt"
ASSUMPTIONS=""
[ -s "$ASSUMPTION_FILE" ] && ASSUMPTIONS="$(cat "$ASSUMPTION_FILE")"
if [ -z "$ASSUMPTIONS" ]; then
  ISSUE_FOR_ASSUMPTIONS="$(python factory/state.py get "$PR_FILE" 2>/dev/null | grep '^issue=' | head -1 | cut -d= -f2- || true)"
  if [ -n "${ISSUE_FOR_ASSUMPTIONS:-}" ]; then
    A2=".factory/assumptions/$(basename "${ISSUE_FOR_ASSUMPTIONS%.md}" | tr ':' '-').txt"
    [ -s "$A2" ] && ASSUMPTIONS="$(cat "$A2")"
  fi
fi
if [ -n "$ASSUMPTIONS" ]; then
  AUTOMERGE_ALLOWED=0
  echo "GATE_NOTE: this change rests on $(printf '%s' "$ASSUMPTIONS" | grep -c .) recorded assumption(s); auto-merge refused, a human decides."
fi

# --- 4. the verdict ----------------------------------------------------------
[ -s "$VERDICT" ] || fail "verdict file is empty or missing - the judge step produced nothing, which is not an approval"
python -c "import json,sys;json.load(open(sys.argv[1]))['verdict']" "$VERDICT" \
  || fail "verdict file is not parseable JSON with a .verdict field"

DECISION=$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['verdict'])" "$VERDICT")
SUMMARY=$(python -c "import json,sys;print(json.load(open(sys.argv[1])).get('summary','no summary'))" "$VERDICT")

case "$DECISION" in
  approve)
    if [ "$AUTOMERGE_ALLOWED" -eq 0 ]; then
      python factory/state.py set "$PR_FILE" state=passed \
        || fail "the gate passed but the verdict could not be recorded on $PR_FILE"
      {
        echo "## Factory Gate: PASS, merge HELD"
        echo ""
        echo "Every structural marker is green and the judge returned \`approve\`."
        if [ -n "$ASSUMPTIONS" ]; then
          echo ""
          echo "**It rests on a decision the factory made rather than one you gave it.**"
          echo "The work is built and validated; merging it is you agreeing with the call."
          echo ""
          echo '```'
          printf '%s
' "$ASSUMPTIONS"
          echo '```'
          echo ""
          echo "Merge to accept, or say what the value should be and it will be rebuilt."
        fi
        if [ "$UNCAL" -gt 0 ]; then
          echo "Auto-merge is also refused because $UNCAL claim(s) have no calibrated threshold:"
          echo "$UNCAL_DETAIL"
        fi
        echo ""
        echo "- e2e steps asserted: $STEPS (floor $FLOOR)"
        echo "- deliberate defects caught: $MC/$MT"
        echo ""
        echo "This is not a failure and re-running will not change it. It clears when the"
        echo "lock files are calibrated against a build a human has actually used, which is"
        echo "deliberately a human decision. Until then the PR waits for a human to merge it."
      } | note || true
      HELD_WHY=""
      [ -n "$ASSUMPTIONS" ] && HELD_WHY="a recorded assumption"
      [ "$UNCAL" -gt 0 ] && HELD_WHY="${HELD_WHY:+$HELD_WHY and }uncalibrated locks"
      echo "GATE_PASS_HELD pr=$PR_FILE  (markers green, verdict approve, auto-merge held: ${HELD_WHY:-unknown})"
      exit 0
    fi
    # GUARDED, and it used to be bare. A bare state write under `set -e` exits this
    # script on the spot -- no GATE_FAIL, no needs-human, no notification -- and it is
    # reachable for an ordinary reason: on the GitHub backend this write is a label
    # edit, and `factory:approved` did not exist on a fresh repo. So the FIRST green
    # gate a new factory ever produced died here, silently, having decided to merge.
    python factory/state.py set "$PR_FILE" state=passed \
      || fail "the gate passed but the verdict could not be recorded on $PR_FILE; refusing to merge something whose state was never written"
    MUT_NOTE=""
    [ "$MT" -gt 0 ] && MUT_NOTE=", mutations $MC/$MT"
    echo "GATE_PASS pr=$PR_FILE  markers green, e2e steps=$STEPS$MUT_NOTE"
    bash factory/merge.sh "$PR_FILE" || fail "merge failed - leaving the PR for a human"
    ;;
  request_changes)
    # HAND THE FINDINGS FORWARD, to a path that outlives this run.
    #
    # The fix node's whole job is to address what the validator objected to, and the
    # objection lives in a verdict inside THIS run's directory - a directory the fix
    # workflow, which is a separate process started later by the dispatcher, has no way to
    # name. The prompt asked for it through a `{{prev_run}}` placeholder the runner never
    # substituted, so the fix node was handed a literal, non-existent path. It did not
    # crash: it read nothing and fixed from memory of the diff. Every fix attempt in this
    # factory would have been a guess at what the validator wanted.
    #
    # Keyed by the PR target so two PRs in flight cannot read each other's findings, and
    # copied rather than referenced so a pruned run directory cannot empty it.
    FINDINGS_KEY="$(printf '%s' "$PR_FILE" | tr '/.:\\' '----')"
    mkdir -p .factory/findings
    cp "$VERDICT" ".factory/findings/$FINDINGS_KEY.json" 2>/dev/null || true
    cp "$LOG"     ".factory/findings/$FINDINGS_KEY.gate.log" 2>/dev/null || true
    echo "FINDINGS_SAVED .factory/findings/$FINDINGS_KEY.json"

    python factory/state.py set "$PR_FILE" state=failed \
      || fail "changes were requested but the state could not be written; the fix loop would never see this PR"
    { echo "## Factory Validation: changes requested"; echo ""; echo "$SUMMARY"; } | note || true
    echo "CHANGES_REQUESTED pr=$PR_FILE"
    ;;
  reject)
    python factory/state.py set "$PR_FILE" state=rejected \
      || fail "the PR was rejected but the state could not be written"
    { echo "## Factory Validation: REJECTED"; echo ""; echo "$SUMMARY"; } | note || true
    echo "REJECTED pr=$PR_FILE"
    ;;
  *)
    fail "unknown verdict '$DECISION'"
    ;;
esac
