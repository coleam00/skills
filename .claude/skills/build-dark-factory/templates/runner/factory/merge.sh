#!/usr/bin/env bash
# The merge. The second of the two decisions made by code rather than by a model.
#
#   bash factory/merge.sh <pr-target>        # gh:pr:<n>, or .factory/prs/<id>.md
#
# This script re-checks the structural gates ITSELF before touching a branch. It does not
# trust that factory/gate.sh already did, and it does not trust the verdict file at all.
# The reason is ordering: gate.sh runs the checks and then calls this, so if anything ever
# calls this directly -- a retry, a human, a future workflow, a bug -- the merge still
# cannot happen against an unchecked branch.
#
# Re-checking costs seconds. Merging an unchecked branch costs a debugging session that
# starts with "but the gate was green".
#
# WHAT THE MOVE TO GITHUB DID NOT CHANGE. FACTORY_RULES.md 11 said branch protection plus
# required checks would replace this script, so that "the gate stops being a script the
# agent could in principle edit". It does not, on this repo, for a reason worth writing
# down: the factory authenticates as a user who administers the repository. An account
# that can edit a ruleset can bypass a ruleset. Branch protection is a good second lock
# and a bad only lock, and it becomes a real wall only when the token that merges belongs
# to a principal that cannot change the rules. Until then this script is still the gate,
# and it still re-checks everything itself.

set -euo pipefail

PR_FILE="${1:?a PR target: gh:pr:<n> or .factory/prs/<id>.md}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

case "$PR_FILE" in
  gh:*) GH=1; PR_NUM="${PR_FILE##*:}" ;;
  *)    GH=0; PR_NUM="" ;;
esac

read_fm() { python factory/state.py get "$PR_FILE" | grep "^$1=" | head -1 | cut -d= -f2-; }

BRANCH="$(read_fm branch)"
ISSUE="$(read_fm issue)"
STATE="$(read_fm state)"

[ -n "$BRANCH" ] || { echo "MERGE_REFUSED: no branch on $PR_FILE"; exit 1; }
[ "$STATE" = "passed" ] || { echo "MERGE_REFUSED: state is '$STATE', not 'passed'"; exit 1; }

if [ "$GH" -eq 1 ]; then
  git fetch --quiet origin main "$BRANCH" || { echo "MERGE_REFUSED: cannot fetch from origin"; exit 1; }
  BASE="origin/main"
  HEAD_REF="origin/$BRANCH"
else
  # `|| true` is load-bearing: with no remote configured, symbolic-ref exits non-zero and
  # `set -e` would kill the script here with no output at all.
  BASE="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@.*/@@' || true)"
  BASE="${BASE:-main}"
  HEAD_REF="$BRANCH"
fi

echo "MERGE_START branch=$BRANCH base=$BASE issue=$ISSUE"

# --- re-check, independently -------------------------------------------------
python factory/guard.py --base "$BASE" --head "$HEAD_REF" \
  || { echo "MERGE_REFUSED: protected-path guard failed on re-check"; exit 1; }

git rev-parse --verify --quiet "$HEAD_REF" >/dev/null \
  || { echo "MERGE_REFUSED: $HEAD_REF does not exist"; exit 1; }

# The branch must actually contain the base, or the squash silently drops work that
# landed while this branch was in flight.
git merge-base --is-ancestor "$BASE" "$HEAD_REF" \
  || {
       # REQUEUE, do not park. Refusing is right - squashing a stale branch silently drops
       # whatever landed while it was in flight - but the refusal used to be terminal: the
       # PR sat at `passed`, which nothing dispatches, and every later tick reprinted this
       # line forever. Indistinguishable from an idle factory.
       #
       # The remedy the message already recommends is exactly what validate-pr does on its
       # own, so send it back rather than telling a human to do it by hand. `passed -> open`
       # is legal for this reason; validate-pr rebases before validating, so the requeued
       # PR is judged on the tree that will actually merge.
       echo "MERGE_REFUSED: $BRANCH is behind $BASE - squashing it now would silently drop whatever landed while it was in flight"
       if python factory/state.py set "$PR_FILE" state=open >/dev/null 2>&1; then
         echo "MERGE_REQUEUED: $PR_FILE is back to 'open'; the validator will rebase it and re-judge the rebased tree"
       else
         echo "MERGE_REFUSED: could not requeue $PR_FILE - it needs a human"
       fi
       exit 1; }

