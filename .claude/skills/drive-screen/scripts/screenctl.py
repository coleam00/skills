#!/usr/bin/env python3
"""
screenctl - deterministic screen-control primitives for a coding agent, on any OS.

One file, no third-party packages. Each backend uses what the operating system
already ships: Windows drives user32 through ctypes and shells to PowerShell only
to PNG-encode a capture; macOS uses osascript, screencapture, pbcopy and sips;
Linux/X11 uses xdotool, xclip and maim or ImageMagick.

The one design rule, and the reason this is a checked-in script rather than shell
improvised per run: EVERY action that sends input re-verifies the foreground window
first, and exits non-zero instead of sending. Keystrokes go wherever focus is. An
unverified send during stolen focus types into the wrong application, and by the
time anyone can see that happened, it already has.

  screenctl.py doctor                       # run this FIRST on a new machine
  screenctl.py list
  screenctl.py find   --title "myrepo - Visual Studio Code"
  screenctl.py focus  --title "..."
  screenctl.py shot   --title "..." --out /tmp/a.png
  screenctl.py type   --title "..." --text "claude"
  screenctl.py paste  --title "..." (--file f | --text t)
  screenctl.py key    --title "..." --keys enter
  screenctl.py click  --title "..." --x 850 --y 730 [--double|--right]
  screenctl.py scroll --title "..." --amount -3

Exit codes: 0 ok, 1 refused (not found / ambiguous / focus unconfirmed / bad input).

Every run appends one line per action to ~/.screenctl/actions.log, so a run that
went wrong is inspectable afterwards instead of being reconstructed from memory.
"""

from __future__ import annotations

import argparse
import datetime
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from dataclasses import dataclass

OS = platform.system()  # 'Windows' | 'Darwin' | 'Linux'
LOG = os.path.join(os.path.expanduser("~"), ".screenctl", "actions.log")

# Window titles routinely contain emoji and box-drawing characters. On Windows
# stdout defaults to cp1252 when redirected, and one bullet in a browser tab title
# crashes the whole command. Fix it before anything can print.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", newline="\n")
    except Exception:
        pass


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{stamp}\t{msg}\n")
    except Exception:
        pass  # logging must never be the reason an action fails


def die(code: str, msg: str, extra: list[str] | None = None) -> None:
    """Fail with a stable, machine-readable first token, then prose.

    The caller is a language model. A failure it cannot classify is a failure it
    improvises around, and improvising around a focus failure is exactly how
    keystrokes end up in the wrong window.
    """
    log(f"FAIL {code}: {msg}")
    print(f"{code}: {msg}")
    for line in extra or []:
        print(f"  {line}")
    sys.exit(1)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_utf8(cmd: list[str], **kw) -> str:
    """Run a command and decode its stdout as UTF-8, whatever the locale says.

    `text=True` decodes with the LOCALE encoding. For clipboard contents that is
    silently destructive: measured live on Windows, reading a clipboard holding
    'cafe ★ rocket' through locale decoding returned mojibake for the accent and
    '?' for everything unmappable. Since the clipboard is READ in order to put
    the user's own clipboard back afterwards, that turns a borrowed clipboard
    into a corrupted one.
    """
    return subprocess.run(cmd, capture_output=True, **kw).stdout.decode(
        "utf-8", "replace")


def need(binary: str, install: str) -> str:
    p = shutil.which(binary)
    if not p:
        die("MISSING_TOOL", f"{binary!r} is not installed.", [f"Install it: {install}"])
    return p


@dataclass
class Win:
    id: str          # opaque per-OS handle: printable and comparable
    title: str
    x: int
    y: int
    w: int
    h: int

    @property
    def minimized(self) -> bool:
        # Windows parks minimized windows at -32000,-32000. The geometry looks
        # perfectly valid, so a click computed from it silently goes nowhere.
        return self.x <= -30000 or self.y <= -30000

    def line(self) -> str:
        return (f"{self.id}\t{self.x},{self.y} {self.w}x{self.h}\t{self.title}"
                f"{'  [minimized]' if self.minimized else ''}")


# --------------------------------------------------------------------------
# PNG introspection. Used for two things that both matter.
# --------------------------------------------------------------------------

def png_size(path: str) -> tuple[int, int]:
    """Width and height straight out of the IHDR chunk.

    The captured file is measured rather than predicted, which is what makes the
    coordinate mapping correct on a Retina Mac and on a scaled Windows display
    without either being special-cased: a 800-point-wide window can produce a
    1600-pixel PNG, and only the file knows that.
    """
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return struct.unpack(">II", head[16:24])


