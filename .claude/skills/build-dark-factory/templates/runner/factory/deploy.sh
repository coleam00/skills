#!/usr/bin/env bash
# Component 3. THE LOOP IS NOT CLOSED UNTIL A STRANGER CAN SEE THE CHANGE.
#
#   bash factory/deploy.sh [--rollback]
#
# If merging does not put code in front of a user, you have built a PR generator with
# extra steps, and the validation harness has been proving things about software nobody
# runs.
#
# This is the SIMPLEST shape that has the properties that matter: a versioned snapshot
# that started successfully, and a pointer at the one users get. Swap the build and swap
# steps for your real deploy - blue/green, a platform push, a container tag swap, a
# static publish. Keep the three properties.
#
#   * It NO-OPS when nothing changed. An unattended deploy loop runs far more often than
#     it deploys, and a deploy path that does work on every tick will eventually do damage
#     on a tick where nothing happened.
#   * The HEALTH CHECK gates the swap. Never point `current` at a build that has not
#     answered. This is the last gate before real users, and the only one that runs after
#     the merge.
#   * ROLLBACK is one command, decided now rather than during the incident.
#
# NOT push-triggered, and this is the trap that silently kills more factories than
# anything else: GITHUB DOES NOT TRIGGER WORKFLOWS ON COMMITS MADE WITH THE DEFAULT
# GITHUB_TOKEN. The agent commits and merges, your `on: push` deploy never fires, nothing
# errors, nothing logs, and the site serves the old build for a week. Either authenticate
# as a GitHub App, or do what this does and POLL - a poll cannot be silently skipped,
# because nothing had to fire for it to run.
#
# Prefer the mechanism that fails loudly. This is a system whose defining property is
# that nobody is watching it.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

# What a built snapshot contains. Everything the app needs to run, and nothing else.
FACTORY_BUILD_INCLUDE="${FACTORY_BUILD_INCLUDE:-src app README.md}"

# The health check. It must START the thing and prove it WORKED - not "did the process
# exit 0". A build that starts, prints nothing and exits clean is indistinguishable from
# a healthy one unless you assert a positive marker. Same rule as the gate, applied after
# the merge.
FACTORY_HEALTH_CMD="${FACTORY_HEALTH_CMD:-}"
# Extended regexes that must ALL appear in the health output. Assert an OUTCOME a user
# would notice, not a status code.
FACTORY_HEALTH_MARKERS="${FACTORY_HEALTH_MARKERS:-}"

BUILDS="builds"
POINTER="$BUILDS/CURRENT"
HISTORY="$BUILDS/HISTORY"

mkdir -p "$BUILDS"

# --- rollback ----------------------------------------------------------------
if [ "${1:-}" = "--rollback" ]; then
  [ -s "$HISTORY" ] || { echo "ROLLBACK_FAILED: no deploy history"; exit 1; }
  PREV=$(tail -2 "$HISTORY" | head -1 | awk '{print $2}')
  [ -n "$PREV" ] && [ -d "$BUILDS/$PREV" ] \
    || { echo "ROLLBACK_FAILED: no previous build to roll back to"; exit 1; }
  echo "$PREV" > "$POINTER"
  echo "$(date -u +%FT%TZ) $PREV rollback" >> "$HISTORY"
  echo "ROLLED_BACK to=$PREV"
  exit 0
fi

SHA="$(git rev-parse --short HEAD)"
DEST="$BUILDS/$SHA"

# --- no-op when nothing changed ---------------------------------------------
if [ -f "$POINTER" ] && [ "$(cat "$POINTER")" = "$SHA" ] && [ -d "$DEST" ]; then
  echo "DEPLOY_NOOP sha=$SHA already current"
  exit 0
fi

echo "DEPLOY_START sha=$SHA"

# --- build -------------------------------------------------------------------
rm -rf "$DEST"
mkdir -p "$DEST"
COPIED=0
MISSING=""
for item in $FACTORY_BUILD_INCLUDE; do
  if [ -e "$item" ]; then
    cp -r "$item" "$DEST/"
    COPIED=$((COPIED + 1))
  else
    MISSING="$MISSING $item"
  fi
done