# --- merge -------------------------------------------------------------------
if [ "$GH" -eq 1 ]; then
  # GitHub's own view of the PR, re-read here rather than taken from the labels. A label
  # says what the factory believes; `state` and `mergeable` say what GitHub will actually
  # do, and a PR closed or made conflicting since validation must not be squashed anyway.
  PR_JSON="$(gh pr view "$PR_NUM" --json state,mergeable,isDraft,baseRefName,mergeStateStatus)"
  PR_STATE="$(python -c "import json,sys;print(json.loads(sys.argv[1])['state'])" "$PR_JSON")"
  PR_MERGEABLE="$(python -c "import json,sys;print(json.loads(sys.argv[1])['mergeable'])" "$PR_JSON")"
  PR_DRAFT="$(python -c "import json,sys;print(json.loads(sys.argv[1])['isDraft'])" "$PR_JSON")"
  PR_BASE="$(python -c "import json,sys;print(json.loads(sys.argv[1])['baseRefName'])" "$PR_JSON")"

  [ "$PR_STATE" = "OPEN" ]      || { echo "MERGE_REFUSED: PR #$PR_NUM is $PR_STATE"; exit 1; }
  [ "$PR_DRAFT" = "False" ]     || { echo "MERGE_REFUSED: PR #$PR_NUM is a draft"; exit 1; }
  [ "$PR_BASE" = "main" ]       || { echo "MERGE_REFUSED: PR #$PR_NUM targets '$PR_BASE', not main"; exit 1; }
  [ "$PR_MERGEABLE" = "MERGEABLE" ] \
    || { echo "MERGE_REFUSED: GitHub reports mergeable=$PR_MERGEABLE"; exit 1; }

  # `mergeable` AND `mergeStateStatus` are different questions, and only the second knows
  # about branch protection. A PR on a protected branch reports `mergeable=MERGEABLE`
  # (there is no conflict) and `mergeStateStatus=BLOCKED` (a required review or a required
  # status check has not happened). Checking only the first, this script sailed past every
  # pre-check and failed at `gh pr merge` with the generic "gh pr merge failed", which is
  # true and useless: a human reads it, re-runs, and gets the same thing forever, because
  # a protection rule is not a transient failure.
  #
  # Named here instead, with the remedy, because the remedy is a REPO SETTING and no
  # amount of re-running or re-validating will change it.
  PR_MERGE_STATE="$(python -c "import json,sys;print(json.loads(sys.argv[1]).get('mergeStateStatus',''))" "$PR_JSON")"
  case "$PR_MERGE_STATE" in
    BLOCKED)
      echo "MERGE_REFUSED: GitHub reports mergeStateStatus=BLOCKED on PR #$PR_NUM."
      echo "  Branch protection on 'main' is refusing this merge - typically a required"
      echo "  approving review, or a required status check that has not run. The factory"
      echo "  cannot satisfy either: it has no second human to review, and at level 3 the"
      echo "  merge IS the review."
      echo "  Decide deliberately: either exempt this actor from the rule, or run the"
      echo "  factory at level 2 and merge these PRs by hand. Re-running will not help."
      exit 1 ;;
    BEHIND)
      echo "MERGE_REFUSED: PR #$PR_NUM is BEHIND main - protection requires branches to be"
      echo "  up to date before merging. validate-pr rebases before it validates, so this"
      echo "  means main moved again since the verdict. It will clear on the next lap."
      exit 1 ;;
    DIRTY)
      echo "MERGE_REFUSED: PR #$PR_NUM is DIRTY - GitHub sees a conflict with main."
      exit 1 ;;
    UNKNOWN|"")
      # GitHub computes this asynchronously; empty or UNKNOWN means "not worked out yet",
      # which is not the same as "fine". Refuse and let the next tick ask again.
      echo "MERGE_REFUSED: GitHub has not computed a merge state for PR #$PR_NUM yet"
      echo "  (mergeStateStatus='$PR_MERGE_STATE'). Not merging on an unknown. The next"
      echo "  dispatch will ask again."
      exit 1 ;;
  esac

  # `gh pr merge` is the one `gh` call left outside gh_backend.py, on purpose. It performs
  # a STATE change rather than publishing prose, and its message goes as argv rather than
  # through a pipe, so neither failure mode in FACTORY_RULES.md 10.1 can reach it. What
  # landed is read back below all the same.
  TITLE="$(read_fm title)"
  gh pr merge "$PR_NUM" --squash --delete-branch \
    --subject "${TITLE:-factory: $ISSUE}" \
    --body "Merged by factory/merge.sh from $BRANCH.
