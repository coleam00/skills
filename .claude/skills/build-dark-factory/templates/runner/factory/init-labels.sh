#!/usr/bin/env bash
# Create the label vocabulary on GitHub. Run ONCE, before the first lap on that backend.
#
#   bash factory/init-labels.sh            create anything missing
#   bash factory/init-labels.sh --check    report only, exit 1 if any are missing
#
# THESE LABELS ARE THE STATE MACHINE. On the GitHub backend there is no front matter to
# read - `factory/state.py` derives every state from the labels below, so a missing one
# is not cosmetic: the dispatcher silently cannot see work in that state, and a factory
# that cannot see work looks exactly like a factory with nothing to do.
#
# They are also the audit trail, and the reason the state lives here rather than in a
# database: labels are visible, editable by a human from a phone, and already backed up.

set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "No origin remote - this repo is on the FILE backend and needs no labels."
  echo "Issues live in issues/<id>.md and their front matter is the state."
  exit 0
fi

# name|colour|description
LABELS=$(cat <<'EOF'
factory:accepted|0e8a16|Triaged and in scope. The dispatcher may build it.
factory:in-progress|fbca04|A workflow is on it now. Not a queue state.
factory:needs-review|1d76db|A PR is waiting for the independent validator.
factory:needs-fix|d93f0b|The validator asked for changes. Under the attempt cap.
factory:approved|0e8a16|Passed every structural gate. Also marks merged PRs and done issues.
factory:needs-human|b60205|Stopped. The only state that should reach a person.
factory:rejected|e4e669|Out of scope. Closed not-planned, with the rule cited.
factory:deferred|c5def5|In scope, not now. NOT the same as rejected.
factory:rate-limited|d4c5f9|Flood protection. Re-evaluated after midnight UTC.
factory:stop|000000|EMERGENCY STOP. Any open issue with this halts all dispatch.
priority:critical|b60205|Production broken, data loss, or a security hole.
priority:high|d93f0b|Core feature broken for most users.
priority:medium|fbca04|Non-core, or a new in-scope feature.
priority:low|0e8a16|Docs, typos, polish.
EOF
)

# --- DRIFT GUARD: the table above must cover every label the backend can write --------
#
# `factory:approved` was missing from that list for its entire life, and it is the label
# THREE states write (`passed`, `merged`, `done`). So a fresh GitHub factory worked
# perfectly right up to its first green gate, at which point `gh pr edit --add-label
# factory:approved` failed with `'factory:approved' not found`, state.py returned 4, and
# gate.sh died on an unguarded line under `set -e`: no merge, no escalation, no
# notification. The one moment the factory was about to do the thing it exists for.
#
# A hand-maintained list that has to agree with a dict in another file is a list with an
# expiry date on it, so the agreement is now ASSERTED rather than remembered. The colours
# and descriptions stay editorial; the NAMES are checked against the source of truth.
EXPECTED="$(python - <<'PY' 2>/dev/null || true
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "factory"))
try:
    import gh_backend as B
except Exception:
    raise SystemExit(0)
names = set(B.LABEL_FOR_STATE.values())
names.add(os.environ.get("FACTORY_STOP_LABEL", "factory:stop"))
for n in sorted(names):
    print(n)
PY
)"
# `tr -d '\r'`, and without it this guard reports EVERY label as uncovered. Python on
# Windows writes text-mode newlines, so each name arrives as `factory:accepted\r` and
# `grep -qx` matches nothing - a check that fails closed on a correct table, which is
# just a louder way of being wrong.
EXPECTED="$(printf '%s' "$EXPECTED" | tr -d '\r')"
if [ -n "$EXPECTED" ]; then
  UNCOVERED=""
  while read -r want; do
    [ -z "$want" ] && continue
    printf '%s\n' "$LABELS" | cut -d'|' -f1 | grep -qx "$want" || UNCOVERED="$UNCOVERED $want"
  done <<< "$EXPECTED"
  if [ -n "$UNCOVERED" ]; then
    echo "LABEL_TABLE_INCOMPLETE:$UNCOVERED" >&2
    echo "factory/gh_backend.py writes those labels and this script does not create them." >&2
    echo "The factory would fail the moment it first tried to set that state. Add them above." >&2
    exit 2
  fi
fi

missing=0
created=0

while IFS='|' read -r name colour desc; do
  [ -z "$name" ] && continue
  if gh label list --limit 200 --json name --jq '.[].name' 2>/dev/null | grep -qx "$name"; then
    printf '  ok       %s\n' "$name"
    continue
  fi
  missing=$((missing + 1))
  if [ "$CHECK_ONLY" -eq 1 ]; then
    printf '  MISSING  %s\n' "$name"
  else
    gh label create "$name" --color "$colour" --description "$desc" >/dev/null 2>&1 \
      && { printf '  created  %s\n' "$name"; created=$((created + 1)); } \
      || printf '  FAILED   %s\n' "$name"
  fi
done <<< "$LABELS"

echo
if [ "$CHECK_ONLY" -eq 1 ]; then
  if [ "$missing" -gt 0 ]; then
    echo "LABELS_MISSING=$missing - run without --check to create them."
    echo "Until they exist the dispatcher cannot see work in those states."
    exit 1
  fi
  echo "LABELS_OK all present"
else
  echo "LABELS_OK created=$created"
  echo ""
  echo "The stop button is now reachable from a phone: label any open issue"
  echo "  factory:stop  and every dispatch halts before it reads anything else."
fi