# EMPTY IS NOT PASS, APPLIED TO THE ONE STEP THAT FACES REAL USERS.
#
# `FACTORY_BUILD_INCLUDE` defaults to `src app README.md`, and a missing entry was skipped
# in silence. On a monorepo - where the code is under `packages/*` - not one entry matches,
# so the snapshot came out holding nothing but BUILD_SHA. Whether that reached users then
# depended entirely on where the health command happened to live: run from inside the
# snapshot it fails (correctly, and by accident), but a health command given as an
# absolute path passes happily and the pointer moves to a build of nothing.
#
# A deploy that copied zero files is not a deploy. Asserted here rather than left to the
# health check, because "the next gate probably catches it" is the reasoning this whole
# system exists to replace.
if [ "$COPIED" -eq 0 ]; then
  echo "DEPLOY_REFUSED: FACTORY_BUILD_INCLUDE matched nothing -$FACTORY_BUILD_INCLUDE"
  echo "  The build snapshot would contain no code at all. Set FACTORY_BUILD_INCLUDE in"
  echo "  factory/config.sh to the paths this project actually ships; the default"
  echo "  (src app README.md) is wrong for a monorepo or any non-standard layout."
  echo "  Pointer NOT moved."
  exit 1
fi
echo "BUILD_SNAPSHOT copied=$COPIED of $(echo "$FACTORY_BUILD_INCLUDE" | wc -w | tr -d ' ')"
# Named, not silent. A snapshot quietly missing a directory is a deploy that works right
# up until the first request that needs it.
[ -n "$MISSING" ] && echo "BUILD_INCLUDE_MISSING:$MISSING (listed in FACTORY_BUILD_INCLUDE, not present in the tree)"
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo "$SHA" > "$DEST/BUILD_SHA"
git log -1 --pretty='%s' > "$DEST/BUILD_SUBJECT"

# --- health check: it must actually start, and actually do the thing ----------
# The last gate before real users, and the only one that runs after the merge. Never
# swap traffic onto a build that has not answered.
echo "HEALTH_CHECK_START"
HEALTH_LOG="$DEST/health.log"

if [ -z "$FACTORY_HEALTH_CMD" ]; then
  # Refuses rather than defaulting to healthy. A deploy with no health check is a deploy
  # that cannot fail, and a step that cannot fail is not a gate - it is a comment. This
  # is empty-is-not-pass applied to the last thing standing between a merge and a user.
  echo "HEALTH_CHECK_MISSING: FACTORY_HEALTH_CMD is not set in factory/config.sh."
  echo "  Set it to a command that starts this build and proves it worked, and set"
  echo "  FACTORY_HEALTH_MARKERS to what its output must contain. Pointer NOT moved."
  exit 1
fi

if ! ( cd "$DEST" && eval "$FACTORY_HEALTH_CMD" ) > "$HEALTH_LOG" 2>&1; then
  echo "HEALTH_CHECK_FAILED: the build did not run. Pointer NOT moved."
  sed 's/^/  /' "$HEALTH_LOG" | tail -20
  exit 1
fi

# Assert the OUTCOME, not the exit code. The failure this catches is the one an exit code
# cannot see: a process that starts, hangs or does nothing, and returns zero. Whatever
# your app's equivalent of "it actually served a request" is, assert that.
for MARKER in $FACTORY_HEALTH_MARKERS; do
  if ! grep -qE "$MARKER" "$HEALTH_LOG"; then
    echo "HEALTH_CHECK_FAILED: the build ran but '$MARKER' never appeared in its output."
    echo "  'It exited zero' is not evidence that the app works. Pointer NOT moved."
    sed 's/^/  /' "$HEALTH_LOG" | tail -20
    exit 1
  fi
done
echo "HEALTH_CHECK_OK markers=$(echo "$FACTORY_HEALTH_MARKERS" | wc -w | tr -d ' ')"

# --- swap --------------------------------------------------------------------
echo "$SHA" > "$POINTER"
echo "$(date -u +%FT%TZ) $SHA deploy" >> "$HISTORY"

# Keep the last 10 builds. Rollback needs the previous one warm; the other eight are
# there so a bisect after a bad week does not need a rebuild.
ls -1dt "$BUILDS"/*/ 2>/dev/null | tail -n +11 | xargs -r rm -rf

echo "DEPLOYED sha=$SHA"
echo "LIVE: $POINTER -> $SHA"
