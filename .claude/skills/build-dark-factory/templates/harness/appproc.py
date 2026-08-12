"""Reach the software under test. Three shapes cover almost everything.

    http     a server. Started on a dynamic port, polled until it answers.
    cli      a command. Invoked with args; stdout, stderr and exit code asserted.
    library  no process at all. The E2E imports it and calls it.

Chosen by `driver` in `harness.config.json`. Every one of them prints `APP_STARTED`,
because that marker means "the thing under test is reachable" - which is a different
claim for a server than for a library, and equally load-bearing for both.

WHY THIS IS SPLIT OUT. The first version of this file was HTTP-only: urllib, a health
path, a GET and a POST. That made the scaffold silently useless for a CLI, a library, a
batch job or a desktop app - the majority of software - while the surrounding
documentation claimed the plumbing was universal. The process management genuinely IS
universal. The way you talk to the thing is not.

The universal parts, kept in one place because getting them wrong is subtle:

  * a DYNAMIC port, so two laps cannot collide
  * WAIT for an answer rather than sleeping; a sleep is a race you chose to lose
  * FAIL HARD if it never comes up - never degrade to "not testable", which is how a
    crashed app becomes a green run
  * TEAR DOWN on every path including failure, or a leaked process holds the port and
    poisons the next lap
"""
from __future__ import annotations

import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class AppDidNotStart(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _argv(cmd: str) -> list[str]:
    """Split, then resolve argv[0] through PATHEXT.

    Without the resolve, a Windows `.cmd` shim (npm, npx, yarn, pnpm) fails as
    "the system cannot find the file specified" - which reads as "not installed"
    for a tool that is on PATH and works in any terminal.
    """
    parts = shlex.split(cmd, posix=False)
    if parts:
        found = shutil.which(parts[0])
        if found:
            parts[0] = found
    return parts


# --------------------------------------------------------------------------- http
class HttpApp:
    """A server on a dynamic port, polled until healthy."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg.get("http", {})
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "HttpApp":
        cmd = self.cfg.get("start", "").replace("{port}", str(self.port))
        if not cmd:
            raise AppDidNotStart("driver=http but http.start is empty in harness.config.json")
        self.proc = subprocess.Popen(_argv(cmd), cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace")
        self._await_health()
        print(f"APP_STARTED port={self.port}", flush=True)
        return self

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _await_health(self) -> None:
        path = self.cfg.get("health_path", "/health")
        want = self.cfg.get("health_contains", "")
        deadline = time.time() + int(self.cfg.get("boot_timeout_s", 30))
        last = "never answered"
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                out = (self.proc.stdout.read() if self.proc.stdout else "") or ""
                raise AppDidNotStart(
                    f"the app exited with {self.proc.returncode} before answering:\n"
                    f"{out[-1500:]}")
            try:
                status, body, _ = self.get(path)
                if status == 200 and (not want or want in body):
                    return
                last = f"status={status} body={body[:120]!r}"
            except (urllib.error.URLError, OSError) as e:
                last = f"not accepting connections yet ({e})"
            time.sleep(0.2)
        raise AppDidNotStart(
            f"never became healthy in time. Last: {last}. This is a FAILURE, not "
            f"'not testable'.")

    def get(self, path: str, follow: bool = False, headers: dict | None = None):
        """(status, body, headers). `follow=False` so a redirect stays VISIBLE -
        following them by default is how a test of a redirect stops testing it."""
        req = urllib.request.Request(self.base + path, headers=headers or {})

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw):
                return None

        opener = (urllib.request.build_opener()
                  if follow else urllib.request.build_opener(_NoRedirect))
        try:
            with opener.open(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)

    def post(self, path: str, body: str, headers: dict | None = None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body.encode("utf-8"),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


# --------------------------------------------------------------------------- cli
class CliApp:
    """A command-line program. `app.run("--flag value")` returns (rc, stdout, stderr).

    The equivalent of a health check is a smoke invocation: if the binary cannot even
    print its own version, nothing below is worth running.
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg.get("cli", {})

    def __enter__(self) -> "CliApp":
        invoke = self.cfg.get("invoke", "")
        if not invoke:
            raise AppDidNotStart("driver=cli but cli.invoke is empty in harness.config.json")
        rc, out, err = self.run(self.cfg.get("smoke_args", "--help"))
        want = self.cfg.get("smoke_contains", "")
        if rc not in (0, 1) or (want and want not in (out + err)):
            raise AppDidNotStart(
                f"the smoke invocation failed: rc={rc}\n{(out + err)[-1000:]}")
        print("APP_STARTED driver=cli", flush=True)
        return self

    def __exit__(self, *exc) -> None:
        return None

    def run(self, args: str = "", stdin: str = "", timeout: int = 60):
        cmd = self.cfg.get("invoke", "").replace("{args}", args)
        p = subprocess.run(_argv(cmd), cwd=ROOT, input=stdin or None,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""


# --------------------------------------------------------------------------- library
class LibraryApp:
    """No process. The E2E imports the thing and calls it.

    `APP_STARTED` here means it imports at all - which is the same claim as a server
    answering: whatever follows is being asserted against something that loaded.
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg.get("library", {})

    def __enter__(self) -> "LibraryApp":
        check = self.cfg.get("import_check", "")
        if check:
            p = subprocess.run(_argv(check), cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
            if p.returncode != 0:
                raise AppDidNotStart(
                    f"the library does not import:\n{(p.stdout + p.stderr)[-1000:]}")
        sys.path.insert(0, str(ROOT))
        print("APP_STARTED driver=library", flush=True)
        return self

    def __exit__(self, *exc) -> None:
        return None


DRIVERS = {"http": HttpApp, "cli": CliApp, "library": LibraryApp}


def make_driver(cfg: dict):
    name = (cfg.get("driver") or "http").strip().lower()
    if name not in DRIVERS:
        raise AppDidNotStart(
            f"unknown driver {name!r} in harness.config.json - expected one of "
            f"{', '.join(sorted(DRIVERS))}")
    return DRIVERS[name](cfg)