Issue: $ISSUE
Gates: contract, ratchet, mutations, e2e, guard -- all green on re-check.
No human read this diff." \
    || { echo "MERGE_REFUSED: gh pr merge failed - leaving for a human"; exit 1; }

  # Bring the local checkout back in line. Without this the next branch is cut from a
  # main that is one merge behind, and the guard's merge base is a commit the remote has
  # already moved past. Nothing errors; the diff just quietly contains someone else's work.
  git fetch --quiet origin main
  if [ "$(git rev-parse --abbrev-ref HEAD)" = "main" ]; then
    git merge --ff-only origin/main >/dev/null 2>&1 || true
  else
    git update-ref refs/heads/main origin/main || true
  fi
  MERGED_SHA="$(git rev-parse --short origin/main)"
  # Read the squash commit back. The merge is the least reversible thing this factory
  # does, so one call to confirm what actually landed is cheap.
  LANDED="$(git log -1 --pretty=%s origin/main)"
  case "$LANDED" in
    *"${TITLE:-factory}"*) echo "MERGE_VERIFIED subject=$LANDED" ;;
    *) echo "MERGE_WARNING: squash subject is '$LANDED', expected to contain '${TITLE:-factory}'" ;;
  esac
else
  # A DIRTY WORKING TREE IS NOT A CONFLICT, and reporting it as one sends whoever reads
  # the log looking for a merge conflict that does not exist.
  #
  # On the file backend the root checkout is dirty for most of a lap BY DESIGN: `state.py`
  # edits `issues/<id>.md` in place and the review node writes `.factory/prs/<id>.md`, and
  # both are tracked on purpose because on this backend they ARE the state. `git merge
  # --squash` refuses when a local change would be overwritten, so the failure arrives at
  # the merge - the least reversible, most expensive step - having been caused three
  # workflows earlier by something perfectly normal.
  #
  # Detected FIRST, and named. The remedy is different in each case (commit or stash the
  # state files, versus resolve a real conflict), and a message that picks the wrong one
  # costs more than no message.
  # One pipeline, no stray commands. The first draft of this check opened with a
  # `git merge-tree` probe that this git does not support; under `set -e` its failure
  # killed the command substitution's subshell, so BLOCKERS came back EMPTY and the check
  # silently passed on the exact case it was written to catch. A guard that fails open is
  # worse than no guard, and it is the same shape as every other silent death in this
  # runner: a non-zero exit somewhere the author was not thinking about exits.
  BLOCKERS=""
  while read -r f; do
    [ -n "$f" ] || continue
    if ! git diff --quiet -- "$f" 2>/dev/null; then
      BLOCKERS="$BLOCKERS $f(modified)"
    elif [ -n "$(git ls-files --others --exclude-standard -- "$f" 2>/dev/null)" ]; then
      BLOCKERS="$BLOCKERS $f(untracked)"
    fi
  done <<EOF
