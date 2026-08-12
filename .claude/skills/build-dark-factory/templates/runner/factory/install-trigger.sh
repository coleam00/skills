#!/usr/bin/env bash
# Component 2, the last mile. This is the switch that makes the repository unattended.
#
#   bash factory/install-trigger.sh --status     what is armed right now
#   bash factory/install-trigger.sh --install    arm it
#   bash factory/install-trigger.sh --remove     disarm it
#
# Everything else in this factory can be run by hand and inspected. This is the one step
# that takes the human out, so it is the last thing you do and the first thing you check
# when something has gone quiet.
#
# ---------------------------------------------------------------------------
# IT POLLS. NOTHING PUSHES.
# ---------------------------------------------------------------------------
# Filing an issue does not trigger a run. There is no webhook and there is not meant to
# be one. A scheduler wakes up on a timer, reads the state, and dispatches at most one
# thing. An issue filed at 09:01 waits until the next tick.
#
# That is deliberate. A push trigger that fails, fails SILENTLY - nothing errors, nothing
# logs, and the factory looks like it had nothing to do. A poll that fails is a poll you
# can see not running. In a system whose defining property is that nobody is watching,
# always prefer the mechanism that fails loudly.
#
# The 30-minute default is also deliberate, and it is slower than feels right. A fast
# loop multiplies the cost of a mistake before you have noticed the mistake.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
# shellcheck source=factory/config.sh
. "$ROOT/factory/config.sh"

INTERVAL_MIN="${FACTORY_INTERVAL_MINUTES:-30}"
TASK_NAME="${FACTORY_TASK_NAME:-dark-factory-$(basename "$ROOT")}"
LOGFILE="$ROOT/factory-orchestrator.log"
ACTION="${1:---status}"

case "$(uname -s 2>/dev/null || echo Windows)" in
  Linux*)   PLATFORM=linux   ;;
  Darwin*)  PLATFORM=macos   ;;
  MINGW*|MSYS*|CYGWIN*|Windows*) PLATFORM=windows ;;
  *)        PLATFORM=unknown ;;
esac

CRON_LINE="*/$INTERVAL_MIN * * * * cd $ROOT && bash factory/orchestrator.sh >> $LOGFILE 2>&1  # $TASK_NAME"

say() { printf '%s\n' "$*"; }

# =============================================================================
# THE REFUSAL. Read this before removing it.
# =============================================================================
# The dial is at 0 until a lap has been proven by hand. Arming a scheduler at 0 gives you
# a cron that wakes up forever and correctly does nothing - which is harmless, and is also
# how people convince themselves the factory is "running" when it has never completed a
# lap. Worse is arming it at 3 on a factory whose gate has never been tested: that is an
# unsupervised code generator nobody has ever checked.
#
# Refusing here is the code version of "the trigger is built last". It is the whole
# argument of this skill expressed as an exit status.
require_dial() {
  if [ "${FACTORY_AUTONOMY:-0}" -lt 1 ]; then
    say "REFUSING: FACTORY_AUTONOMY is ${FACTORY_AUTONOMY:-0}."
    say ""
    say "  A scheduler at level 0 wakes up and does nothing, forever. That is not a"
    say "  factory, it is a cron job with good intentions - and it looks identical to a"
    say "  working one, which is worse."
    say ""
    say "  Prove one lap by hand first:"
    say "     bash factory/orchestrator.sh --dry-run"
    say "     bash factory/run-workflow.sh implement-issue <target>"
    say ""
    say "  Then set FACTORY_AUTONOMY=1 in factory/config.sh and run this again."
    exit 1
  fi
}

status_linux_macos() {
  if crontab -l 2>/dev/null | grep -qF "$TASK_NAME"; then
    say "ARMED (cron):"
    crontab -l 2>/dev/null | grep -F "$TASK_NAME" | sed 's/^/    /'
  else
    say "NOT ARMED - no cron entry named $TASK_NAME"
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-timers 2>/dev/null | grep -q "$TASK_NAME"; then
    say "ARMED (systemd timer): $TASK_NAME.timer"
  fi
}

status_windows() {
  if schtasks //Query //TN "$TASK_NAME" >/dev/null 2>&1; then
    say "ARMED (Task Scheduler): $TASK_NAME"
    schtasks //Query //TN "$TASK_NAME" //FO LIST 2>/dev/null | grep -iE "Status|Next Run|Schedule" | sed 's/^/    /'
  else
    say "NOT ARMED - no scheduled task named $TASK_NAME"
  fi
}