def looks_blank(path: str) -> bool:
    """True if the image really is one flat colour.

    macOS returns a black or wallpaper-only screenshot, with a zero exit code,
    when Screen Recording permission is missing. That is the most dangerous
    failure in this whole script: it does not error, it hands back a picture of
    nothing and lets the model reason about it.

    Counting distinct byte values in the FILTERED stream (what this used to do)
    cannot separate that case from a legitimately plain page: a white document
    compresses to almost all zeros too, so every ordinary white page was
    reported as a broken capture. This decodes real pixels from a strip of
    scanlines and asks how many colours are actually on screen.
    """
    try:
        idat, w, colour, depth = bytearray(), 0, 0, 8
        with open(path, "rb") as f:
            f.read(8)
            while chunk := f.read(8):
                if len(chunk) < 8:
                    break
                length, kind = struct.unpack(">I4s", chunk)
                data = f.read(length)
                f.read(4)                      # CRC
                if kind == b"IHDR":
                    w, _h, depth, colour = struct.unpack(">IIBB", data[:10])
                elif kind == b"IDAT":
                    idat += data
                    if len(idat) > 600_000:
                        break
                elif kind == b"IEND":
                    break
        if not idat or depth != 8 or colour not in (2, 6):
            return False
        bpp = 3 if colour == 2 else 4
        stride = w * bpp
        raw = zlib.decompressobj().decompress(bytes(idat), 4_000_000)
        prev = bytearray(stride)
        colours = set()
        for y in range(200):
            off = y * (stride + 1)
            if off + stride + 1 > len(raw):
                break
            ftype = raw[off]
            line = bytearray(raw[off + 1:off + 1 + stride])
            if ftype == 1:
                for i in range(bpp, stride):
                    line[i] = (line[i] + line[i - bpp]) & 0xFF
            elif ftype == 2:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 0xFF
            elif ftype == 3:
                for i in range(stride):
                    left = line[i - bpp] if i >= bpp else 0
                    line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
            elif ftype == 4:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[i] = (line[i] + pr) & 0xFF
            for x in range(0, stride - bpp + 1, bpp * 13):
                colours.add(bytes(line[x:x + bpp]))
                if len(colours) > 1:
                    return False
            prev = line
        return len(colours) <= 1
    except Exception:
        return False       # never block a capture on the checker failing


# ==========================================================================
# Windows
# ==========================================================================

