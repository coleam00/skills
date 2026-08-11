#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Stop hook - the one that gets your attention back.

Fires when the agent finishes its turn, and sends you a native desktop
notification. It never blocks anything (always exits 0). This is the hook that
makes long autonomous runs actually usable: you go do something else, and the
machine tells you when it wants you.

Pair it with `Notification` (fires when the agent is waiting on YOU, not when it
is done) if you want both halves. See hooks/README.md.

Fails OPEN and silent: a notification that will not fire must never interrupt
your work.

============================================================================
EDIT THESE
============================================================================
"""

TITLE = "Claude Code"

# Include the last thing the agent said, trimmed. Set to 0 for title only.
MESSAGE_CHARS = 120

# Terminal bell as well as the OS notification. Cheap, works over SSH, works when
# the notification daemon does not.
RING_BELL = True

# ============================================================================

import json
import platform
import subprocess
import sys


def _quote_for_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _quote_for_powershell(text: str) -> str:
    return text.replace("'", "''")


def notify(title: str, message: str) -> None:
    """Best-effort native notification on Windows, macOS and Linux."""
    system = platform.system()

    if system == "Windows":
        # BurntToast is nicer but is not installed by default. This uses the
        # built-in shell API so it works on a clean machine.
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
            " ContentType=WindowsRuntime] > $null; "
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(1); "
            f"$t.GetElementsByTagName('text').Item(0).AppendChild($t.CreateTextNode('{_quote_for_powershell(title)}')) > $null; "
            f"$t.GetElementsByTagName('text').Item(1).AppendChild($t.CreateTextNode('{_quote_for_powershell(message)}')) > $null; "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code')"
            ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=10,
        )

    elif system == "Darwin":
        script = (
            f'display notification "{_quote_for_applescript(message)}" '
            f'with title "{_quote_for_applescript(title)}"'
        )
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)

    else:
        subprocess.run(["notify-send", title, message], capture_output=True, timeout=10)


def main() -> None:
    try:
        data = json.load(sys.stdin)

        message = "Finished."
        if MESSAGE_CHARS:
            last = (data.get("last_assistant_message") or "").strip().replace("\n", " ")
            if last:
                message = last[:MESSAGE_CHARS] + ("..." if len(last) > MESSAGE_CHARS else "")

        if RING_BELL:
            # stderr, not stdout: on Stop, stdout is parsed for a JSON decision.
            sys.stderr.write("\a")
            sys.stderr.flush()

        try:
            notify(TITLE, message)
        except Exception:
            pass  # no notification daemon, no problem

        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