$(git diff --name-only "$BASE...$BRANCH" 2>/dev/null || true)
EOF
  if [ -n "${BLOCKERS// /}" ]; then
    echo "MERGE_REFUSED: the working tree has uncommitted changes to file(s) this branch also changed: $BLOCKERS"
    echo "  This is NOT a merge conflict. Commit or stash those files and re-run the merge."
    echo "  On the file backend, issues/*.md and .factory/prs/*.md are tracked state that"
    echo "  the runner edits in place, so they are the usual cause."
    exit 1
  fi

  git checkout -q "$BASE" || { echo "MERGE_REFUSED: could not check out $BASE - the working tree is not in a state a merge can run from"; exit 1; }
  if ! git merge --squash "$BRANCH"; then
    git merge --abort 2>/dev/null || true
    echo "MERGE_REFUSED: squash produced conflicts - leaving for a human"
    exit 1
  fi
  TITLE="$(read_fm title)"
  git commit -q -m "${TITLE:-factory: $ISSUE}

Merged by factory/merge.sh from $BRANCH.
Issue: $ISSUE
Gates: contract, ratchet, mutations, e2e, guard -- all green on re-check.
No human read this diff."
  git branch -q -D "$BRANCH" 2>/dev/null || true
  MERGED_SHA="$(git rev-parse --short HEAD)"
fi

# =============================================================================
# EVERYTHING PAST THIS LINE IS BOOKKEEPING, AND BOOKKEEPING MUST NOT BE ABLE TO
# REPORT THE MERGE AS FAILED.
# =============================================================================
# The merge is the least reversible thing this factory does, and it has now HAPPENED.
# What follows updates records to match reality. If one of those writes fails, reality is
# unchanged - the code is on the base branch either way.
#
# It used to `set -e` straight out of here. Observed end to end: the squash landed
# perfectly, the follow-up tried to move an issue that a previous failed run had parked
# at `needs-human`, that transition is correctly forbidden, and the script exited
# non-zero. The caller printed `GATE_FAIL: merge failed`, the deploy never ran, and the
# log told a human that nothing had merged while the commit sat on main.
#
# That is the worst direction for this error to point. A false "it failed" after a
# successful merge invites someone to re-run or re-implement work that already shipped.
# Report the merge, then report the bookkeeping separately and loudly.
BOOKKEEPING_FAILED=""

python factory/state.py set "$PR_FILE" state=merged \
  || BOOKKEEPING_FAILED="$BOOKKEEPING_FAILED PR-record($PR_FILE)"

if [ "$GH" -eq 1 ]; then
  python factory/state.py set "$ISSUE" state=done \
    || BOOKKEEPING_FAILED="$BOOKKEEPING_FAILED issue($ISSUE)"
else
  python factory/state.py set "issues/$(basename "$ISSUE")" state=done 2>/dev/null \
    || python factory/state.py set "$ISSUE" state=done \
    || BOOKKEEPING_FAILED="$BOOKKEEPING_FAILED issue($ISSUE)"
fi

echo "MERGED branch=$BRANCH -> $BASE"
echo "MERGED_SHA=$MERGED_SHA"

if [ -n "$BOOKKEEPING_FAILED" ]; then
  echo "MERGE_BOOKKEEPING_FAILED:$BOOKKEEPING_FAILED"
  echo "  THE CODE IS MERGED. $MERGED_SHA is on $BASE and the deploy should run."
  echo "  What failed is the record-keeping - most often an issue already parked at"
  echo "  needs-human, which a node may never move. Fix the record by hand; do NOT"
  echo "  re-run the implementation, and do not treat this as an unmerged PR."
  echo "- $(date -u +%FT%TZ)  $PR_FILE  (merge)  merged as $MERGED_SHA but records not updated:$BOOKKEEPING_FAILED" \
    >> .factory/needs-human.md
fi

# Deployment is a separate step on purpose: a merge that also deploys makes a bad merge
# and a bad deploy the same incident. See factory/deploy.sh.
echo "NEXT: bash factory/deploy.sh"