install_linux_macos() {
  require_dial
  if crontab -l 2>/dev/null | grep -qF "$TASK_NAME"; then
    say "already armed; removing the old entry first"
    remove_linux_macos
  fi
  { crontab -l 2>/dev/null || true; printf '%s\n' "$CRON_LINE"; } | crontab -
  say "ARMED: every $INTERVAL_MIN minutes"
  say "  $CRON_LINE"
  say ""
  say "Log:  $LOGFILE"
  say "Stop: touch $FACTORY_STOP_FILE   (checked before anything else, every tick)"
}

remove_linux_macos() {
  crontab -l 2>/dev/null | grep -vF "$TASK_NAME" | crontab - || true
  say "DISARMED: cron entry $TASK_NAME removed"
}

install_windows() {
  require_dial
  # A LAUNCHER FILE, not an inline command, and this is not tidiness.
  #
  # `schtasks /TR` is capped at 261 characters. An inline `bash -lc "cd <root> && ..."`
  # blows that on any repo more than a couple of directories deep, and schtasks reports
  # it as a flat ERROR with no task created - so the factory is simply never scheduled
  # while everything upstream says it succeeded. Same 260-ish Windows ceiling that has
  # already broken `git worktree add` in a real factory; it turns up in a different
  # costume every time.
  #
  # Writing a launcher keeps /TR down to one path, and has the side benefit that you can
  # run the launcher by hand to see exactly what the scheduler will do.
  local LAUNCHER="$ROOT/factory/tick.cmd"
  local BASH_EXE; BASH_EXE="$(cygpath -w "$(command -v bash)" 2>/dev/null || command -v bash)"
  local WROOT;    WROOT="$(cygpath -w "$ROOT" 2>/dev/null || echo "$ROOT")"
  local WLOG;     WLOG="$(cygpath -w "$LOGFILE" 2>/dev/null || echo "$LOGFILE")"
  {
    printf '@echo off\r\n'
    printf 'REM Generated by factory/install-trigger.sh. One tick of the dispatcher.\r\n'
    printf 'REM Run this by hand to see exactly what the scheduler runs.\r\n'
    printf '"%s" -lc "cd \x27%s\x27 && bash factory/orchestrator.sh" >> "%s" 2>&1\r\n' \
      "$BASH_EXE" "$ROOT" "$WLOG"
  } > "$LAUNCHER"

  local WLAUNCH; WLAUNCH="$(cygpath -w "$LAUNCHER" 2>/dev/null || echo "$LAUNCHER")"
  if [ "${#WLAUNCH}" -gt 250 ]; then
    say "REFUSING: the launcher path is ${#WLAUNCH} characters and schtasks caps /TR at 261."
    say "  Move the repo somewhere shallower, or schedule it by hand. Failing here is"
    say "  better than a task that silently never gets created."
    exit 1
  fi

  schtasks //Create //TN "$TASK_NAME" //SC MINUTE //MO "$INTERVAL_MIN" //F \
    //TR "$WLAUNCH" >/dev/null
  say "ARMED: Task Scheduler task '$TASK_NAME', every $INTERVAL_MIN minutes"
  say ""
  say "Log:  $LOGFILE"
  say "Stop: touch $FACTORY_STOP_FILE   (checked before anything else, every tick)"
  say ""
  say "NOTE: a task registered this way runs only while you are logged in unless you"
  say "  reconfigure it to run whether or not the user is logged on. A factory that"
  say "  stops overnight because the session ended looks exactly like one with nothing"
  say "  to do."
}

remove_windows() {
  schtasks //Delete //TN "$TASK_NAME" //F >/dev/null 2>&1 || true
  say "DISARMED: scheduled task $TASK_NAME removed"
}

case "$ACTION" in
  --status)
    say "repo:     $ROOT"
    say "dial:     FACTORY_AUTONOMY=${FACTORY_AUTONOMY:-0}"
    say "interval: every $INTERVAL_MIN minutes"
    say "platform: $PLATFORM"
    say ""
    case "$PLATFORM" in
      linux|macos) status_linux_macos ;;
      windows)     status_windows ;;
      *)           say "unknown platform - install a timer by hand, see references/setup.md" ;;
    esac
    ;;
  --install)
    case "$PLATFORM" in
      linux|macos) install_linux_macos ;;
      windows)     install_windows ;;
      *) say "unknown platform. The line to schedule is:"; say "  $CRON_LINE"; exit 1 ;;
    esac
    ;;
  --remove)
    case "$PLATFORM" in
      linux|macos) remove_linux_macos ;;
      windows)     remove_windows ;;
      *) say "unknown platform - remove the timer by hand" ;;
    esac
    ;;
  *)
    say "usage: bash factory/install-trigger.sh [--status|--install|--remove]"
    exit 2 ;;
esac
