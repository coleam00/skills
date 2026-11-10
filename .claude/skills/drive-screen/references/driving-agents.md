# Driving a Claude Code session

How to start agent sessions on someone's machine and steer them from outside, plus
the per-OS setup the primitives depend on. Read this with `SKILL.md`, which holds
the hard rules and the primitive reference.

- [First run, per operating system](#first-run-per-operating-system)
- [Choosing the surface](#choosing-the-surface)
- [Opening the editor on the right folder](#opening-the-editor-on-the-right-folder)
- [Starting a session](#starting-a-session)
- [Sending a prompt](#sending-a-prompt)
- [Waiting, and answering prompts](#waiting-and-answering-prompts)
- [Auditing what the agent actually did](#auditing-what-the-agent-actually-did)
- [Several sessions at once](#several-sessions-at-once)
- [Cleaning up](#cleaning-up)

---

## First run, per operating system

Run `python scripts/screenctl.py doctor --out /tmp/probe.png` first. It fails
loudly for the things that otherwise fail silently.

### Windows

Nothing to install. Two things the script handles that hand-written attempts
usually do not:

- **DPI awareness is declared before anything is measured.** A DPI-unaware process
  is handed virtualised coordinates on a scaled display, so window rectangles,
  captures and cursor positions all quietly disagree with the real screen. At 100%
  scaling nothing changes, which is why this bug survives on the author's machine
  and breaks on everyone else's 4K laptop.
- **Input goes through SendInput, not SendKeys.** Microsoft's own documentation
  calls SendKeys "susceptible to timing issues" and warns against it for
  international keyboards. It also treats `+ ^ % ~ ( ) { } [ ]` as control
  characters, so every literal string needs escaping and a missed escape silently
  sends a chord instead of text.

### macOS

`brew install cliclick` for coordinate clicks. macOS ships no CLI that clicks at a
point; everything else is built in.

Then grant three separate permissions, in System Settings under Privacy & Security.
**They attach to the application that runs the command** - Terminal, iTerm, the
editor, whichever one hosts the agent - never to python, and they are dropped when
that application updates.

| Permission | Needed for | What failure looks like |
|---|---|---|
| Accessibility | Focusing windows, typing, keys | A clear error mentioning assistive access |
| Screen Recording | Capturing any window but your own | **A black or wallpaper-only image, and exit code 0** |
| Automation | The first time you target each app | A one-time prompt naming the target app |

The middle one is the dangerous one. A missing Screen Recording grant does not
error; it hands back a picture of nothing and lets the agent reason about it.
`screenctl.py` checks every capture for being a single flat colour and says so.

Two more macOS facts worth holding: window queries go through the accessibility
tree and cost real time, so avoid re-listing windows in a tight loop; and screen
captures come back at twice the coordinate space on a Retina display, which is why
every `shot` prints its own measured scale instead of assuming one.

### Linux

X11: `sudo apt install xdotool xclip maim`. That is the whole setup, and it is the
best-supported of the three platforms.

Wayland: `screenctl.py` refuses, and says why. One application may not read or
drive another's windows under Wayland; that is the point of the protocol, not a
gap in it, and `xdotool` does not work there at all. The honest options are to use
an X11 session for this work, or to use tmux for anything terminal-shaped and skip
screen control entirely. Piecemeal alternatives exist but are per-compositor:
`ydotool` needs a privileged daemon, `swaymsg` covers sway and Hyprland, `kdotool`
covers KDE Plasma 6, and GNOME has no good answer short of a shell extension.

---

## Choosing the surface

**tmux, when the target is a terminal.** No focus, no keystrokes, no screenshots,
and the human keeps their machine. This should be the default for driving an agent
that does not need to be seen:

```bash
tmux new-session -d -s demo -c /path/to/repo
tmux send-keys -t demo 'claude' Enter
tmux send-keys -t demo 'Refactor the auth module' Enter
tmux capture-pane -t demo -p            # what a human would see
tmux capture-pane -t demo -p -S -1000   # with scrollback
```

**A dedicated terminal window,** when it must be visible and you want a title you
control exactly. This sidesteps editor title collisions entirely:

```bash
wt.exe -w new --title "DEMO-1" -d "C:/path/to/repo"      # Windows Terminal
wezterm cli spawn --new-window --cwd /path/to/repo       # WezTerm, prints a pane id
gnome-terminal --window --title="DEMO-1" --working-directory=/path/to/repo
ghostty --title="DEMO-1" --working-directory=/path/to/repo -e claude
```

Windows Terminal's `--title` is overridden by whatever the running program sets
unless you also pass `--suppressApplicationTitle`. Ghostty is the opposite: setting
`--title` makes it ignore the program's own title sequences.

**Editor integrated terminals,** when it has to look like a real working session on
camera. Several sessions stay visible at once and the window title is stable enough
to target. This is the highest-friction option and the one the traps in `SKILL.md`
are mostly about.

---

## Opening the editor on the right folder

Open the folder itself rather than reusing a window. The folder name then appears
in the title, and new terminals default to that directory.

```bash
code "/path/to/repo"          # opens or focuses
code -r "/path/to/repo"       # reuse the current window
code -n "/path/to/repo"       # force a new window
```

Wait several seconds, then confirm the window exists with `screenctl.py list`
before targeting it.

**The title changes as the active file changes.** `SKILL.md - my-repo - Visual
Studio Code` becomes `README.md - my-repo - Visual Studio Code` the moment another
tab is focused. Target the stable middle segment, the folder name, and make it long
enough to be unique: `checkout-service-v2`, never `checkout-service`.

**The separator differs by platform.** On macOS the default window title joins
segments with an em dash; on Windows and Linux it is a plain hyphen. Match on the
folder name alone rather than on a separator, or pin the format for everyone by
setting `window.title` explicitly in settings.

Re-resolve the window before each step. Do not cache a handle across a long run.

---

## Starting a session

The commands in this reference launch Claude Code. For Codex, use the provider-specific `codex exec --json` workflow in [Driving Codex](driving-codex.md) instead; do not reuse the Claude environment cleanup, session-id flags, or transcript watcher.

```bash
S="scripts/screenctl.py"
T="my-repo - Visual Studio Code"

python $S key   --title "$T" --keys ctrl+shift+backtick   # new terminal
python $S shot  --title "$T" --out /tmp/t1.png            # confirm it opened
```

`Ctrl+Shift+backtick` opens a new integrated terminal on all three platforms,
macOS included: the editor binds the physical Control key there, not Command.

Spell it `backtick`, not `` ` ``. A literal backtick inside double quotes is command
substitution in most shells, and a bare punctuation character has no virtual key
code to map to anyway. The same applies to `minus`, `equals`, `comma`, `period`,
`slash` and `semicolon`.

Then launch, clearing the inherited environment (trap 2 in `SKILL.md`) and
**assigning the session ID up front** rather than discovering it afterwards:

```bash
UUID=$(python -c "import uuid; print(uuid.uuid4())")
python $S paste --title "$T" --text \
  "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_CHILD_SESSION claude --session-id $UUID"
python $S key   --title "$T" --keys enter
```

Knowing the UUID before the session exists removes a whole class of fragility: the
older approach of listing the sessions directory before and after launch and
diffing it picks the wrong session whenever the baseline is empty or another
session writes at the same moment.

Then wait for it to appear on disk rather than sleeping a fixed amount:

```bash
python scripts/session_watch.py dir --repo "/path/to/repo"
```

A missing directory means the terminal's working directory is not what you assumed.
Screenshot and look.

A brand-new project may also show a workspace-trust dialog, and any MCP servers it
declares are approved separately from that. Expect up to two prompts before the
first turn.

---

## Sending a prompt

Always paste, and keep submission separate:

```bash
python $S paste --title "$T" --file "prompts/round-1.md"
python $S shot  --title "$T" --out /tmp/before-submit.png   # read it, then:
python $S key   --title "$T" --keys enter
```

Reading `before-submit.png` before pressing Enter is what stops a mangled or
half-pasted prompt from being submitted and quietly ruining a round.

---

## Waiting, and answering prompts

```bash
python scripts/session_watch.py mark --repo "$REPO" --session "$UUID"
# Submit the prompt, then pass the recorded baseline using wait --since.
python scripts/session_watch.py wait --repo "$REPO" --session "$UUID" --since <MARK> --timeout 900
```

Never estimate with a sleep. Turns run from seconds to many minutes, and a sleep
that is too short means the next keystrokes land mid-turn.

`wait` exits 2 for a quiet state without proven completion. This does not
identify a permission prompt: the agent may be running, thinking, or waiting for
transcript output. Inspect the current UI and actual request before acting.

**Inspect the selected decision before answering.** UI shortcuts and the
highlighted option can vary by provider and version. Use the visible control for
the authorized decision; never infer that Enter means approve-once.

Be deliberate about the "don't ask again" option, because it is not one thing. For
a Bash command it writes a permanent rule into the repository's local settings
file. For a file edit it lasts only until the session ends. Granting the first kind
unattended widens permissions past the end of the task.

For a filmed session, prepare only the permissions already authorized for the
task. A throwaway worktree isolates source edits, not credentials, network access,
or the rest of the machine.

---

## Auditing what the agent actually did

This is the reason to prefer transcripts over screenshots.

```bash
python scripts/session_watch.py reads --repo "$REPO" --since <MARK> --match "CLAUDE.md"
python scripts/session_watch.py reads --repo "$REPO" --all       # include subagents
```

`reads` records recognized transcript tools; it is not a complete file-access
audit. Include startup instructions, supplied context, shell commands, tool
coverage, child agents, and delayed output when interpreting a recall experiment.
An absent file-read event does not prove the model never received the file.

Pass `--all` whenever the driven session might have dispatched subagents. Their
work lands in a `subagents/` subdirectory, not in the parent transcript, so without
it a large part of what happened is simply invisible.

Two things to know about the transcript itself. Its format is explicitly internal
and Anthropic warns it can change in any release, so treat a missing field as a
version difference rather than a failure. And `/compact` keeps the same session and
the same file, condensing it in place; it is `/branch` and `--fork-session` that
create a new one.

---

## Several sessions at once

Terminals inside one editor window are not separately targetable by title, so
switching between them means clicking a tab, and tab positions shift as terminals
come and go. Prefer separate windows with distinct titles whenever sessions must be
driven independently. Title targeting is deterministic; a click at a remembered
coordinate is not.

Each session writes its own transcript in the same project directory. Track them by
the UUID you assigned at launch, not by assuming the newest file is the one you
care about, and pass it to `session_watch.py --session <uuid>`.

---

## Cleaning up

Leave the machine usable. Close only the terminals and windows you opened, restore
whatever was focused at the start, and tell the user the blackout is over and what
state things are in. If you left something running on purpose, say so and say why.