if OS == "Windows":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # MUST run before any measurement. A DPI-unaware process is handed VIRTUALISED
    # coordinates on a scaled display: window rects come back in logical pixels, a
    # capture is a stretched blur, and a coordinate read off that capture maps to
    # the wrong physical point. At 100% scaling nothing changes, which is exactly
    # why this bug ships: it is invisible to whoever wrote it and breaks for
    # everyone on a 4K laptop.
    # https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _title_of(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def list_windows() -> list[Win]:
        out: list[Win] = []

        def cb(hwnd, _l):
            if user32.IsWindowVisible(hwnd) and (t := _title_of(hwnd)):
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                w, h = r.right - r.left, r.bottom - r.top
                if w > 0 and h > 0:
                    out.append(Win(str(int(hwnd)), t, r.left, r.top, w, h))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out

    def foreground_id() -> str:
        return str(int(user32.GetForegroundWindow()))

    def same_window(win: Win) -> bool:
        return foreground_id() == win.id

    def raise_window(win: Win) -> None:
        h = wintypes.HWND(int(win.id))
        user32.ShowWindow(h, 9)          # SW_RESTORE
        user32.SetForegroundWindow(h)

    def unlock_foreground() -> None:
        # Microsoft documents SetForegroundWindow as refusable: a process may only
        # take the foreground under a specific list of conditions, one being that
        # it "received the last input event", and even then "it is possible for a
        # process to be denied the right to set the foreground window".
        # A synthetic ALT tap satisfies that condition. Tried once; if it does not
        # work we stop honestly rather than fight the OS in a loop.
        # https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
        user32.keybd_event(0x12, 0, 0, 0)          # VK_MENU down
        user32.keybd_event(0x12, 0, 0x0002, 0)     # VK_MENU up

    # --- input -----------------------------------------------------------
    # SendInput, not SendKeys. Microsoft's own docs call SendKeys "susceptible to
    # timing issues" and warn it "could yield unpredictable results" on non-US
    # keyboards. It also parses its argument as a mini-language where + ^ % ~ ( )
    # { } [ ] are control characters, so every literal string needs escaping and a
    # miss silently sends a chord instead of text. SendInput with
    # KEYEVENTF_UNICODE sends the character itself and has no grammar to get wrong.
    # https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.sendkeys

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

    _KEYUP, _UNICODE = 0x0002, 0x0004

    VK = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
          "space": 0x20, "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28,
          "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
          "pageup": 0x21, "pagedown": 0x22, "ctrl": 0x11, "shift": 0x10,
          "alt": 0x12, "win": 0x5B, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
          "f5": 0x74, "f6": 0x75, "f11": 0x7A, "f12": 0x7B,
          # Punctuation needs naming. A bare "`" would fall through to ord() below,
          # which is right for letters and digits (VK_A really is ord('A')) and
          # wrong for everything else. Backtick is here because the editor's
          # new-terminal shortcut needs it, and because a backtick inside double
          # quotes is command substitution in most shells, so it has to be
          # spellable as a word anyway.
          "backtick": 0xC0, "grave": 0xC0, "minus": 0xBD, "equals": 0xBB,
          "comma": 0xBC, "period": 0xBE, "slash": 0xBF, "semicolon": 0xBA}

    def _send(evs: list) -> None:
        arr = (_INPUT * len(evs))(*evs)
        user32.SendInput(len(evs), arr, ctypes.sizeof(_INPUT))

    def _key_ev(vk: int, up: bool):
        i = _INPUT(type=1)
        i.u.ki = _KEYBDINPUT(vk, 0, _KEYUP if up else 0, 0, None)
        return i

    def _char_ev(unit: int, up: bool):
        # wScan is a WORD. It carries a UTF-16 CODE UNIT, not a code point.
        i = _INPUT(type=1)
        i.u.ki = _KEYBDINPUT(0, unit, _UNICODE | (_KEYUP if up else 0), 0, None)
        return i

    def _utf16_units(ch: str) -> list[int]:
        """The UTF-16 code units of one character: two for anything astral.

        Passing ord(ch) straight into the 16-bit wScan field silently truncates
        every character above U+FFFF. Measured live: typing a rocket (U+1F680)
        delivered U+F680, a private-use glyph, with no error and no warning.
        Everything in the Basic Multilingual Plane - accents, CJK, symbols - has
        one unit and was always fine, which is exactly why this survived.
        """
        b = ch.encode("utf-16-le")
        return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]

    def type_text(text: str, delay: float = 0.012) -> None:
        # One character per SendInput call, with a delay between them.
        #
        # Batching the whole string into one call is faster and looks correct:
        # SendInput reports every event accepted and sets no error. The
        # characters still arrive wrong. Measured on Windows 11 Notepad, sending
        # 'test+^%~(){}[] 123' as one 36-event batch produced
        # 'test+^%~(333333333' - the first nine characters correct and the rest
        # collapsed onto the last one. The events reach the input queue; the
        # receiving application cannot keep up with them.
        #
        # 12ms matches what xdotool defaults to and what Anthropic's own
        # computer-use reference implementation uses, for the same reason.
        for ch in text:
            # A surrogate pair has to reach the application as two adjacent
            # events or it is not composed back into one character, so the units
            # of a single character go out together. That is at most four events
            # per call, well inside what the corruption above was about.
            evs = []
            for unit in _utf16_units(ch):
                evs += [_char_ev(unit, False), _char_ev(unit, True)]
            _send(evs)
            time.sleep(delay)

    def send_chord(keys: str) -> None:
        parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
        codes = []
        for p in parts:
            if p in VK:
                codes.append(VK[p])
            elif len(p) == 1:
                codes.append(ord(p.upper()))
            else:
                die("BAD_KEY", f"unknown key {p!r} in {keys!r}",
                    ["Known names: " + ", ".join(sorted(VK))])
        _send([_key_ev(c, False) for c in codes] +
              [_key_ev(c, True) for c in reversed(codes)])

    def move_click(x: int, y: int, button: str = "left", double: bool = False) -> None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.12)
        down, up = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}[button]
        for i in range(2 if double else 1):
            user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.06)
            user32.mouse_event(up, 0, 0, 0, 0)
            if i == 0 and double:
                time.sleep(0.05)

    def scroll(win: Win, amount: int) -> None:
        # The wheel goes to the window under the POINTER, not to the focused
        # window. Focusing alone is not enough, and the failure is silent and
        # doubly wrong: the target does not move, and whatever the mouse happens
        # to be sitting over scrolls instead. Measured live, a scroll aimed at a
        # text window went to a window on a different monitor.
        user32.SetCursorPos(win.x + win.w // 2, win.y + win.h // 2)
        time.sleep(0.05)
        user32.mouse_event(0x0800, 0, 0, int(amount) * 120, 0)   # WHEEL

    def get_clipboard() -> str:
        # Deliberately NOT through stdout. PowerShell writes stdout in the
        # console code page and Python decodes it with the locale encoding, so
        # every non-ASCII character comes back wrong: 'cafe' with an acute e
        # became 'caf,' and a star became '?'. That made `paste` refuse valid
        # payloads, and - far worse - made the restore step write mojibake back
        # over whatever the user actually had on their clipboard.
        # A file carries the encoding explicitly and has no console in the path.
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            run(["powershell.exe", "-NoProfile", "-Command",
                 f"Get-Clipboard -Raw | "
                 f"Set-Content -LiteralPath '{path}' -Encoding UTF8 -NoNewline"])
            # Windows PowerShell 5.1 writes a BOM with -Encoding UTF8.
            with open(path, encoding="utf-8-sig") as f:
                return f.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def set_clipboard(text: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(text)
            path = f.name
        try:
            run(["powershell.exe", "-NoProfile", "-Command",
                 f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '{path}')"])
        finally:
            os.unlink(path)

    PASTE_CHORD = "ctrl+v"

    def capture(win: Win, out: str, max_width: int) -> None:
        # PowerShell owns this one step because System.Drawing grabs and
        # PNG-encodes together, and a 200ms process start is nothing next to a
        # once-per-step action.
        w, h = win.w, win.h
        tw = min(w, max_width) if max_width else w
        th = max(1, round(h * tw / w))
        ps = f"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {w}, {h}
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen({win.x}, {win.y}, 0, 0, $bmp.Size)
$g.Dispose()
if ({tw} -ne {w}) {{
  $small = New-Object System.Drawing.Bitmap {tw}, {th}
  $g2 = [System.Drawing.Graphics]::FromImage($small)
  $g2.InterpolationMode = 'HighQualityBicubic'
  $g2.DrawImage($bmp, 0, 0, {tw}, {th})
  $g2.Dispose(); $bmp.Dispose(); $bmp = $small
}}
$bmp.Save('{out}', [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"""
        r = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-Command", ps])
        if r.returncode != 0:
            die("CAPTURE_FAILED", r.stderr.strip()[:300] or "capture failed")


# ==========================================================================
# macOS
# ==========================================================================

elif OS == "Darwin":

    def _osa(script: str, lang: str = "AppleScript"):
        return run(["osascript", "-l", lang, "-e", script])

    # JXA rather than AppleScript: it returns a delimited string in one call, so
    # the whole window list costs one osascript round trip. That matters because
    # each System Events call carries real latency (PyWinCtl documents 400-500ms
    # per call for the same mechanism on Apple Silicon).
    _LIST = r"""
    var out = [];
    var se = Application("System Events");
    var procs = se.applicationProcesses.whose({visible: true});
    for (var i = 0; i < procs.length; i++) {
      var p = procs[i], wins;
      try { wins = p.windows(); } catch (e) { continue; }
      for (var j = 0; j < wins.length; j++) {
        try {
          var pos = wins[j].position(), sz = wins[j].size();
          out.push([p.name() + "#" + j, wins[j].name() || p.name(),
                    pos[0], pos[1], sz[0], sz[1]].join(""));
        } catch (e) {}
      }
    }
    out.join("\n");
    """

    def list_windows() -> list[Win]:
        r = _osa(_LIST, "JavaScript")
        if r.returncode != 0:
            if "-25211" in r.stderr or "assistive" in r.stderr.lower():
                die("NO_ACCESSIBILITY", "System Events is not allowed assistive access.",
                    ["Grant Accessibility to the app that RUNS this command:",
                     "  System Settings > Privacy & Security > Accessibility",
                     "The grant attaches to the host app (Terminal, iTerm, VS Code),",
                     "never to python, and it is dropped when that app updates.",
                     "Then re-run: screenctl.py doctor"])
            die("LIST_FAILED", r.stderr.strip()[:300] or "could not enumerate windows")
        out = []
        for line in r.stdout.splitlines():
            parts = line.split("")
            if len(parts) == 6:
                wid, title, x, y, w, h = parts
                try:
                    out.append(Win(wid, title, int(float(x)), int(float(y)),
                                   int(float(w)), int(float(h))))
                except ValueError:
                    continue
        return out

    def foreground_id() -> str:
        return _osa('tell application "System Events" to get name of first '
                    'application process whose frontmost is true').stdout.strip()

    def same_window(win: Win) -> bool:
        # Identity on macOS is the owning process: AXRaise has already brought the
        # right window of that process to the front.
        return foreground_id() == win.id.rsplit("#", 1)[0]

    def raise_window(win: Win) -> None:
        app, idx = win.id.rsplit("#", 1)
        app = app.replace('"', '\\"')
        _osa(f'tell application "System Events" to tell process "{app}" '
             f'to set frontmost to true')
        _osa(f'tell application "System Events" to tell process "{app}" '
             f'to perform action "AXRaise" of window {int(idx) + 1}')

    def unlock_foreground() -> None:
        pass  # macOS has no foreground lock to defeat

    def type_text(text: str) -> None:
        safe = text.replace("\\", "\\\\").replace('"', '\\"')
        _osa(f'tell application "System Events" to keystroke "{safe}"')

    KEYNAME = {"enter": "return", "return": "return", "esc": "escape",
               "escape": "escape", "tab": "tab", "space": "space",
               "delete": "delete", "backspace": "delete",
               "up": "up arrow", "down": "down arrow",
               "left": "left arrow", "right": "right arrow",
               "pageup": "page up", "pagedown": "page down"}
    # Punctuation that must be spellable as a word: a backtick inside double
    # quotes is command substitution in most shells.
    LITERAL = {"backtick": "`", "grave": "`", "minus": "-", "equals": "=",
               "comma": ",", "period": ".", "slash": "/", "semicolon": ";"}
    MODNAME = {"ctrl": "control down", "control": "control down",
               "shift": "shift down", "alt": "option down",
               "option": "option down", "cmd": "command down",
               "command": "command down", "win": "command down"}

    def send_chord(keys: str) -> None:
        parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
        mods = [MODNAME[p] for p in parts if p in MODNAME]
        rest = [p for p in parts if p not in MODNAME]
        if len(rest) != 1:
            die("BAD_KEY", f"expected exactly one non-modifier key in {keys!r}")
        k = rest[0]
        using = f" using {{{', '.join(mods)}}}" if mods else ""
        if target := KEYNAME.get(k):
            _osa(f'tell application "System Events" to keystroke {target}{using}')
        else:
            lit = LITERAL.get(k, k).replace("\\", "\\\\").replace('"', '\\"')
            _osa(f'tell application "System Events" to keystroke "{lit}"{using}')

    def move_click(x: int, y: int, button: str = "left", double: bool = False) -> None:
        cli = need("cliclick",
                   "brew install cliclick   (macOS ships no coordinate-click CLI)")
        run([cli, f"{'dc' if double else ('rc' if button == 'right' else 'c')}:"
                  f"{int(x)},{int(y)}"])

    def scroll(win: Win, amount: int) -> None:
        # cliclick has no wheel verb, so page keys stand in. Documented rather
        # than silently approximated. `win` is unused because this is a
        # KEYSTROKE: it follows focus and needs no pointer positioning, which is
        # why this backend never had the wheel-goes-to-the-pointer bug.
        send_chord("pageup" if amount > 0 else "pagedown")

    def get_clipboard() -> str:
        # UTF-8 explicitly: locale decoding mangles every non-ASCII character,
        # and this value is written BACK to the user's clipboard afterwards.
        return run_utf8(["pbpaste"])

    def set_clipboard(text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)

    PASTE_CHORD = "cmd+v"

    def capture(win: Win, out: str, max_width: int) -> None:
        # -R takes POINTS. On a Retina display the PNG comes back at 2x those
        # points. Nothing here tries to predict that: act_shot measures the file.
        r = run(["screencapture", "-x", "-o",
                 f"-R{win.x},{win.y},{win.w},{win.h}", out])
        if r.returncode != 0:
            die("CAPTURE_FAILED", r.stderr.strip()[:300] or "screencapture failed",
                ["If this persists, grant Screen Recording to the host app:",
                 "  System Settings > Privacy & Security > Screen Recording"])
        if max_width and png_size(out)[0] > max_width:
            run(["sips", "-Z", str(max_width), out])


# ==========================================================================
# Linux. X11 works; Wayland is refused loudly rather than half-working.
# ==========================================================================

else:
    _WAYLAND = (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
                or bool(os.environ.get("WAYLAND_DISPLAY")))

    def _guard() -> None:
        if _WAYLAND:
            die("WAYLAND_UNSUPPORTED",
                "This is a Wayland session, where one application may not read or "
                "drive another's windows.",
                ["That is a deliberate security property of the protocol, not a",
                 "missing feature, and there is no portable way around it. xdotool",
                 "does not work here at all. Options, in order of least pain:",
                 "  - log into an X11/Xorg session for this work",
                 "  - for terminal-only work use tmux, which needs no screen control",
                 "  - install ydotool (kernel uinput, needs a privileged daemon) for",
                 "    input, plus a compositor-specific tool for windows: swaymsg on",
                 "    sway/Hyprland, kdotool on KDE Plasma 6. GNOME has no good",
                 "    answer short of a Shell extension."])

    def list_windows() -> list[Win]:
        _guard()
        xdo = need("xdotool", "sudo apt install xdotool")
        ids = run([xdo, "search", "--onlyvisible", "--name", ".*"]).stdout.split()
        out = []
        for wid in ids:
            name = run([xdo, "getwindowname", wid]).stdout.strip()
            if not name:
                continue
            g = run([xdo, "getwindowgeometry", "--shell", wid]).stdout
            d = dict(l.split("=", 1) for l in g.splitlines() if "=" in l)
            try:
                out.append(Win(wid, name, int(d["X"]), int(d["Y"]),
                               int(d["WIDTH"]), int(d["HEIGHT"])))
            except (KeyError, ValueError):
                continue
        return out

    def foreground_id() -> str:
        _guard()
        return run([need("xdotool", "sudo apt install xdotool"),
                    "getactivewindow"]).stdout.strip()

    def same_window(win: Win) -> bool:
        return foreground_id() == win.id

    def raise_window(win: Win) -> None:
        # windowactivate, not windowfocus: xdotool's own man page warns some window
        # managers ignore windowfocus. --sync blocks until activation completes
        # rather than racing the next command.
        run([need("xdotool", "sudo apt install xdotool"),
             "windowactivate", "--sync", win.id])

    def unlock_foreground() -> None:
        pass  # GNOME/KDE focus-stealing prevention cannot be defeated from here

    def type_text(text: str) -> None:
        run([need("xdotool", "sudo apt install xdotool"),
             "type", "--clearmodifiers", "--delay", "12", "--", text])

    XK = {"enter": "Return", "return": "Return", "esc": "Escape",
          "escape": "Escape", "tab": "Tab", "space": "space",
          "backspace": "BackSpace", "delete": "Delete", "up": "Up", "down": "Down",
          "left": "Left", "right": "Right", "home": "Home", "end": "End",
          "pageup": "Prior", "pagedown": "Next", "ctrl": "ctrl", "shift": "shift",
          "alt": "alt", "win": "super",
          # Spellable punctuation: a backtick inside double quotes is command
          # substitution in most shells, so it needs a word form.
          "backtick": "grave", "grave": "grave", "minus": "minus",
          "equals": "equal", "comma": "comma", "period": "period",
          "slash": "slash", "semicolon": "semicolon"}

    def send_chord(keys: str) -> None:
        parts = [XK.get(k.strip().lower(), k.strip())
                 for k in keys.split("+") if k.strip()]
        run([need("xdotool", "sudo apt install xdotool"),
             "key", "--clearmodifiers", "+".join(parts)])

    def move_click(x: int, y: int, button: str = "left", double: bool = False) -> None:
        xdo = need("xdotool", "sudo apt install xdotool")
        run([xdo, "mousemove", str(int(x)), str(int(y))])
        run([xdo, "click", "--repeat", "2" if double else "1",
             "3" if button == "right" else "1"])

    def scroll(win: Win, amount: int) -> None:
        xdo = need("xdotool", "sudo apt install xdotool")
        # Buttons 4 and 5 are delivered to the window under the POINTER, so the
        # pointer has to be over the target first or the scroll lands elsewhere.
        run([xdo, "mousemove", str(win.x + win.w // 2), str(win.y + win.h // 2)])
        run([xdo, "click", "--repeat", str(max(1, abs(int(amount)))),
             "4" if amount > 0 else "5"])

    def _clip() -> str:
        return shutil.which("xclip") or need("xsel", "sudo apt install xclip")

    def get_clipboard() -> str:
        t = _clip()
        # -selection clipboard is not optional: X11 has several selections and the
        # default is PRIMARY (middle-click), not the one Ctrl+V reads.
        args = ([t, "-selection", "clipboard", "-o"] if t.endswith("xclip")
                else [t, "--clipboard", "--output"])
        # UTF-8 explicitly: under LANG=C locale decoding would corrupt this, and
        # it is written BACK to the user's clipboard afterwards.
        return run_utf8(args)

    def set_clipboard(text: str) -> None:
        t = _clip()
        args = ([t, "-selection", "clipboard"] if t.endswith("xclip")
                else [t, "--clipboard", "--input"])
        subprocess.run(args, input=text.encode("utf-8"), check=True)

    PASTE_CHORD = "ctrl+v"

    def capture(win: Win, out: str, max_width: int) -> None:
        if m := shutil.which("maim"):
            r = run([m, "-i", win.id, out])
        elif i := shutil.which("import"):
            r = run([i, "-window", win.id, out])
        else:
            die("MISSING_TOOL", "no window screenshot tool found",
                ["Install one: sudo apt install maim   (or imagemagick)"])
        if r.returncode != 0:
            die("CAPTURE_FAILED", r.stderr.strip()[:300] or "capture failed")
        if max_width and png_size(out)[0] > max_width:
            if conv := (shutil.which("magick") or shutil.which("convert")):
                run([conv, out, "-resize", f"{max_width}x", out])


# ==========================================================================
# Shared: resolve, verify, act
# ==========================================================================

def resolve(title: str, wid: str | None = None) -> Win:
    """Return the ONE window matching, or refuse.

    Refusing on ambiguity is the point. Editor titles read
    '<file> - <folder> - <editor>', so 'checkout-service' also matches
    'checkout-service-v2'. Taking the first hit silently drives the wrong window,
    and that only becomes visible after the keystrokes have landed.

    `wid` is the escape hatch for when a title is genuinely unusable: an
    application that renames its own window to something generic mid-run, or two
    windows that really do share a name. A handle is exact and cannot drift, but
    it does not survive the window being closed and reopened, so titles stay the
    default and this is for when they stop working.
    """
    if wid:
        for w in list_windows():
            if w.id == wid:
                return w
        die("NO_SUCH_ID", f"no visible window has id {wid!r}",
            ["Handles change when a window is closed and reopened.",
             "Run `screenctl.py list` for the current ones."])
    if not title:
        die("NO_TITLE", "--title (or --id) is required for this action")
    hits = [w for w in list_windows() if title.lower() in w.title.lower()]
    if not hits:
        die("NOT_FOUND", f"no visible window title contains {title!r}",
            ["Run `screenctl.py list` to see what is actually open."])
    if len(hits) > 1:
        die("AMBIGUOUS", f"{title!r} matches {len(hits)} visible windows. Refusing.",
            [w.line() for w in hits] +
            ["Pass a longer --title that matches exactly one, or pass --id with",
             "the handle from the first column above.",
             # Two windows of the same app routinely carry the SAME title, and
             # then no title is long enough to separate them. Suggesting only a
             # longer title sends the caller looking for something that does not
             # exist.
             "--id is the only way to separate windows whose titles are equal."])
    return hits[0]


def focus(title: str, settle: float = 0.45, wid: str | None = None) -> Win:
    """Focus, then PROVE it by comparing window IDENTITY, not title text.

    Comparing the foreground window's title against the requested substring passes
    whenever some other window happens to share that substring. Resolution above
    has already earned an exact handle, so identity is stricter and free.
    """
    win = resolve(title, wid)
    raise_window(win)
    time.sleep(settle)
    if same_window(win):
        log(f"FOCUS {win.title}")
        print(f"FOCUS_OK: {win.title}")
        return resolve(title, wid)      # re-read geometry after the restore

    unlock_foreground()
    raise_window(win)
    time.sleep(settle)
    if same_window(win):
        log(f"FOCUS(unlock) {win.title}")
        print(f"FOCUS_OK (after unlock): {win.title}")
        return resolve(title, wid)

    fg = next((w for w in list_windows() if w.id == foreground_id()), None)
    die("FOCUS_FAILED",
        f"wanted {win.title!r}, foreground is {(fg.title if fg else 'unknown')!r}.",
        ["Nothing was sent.",
         "A fullscreen or exclusive-mode application (a game, a screen share, a",
         "system dialog) can hold the foreground against every request, by design.",
         "Switch it to windowed mode or close it, then retry."])
    raise AssertionError("unreachable")


# How many characters go out between focus re-checks while typing.
#
# On Windows the check is GetForegroundWindow(), an in-process call costing
# microseconds against a 12ms per-character delay, so it runs before EVERY
# character and the guarantee is exact: no character is sent without focus
# having just been confirmed.
#
# macOS and Linux resolve the foreground by spawning osascript or xdotool, tens
# of milliseconds each, so checking per character would cost more than the
# typing. They check every 20 characters instead, which bounds the exposure at
# roughly a quarter-second of input rather than eliminating it. `paste` has no
# such window on any platform: it is one atomic operation.
TYPE_CHUNK = 1 if OS == "Windows" else 20


def _die_focus_lost(sent: int, total: int) -> None:
    fg = next((w for w in list_windows() if w.id == foreground_id()), None)
    where = f"{(fg.title if fg else 'unknown')!r}"
    # Be precise about what is known. Claiming all `sent` characters landed is
    # the same species of error this guard exists to prevent: on a platform that
    # checks per chunk, focus can move partway THROUGH a chunk, and measured
    # live that lost 9 characters of a 20-character chunk.
    if TYPE_CHUNK == 1:
        landed = [f"All {sent} characters sent reached the target; each one was",
                  "sent with focus confirmed immediately beforehand."]
    else:
        landed = [f"Of the {sent} characters sent, up to the last {TYPE_CHUNK} may",
                  "NOT have reached the target: focus moved during that chunk."]
    die("FOCUS_LOST_MIDSEND",
        f"sent {sent} of {total} characters, then the foreground became {where}.",
        landed +
        [f"The remaining {total - sent} were not sent anywhere.",
         "Screenshot before retrying: re-sending the whole string would",
         "duplicate whatever already landed.",
         "For anything this long, prefer `paste`: it is one atomic operation."])


def act_shot(a) -> None:
    win = focus(a.title, wid=a.id)
    time.sleep(a.settle)      # let the UI settle before capturing it
    capture(win, a.out, a.max_width)
    iw, ih = png_size(a.out)
    if iw == 0:
        die("CAPTURE_FAILED", f"{a.out} is not a readable PNG")
    if looks_blank(a.out):
        print("WARNING: the capture looks like a single flat colour.")
        if OS == "Darwin":
            print("  On macOS that is what a missing Screen Recording grant looks")
            print("  like: it does not error, it returns an empty picture.")
            print("  System Settings > Privacy & Security > Screen Recording")
        print("  Do not reason about this image. Fix the capture first.")
    scale = iw / win.w if win.w else 1.0
    log(f"SHOT {a.out} {iw}x{ih} scale={scale:.4f} win={win.title}")
    print(f"SHOT: {a.out}  {iw}x{ih}")
    print(f"WINDOW_ORIGIN: {win.x},{win.y}    IMAGE_SCALE: {scale:.4f}")
    print("To click what you see at image pixel (px,py), pass:")
    print(f"  --x {win.x} + px/{scale:.4f}    --y {win.y} + py/{scale:.4f}")
    if abs(scale - 1.0) > 0.01:
        print("  The scale is not 1. The image is not in screen pixels; divide.")


def act_type(a) -> None:
    if "\n" in a.text or "\r" in a.text:
        die("NEWLINE_IN_TYPE", "refusing: --text contains a newline.",
            ["In a full-screen terminal UI a newline SUBMITS, so the first line",
             "would be sent as a prompt and the rest typed into whatever follows.",
             "Use `paste` for anything multi-line."])
    win = focus(a.title, wid=a.id)

    # Focus is checked once, before the send. That check goes STALE while a long
    # string is still going out, because typing is a stream of separate events
    # and each one lands wherever the foreground is at that instant.
    #
    # Measured live: a 200-character send with a window stealing focus 1.5s in
    # delivered 92 characters to the target, sent the other 108 somewhere else,
    # and still printed "TYPED 200 chars" and exited 0. A wrong answer reported
    # as success is the worst failure this tool can have, so re-verify between
    # chunks and stop at the first loss.
    #
    # Chunking here rather than inside each backend keeps all three platforms
    # identical and keeps the backend API the same.
    chunks = [a.text[i:i + TYPE_CHUNK] for i in range(0, len(a.text), TYPE_CHUNK)]
    sent = 0
    for n, piece in enumerate(chunks):
        if n and not same_window(win):
            _die_focus_lost(sent, len(a.text))
        type_text(piece)
        sent += len(piece)

    time.sleep(0.25)
    # The last chunk is unverified until now, so the success line below would
    # otherwise be a claim about events nobody confirmed arrived.
    if not same_window(win):
        _die_focus_lost(sent, len(a.text))

    log(f"TYPE {len(a.text)} chars into {a.title!r}")
    print(f"TYPED {len(a.text)} chars (no Enter sent)")


def act_paste(a) -> None:
    if a.file:
        if not os.path.exists(a.file):
            die("NO_FILE", a.file)
        payload = open(a.file, encoding="utf-8").read()
    elif a.text is not None:
        payload = a.text
    else:
        die("NO_PAYLOAD", "paste needs --file or --text")

    # The clipboard belongs to the human. Borrow it and give it back.
    try:
        saved = get_clipboard()
    except Exception:
        saved = None

    set_clipboard(payload)
    time.sleep(0.2)

    def norm(s: str) -> str:
        return s.replace("\r\n", "\n").rstrip("\n")

    # Compare normalised. A round trip through the OS clipboard routinely adds or
    # drops one trailing newline, and a strict compare turns a paste that would
    # have worked into a refusal.
    if norm(get_clipboard()) != norm(payload):
        die("CLIPBOARD_MISMATCH", "the clipboard did not take the payload.",
            ["Nothing was pasted. Retry; if it repeats, another application is",
             "holding the clipboard open."])

    focus(a.title, wid=a.id)
    send_chord(PASTE_CHORD)
    time.sleep(0.6)
    log(f"PASTE {len(payload)} chars into {a.title!r}")
    print(f"PASTED {len(payload)} chars verbatim (no Enter sent)")

    if saved is not None and not a.keep_clipboard:
        try:
            set_clipboard(saved)
            print("CLIPBOARD_RESTORED")
        except Exception:
            print("CLIPBOARD_RESTORE_FAILED (the payload is still on the clipboard)")


def act_click(a) -> None:
    focus(a.title, wid=a.id)
    move_click(a.x, a.y, "right" if a.right else "left", a.double)
    log(f"CLICK {a.x},{a.y} in {a.title!r}")
    print(f"CLICKED {a.x},{a.y}"
          f"{' (double)' if a.double else ''}{' (right)' if a.right else ''}")
    print("Screenshot again before the next click. Any click can move the layout,")
    print("and coordinates from a stale image land somewhere else entirely.")


def act_doctor(a) -> None:
    """Prove the environment works before a run depends on it.

    Almost every first-run failure is a missing permission or a missing binary,
    and on macOS the worst of them returns a blank picture with a zero exit code.
    Naming those up front is the whole difference between a skill that works and
    one that only worked on the machine it was written on.
    """
    print(f"os:      {OS} ({platform.platform()})")
    print(f"python:  {sys.version.split()[0]}")
    print(f"log:     {LOG}")
    ok = True

    if OS == "Windows":
        import ctypes
        u = ctypes.WinDLL("user32")
        aw = u.GetAwarenessFromDpiAwarenessContext(u.GetThreadDpiAwarenessContext())
        print(f"dpi_awareness: {aw}   (2 = per-monitor aware, which is what we want)")
        ok &= (aw == 2)
    elif OS == "Darwin":
        cc = shutil.which("cliclick")
        print(f"cliclick: {cc or 'MISSING - brew install cliclick (needed for click)'}")
        ok &= bool(cc)
    else:
        if _WAYLAND:
            print("session: WAYLAND - screen driving is not supported here")
            ok = False
        else:
            print("session: X11")
        for b in ("xdotool", "xclip"):
            p = shutil.which(b)
            print(f"{b}: {p or 'MISSING'}")
            ok &= bool(p)

    try:
        wins = list_windows()
        print(f"windows_visible: {len(wins)}")
        ok &= len(wins) > 0
    except SystemExit:
        raise
    except Exception as e:
        print(f"windows_visible: FAILED ({e})")
        ok = False

    try:
        before = get_clipboard()
        # Non-ASCII on purpose. An ASCII-only probe passed on a machine where
        # every accented character came back mangled and every symbol came back
        # as '?', because the clipboard was being read through locale decoding.
        # That made `paste` refuse valid payloads and, worse, made the restore
        # step write mojibake over the user's own clipboard. An ASCII probe
        # cannot see any of it. Astral characters are included because they are
        # a surrogate pair and exercise a different path again.
        probe = "screenctl-doctor café ★ 日本語 \U0001F680"
        set_clipboard(probe)
        rt = get_clipboard().strip() == probe
        set_clipboard(before)
        print(f"clipboard_roundtrip: {'ok' if rt else 'FAILED (non-ASCII is corrupted)'}")
        ok &= rt
    except Exception as e:
        print(f"clipboard_roundtrip: FAILED ({e})")
        ok = False

    # A capture of the window that is already frontmost: proves the screenshot
    # path end to end, including the macOS Screen Recording grant, without
    # stealing focus from anything.
    if a.out:
        try:
            fid = foreground_id()
            fw = next((w for w in list_windows() if w.id == fid), None)
            if fw:
                capture(fw, a.out, a.max_width)
                iw, ih = png_size(a.out)
                blank = looks_blank(a.out)
                print(f"screenshot: {a.out} {iw}x{ih}"
                      f"{'  LOOKS BLANK - check Screen Recording permission' if blank else ''}")
                ok &= (iw > 0 and not blank)
            else:
                print("screenshot: skipped (no resolvable foreground window)")
        except SystemExit:
            print("screenshot: FAILED")
            ok = False

    print("DOCTOR_OK" if ok else "DOCTOR_PROBLEMS - fix the lines above before driving")
    sys.exit(0 if ok else 1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["doctor", "list", "find", "focus", "shot",
                                       "type", "paste", "key", "click", "scroll"])
    ap.add_argument("--title")
    ap.add_argument("--id", help="target a window by handle from `list`, for when a title is ambiguous or the app renames its own window")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--keys")
    ap.add_argument("--out")
    ap.add_argument("--x", type=int)
    ap.add_argument("--y", type=int)
    ap.add_argument("--amount", type=int, default=-3)
    ap.add_argument("--settle", type=float, default=1.0,
                    help="seconds to wait after focusing before capturing, so the "
                         "UI has finished animating. Anthropic's own reference "
                         "implementation hardcodes 2.0s for the same reason.")
    ap.add_argument("--max-width", type=int, default=1280,
                    help="downscale the capture to this width (0 = native). "
                         "Anthropic's computer-use guidance puts accuracy 'consistently "
                         "poor' above roughly this size, and a native-resolution window "
                         "costs several times the tokens to read no better.")
    ap.add_argument("--double", action="store_true")
    ap.add_argument("--right", action="store_true")
    ap.add_argument("--keep-clipboard", action="store_true",
                    help="do not restore the user's clipboard after a paste")
    a = ap.parse_args()

    if a.action == "doctor":
        act_doctor(a)
    elif a.action == "list":
        for w in list_windows():
            print(w.line())
    elif a.action == "find":
        print(resolve(a.title, a.id).line())
    elif a.action == "focus":
        focus(a.title, wid=a.id)
    elif a.action == "shot":
        if not a.out:
            die("NO_OUT", "--out is required for shot")
        act_shot(a)
    elif a.action == "type":
        if a.text is None:
            die("NO_TEXT", "--text is required for type")
        act_type(a)
    elif a.action == "paste":
        act_paste(a)
    elif a.action == "key":
        if not a.keys:
            die("NO_KEYS", "--keys is required, e.g. enter, esc, ctrl+shift+p")
        focus(a.title, wid=a.id)
        send_chord(a.keys)
        time.sleep(0.3)
        log(f"KEY {a.keys} into {a.title!r}")
        print(f"SENT: {a.keys}")
    elif a.action == "click":
        if a.x is None or a.y is None:
            die("NO_COORDS", "--x and --y are required for click")
        act_click(a)
    elif a.action == "scroll":
        win = focus(a.title, wid=a.id)
        scroll(win, a.amount)
        log(f"SCROLL {a.amount} in {a.title!r}")
        print(f"SCROLLED {a.amount}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
