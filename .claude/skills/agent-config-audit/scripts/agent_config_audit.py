#!/usr/bin/env python3
"""List everything a repo's coding-agent config can run, and flag what looks wrong.

Strictly read-only. Files are only ever opened for reading, nothing found is executed,
and there is no subprocess or network code in this file. Values are redacted by default.

    python agent_config_audit.py                      # the current directory
    python agent_config_audit.py ~/code/some-repo     # one repo, before you open it
    python agent_config_audit.py ~/code               # a folder of repos
    python agent_config_audit.py . --user             # also your user-level agent config
    python agent_config_audit.py . --json             # structured output
    python agent_config_audit.py . --show-values      # print env values and tokens as-is
    python agent_config_audit.py . --history-for .    # also this repo's agent transcripts
    python agent_config_audit.py . --user --history   # the whole machine

WHAT IT READS
-------------
Claude Code   .claude/settings.json, .claude/settings.local.json, .mcp.json,
              plugin hooks/hooks.json, and .claude/{skills,commands,agents}/*.md
Codex         .codex/config.toml, .codex/hooks.json
Cursor        .cursor/hooks.json, .cursor/mcp.json
Gemini CLI    .gemini/settings.json
VS Code       .vscode/tasks.json (runOn: folderOpen), .vscode/mcp.json
Instructions  CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules and friends, checked only
              for invisible characters (text the agent reads and you cannot see)
Dependencies  manifests without a lockfile, pins of known-compromised releases in lockfiles
              and requirements, installed metadata and code-running .pth files in project
              virtualenvs, a .claude/settings.local.json tracked in .git/index, and AI gateway
              config left on the LiteLLM default key
--user        also installed VS Code, Cursor and Windsurf extensions (known-bad versions)
--history     Claude Code and Codex transcripts, for pasted or printed secrets. Only the type,
              the first four characters, the file and the line are ever reported

The inventory lists every hook, MCP server, task, helper command, env var, permission
rule, plugin source and auto-approval setting. Flags are deliberately few: each one is
something a legitimate config rarely needs. No flag does not mean safe; read the list.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None

if __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MAX_BYTES = 2_000_000
REDACTED = "<redacted>"

# (parent directory name, file name) -> agent. "" means "any directory".
TARGETS = {
    (".claude", "settings.json"): "Claude Code",
    (".claude", "settings.local.json"): "Claude Code",
    ("", ".mcp.json"): "Claude Code",
    ("hooks", "hooks.json"): "Claude Code plugin",
    (".codex", "config.toml"): "Codex",
    (".codex", "hooks.json"): "Codex",
    (".cursor", "hooks.json"): "Cursor",
    (".cursor", "mcp.json"): "Cursor",
    (".gemini", "settings.json"): "Gemini CLI",
    (".vscode", "tasks.json"): "VS Code",
    (".vscode", "mcp.json"): "VS Code",
}
CONFIG_DIRS = {".claude", ".codex", ".cursor", ".gemini", ".vscode", "hooks"}

USER_FILES = [
    (".claude/settings.json", "Claude Code (user)"),
    (".claude/settings.local.json", "Claude Code (user)"),
    (".claude.json", "Claude Code (user)"),
    (".codex/config.toml", "Codex (user)"),
    (".codex/hooks.json", "Codex (user)"),
    (".cursor/mcp.json", "Cursor (user)"),
    (".cursor/hooks.json", "Cursor (user)"),
    (".gemini/settings.json", "Gemini CLI (user)"),
]

SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "site-packages",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next", ".nuxt",
    "dist", "build", "target", "vendor", ".cache", ".terraform",
}

# Keys whose value is reported as one inventory entry instead of being descended into.
LEAF_KEYS = {
    "command", "args", "url", "serverUrl", "httpUrl", "headers", "http_headers",
    "env_http_headers", "env", "apiKeyHelper", "headersHelper", "awsAuthRefresh",
    "awsCredentialExport", "otelHeadersHelper", "gcpAuthRefresh", "allow",
    "additionalDirectories", "enableAllProjectMcpServers", "enabledMcpjsonServers",
    "extraKnownMarketplaces", "enabledPlugins", "defaultMode", "runOn", "notify",
    "base_url", "approval_policy", "sandbox_mode", "discoveryCommand", "callCommand",
    "toolDiscoveryCommand", "toolCallCommand", "disableAllHooks", "allowedTools",
}
SERVER_CONTAINERS = {"mcpServers", "mcp_servers", "servers"}
HELPER_KEYS = {"apiKeyHelper", "headersHelper", "awsAuthRefresh", "awsCredentialExport",
               "otelHeadersHelper", "gcpAuthRefresh", "discoveryCommand", "callCommand",
               "toolDiscoveryCommand", "toolCallCommand"}
SECRET_MAPS = {"env", "headers", "http_headers", "env_http_headers"}
RUNNABLE = {"hook", "helper", "statusline", "task", "mcp"}

AGENT_DIRS = {".claude", ".cursor", ".agents", ".codex", ".gemini", ".windsurf", ".clinerules"}
INSTRUCTION_SUBDIRS = {"skills", "commands", "agents", "rules", "prompts", "workflows"}
INSTRUCTION_FILES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "GEMINI.md", ".cursorrules",
                     ".windsurfrules", ".clinerules", "copilot-instructions.md"}

# --------------------------------------------------------------------------- redaction

TOKEN_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_\-]{8,}",
    r"sk-(?:proj-|or-v1-|live_|test_)?[A-Za-z0-9_\-]{16,}",
    r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{10,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"glpat-[A-Za-z0-9_\-]{16,}",
    r"xox[abposre]-[A-Za-z0-9\-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z_\-]{30,}",
    r"npm_[A-Za-z0-9]{30,}",
    r"hf_[A-Za-z0-9]{30,}",
    r"fc-[a-f0-9]{24,}",
    r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]
TOKEN_RE = re.compile("|".join(f"(?:{p})" for p in TOKEN_PATTERNS))
SECRET_NAME = r"[A-Za-z0-9_\-]*?(?:token|secret|passw(?:or)?d|pwd|api[_\-]?key|apikey|access[_\-]?key|private[_\-]?key|credential|auth)[A-Za-z0-9_\-]*"
ASSIGN_RE = re.compile(rf"(?i)\b({SECRET_NAME}[\"']?\s*[=:]\s*[\"']?)([^\s\"'&;,]+)")
FLAG_ARG_RE = re.compile(
    r"(?i)(?<![^\s\"',\[(])(--?(?:api[_\-]?key|token|auth[_\-]?token|access[_\-]?token|secret|password|passwd|key)"
    r"(?:=|\s+|[\"']?\s*,\s*[\"']))([^\s\"',]+)")
URL_USERINFO_RE = re.compile(r"([a-z][a-z0-9+.\-]*://)([^/\s:@\"']+):([^/\s@\"']+)@", re.I)
URL_QUERY_RE = re.compile(
    r"(?i)([?&](?:token|key|api[_\-]?key|apikey|secret|password|auth|sig|signature|access_token|code)=)([^&\s\"'#]+)")
BEARER_RE = re.compile(r"(?i)\b(Bearer|Basic|Token)\s+([A-Za-z0-9._~+/=\-]{8,})")
BLOB_RE = re.compile(r"[A-Za-z0-9+=_\-]{32,}")


def _blob(m: re.Match) -> str:
    s = m.group(0)
    if REDACTED in s:
        return s
    mixed = re.search(r"[a-z]", s) and re.search(r"[A-Z]", s) and re.search(r"\d", s)
    hexish = re.fullmatch(r"[a-f0-9]{32,}", s) or re.fullmatch(r"[A-F0-9]{32,}", s)
    return f"<redacted:{len(s)} chars>" if (mixed or hexish) else s


def redact(text: str, blobs: bool = True) -> str:
    """The one chokepoint every printed string goes through."""
    s = TOKEN_RE.sub(REDACTED, text)
    s = URL_USERINFO_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:{REDACTED}@", s)
    s = URL_QUERY_RE.sub(lambda m: m.group(1) + REDACTED, s)
    s = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", s)
    s = ASSIGN_RE.sub(lambda m: m.group(1) + (m.group(2) if _is_reference(m.group(2)) else REDACTED), s)
    s = FLAG_ARG_RE.sub(lambda m: m.group(1) + (m.group(2) if _is_reference(m.group(2)) else REDACTED), s)
    return BLOB_RE.sub(_blob, s) if blobs else s


REFERENCE_RE = re.compile(
    r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}|\$[A-Za-z_][A-Za-z0-9_]*|\{env:[A-Za-z_][A-Za-z0-9_]*\}|"
    r"\$\{env:[A-Za-z_][A-Za-z0-9_]*\}|%[A-Za-z_][A-Za-z0-9_]*%|<[A-Za-z][A-Za-z0-9 _\-]*>")


def _is_reference(value: str) -> bool:
    """`${VAR}`, `$VAR`, `{env:VAR}`, or a placeholder: names a secret without holding it."""
    v = re.sub(r"(?i)^(?:bearer|basic|token)\s+", "", value.strip().strip("\"'"))
    return (not v or v.startswith(REDACTED) or bool(REFERENCE_RE.fullmatch(v))
            or v.lower() in {"true", "false", "null", "none", "xxx", "changeme", "your-key-here", "bearer", "basic"})


# --------------------------------------------------------------------------- flags

URL_RE = re.compile(r"https?://([^/\s\"'`|;)]+)", re.I)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}
FETCH = r"(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod|fetch|new-object\s+net\.webclient)"
SHELL = r"(?:sudo\s+)?(?:sh|bash|zsh|dash|ksh|python3?|node|perl|ruby|iex|invoke-expression|pwsh|powershell)"

COMMAND_RULES = [
    ("pipe-to-shell", re.compile(rf"(?i)\b{FETCH}\b[^;&\n]*\|\s*{SHELL}\b"),
     "downloads code and pipes it straight into a shell, so what runs is whatever the server sends today"),
    ("pipe-to-shell", re.compile(rf"(?i)\b(?:iex|invoke-expression)\b[\s(]*{FETCH}"),
     "downloads code and executes it in memory (PowerShell iex)"),
    ("download-then-run", re.compile(
        rf"(?i)\b{FETCH}\b.*?(?:\s-o\s|\s-O\b|--output|-outfile|>\s*\S).*?(?:chmod\s+\+x|&&\s*(?:\./|sh\b|bash\b|start\b)|;\s*(?:\./|sh\b|bash\b))"),
     "downloads a file and then runs it"),
    ("encoded-payload", re.compile(
        r"(?i)base64\s+(?:-d|--decode|-D)\b|frombase64string|atob\(|\s-e(?:nc|ncodedcommand)?\s+[A-Za-z0-9+/=]{20,}|"
        r"(?:\\x[0-9a-f]{2}){6,}|[A-Za-z0-9+/]{120,}={0,2}"),
     "decodes or carries an encoded payload, so the command you can read is not the command that runs"),
    ("eval", re.compile(r"(?i)\beval\b\s*[\"'($`]|\$\(\s*(?:curl|wget)\b"),
     "evaluates a string built at runtime"),
    ("hidden-process", re.compile(
        r"(?i)-w(?:indowstyle)?\s+hidden|\bnohup\b|\bdisown\b|\bsetsid\b|\bstart\s+/b\b|\bstart\s+/min\b"),
     "starts a hidden or detached process that keeps running after the agent moves on"),
    ("credential-files", re.compile(
        r"(?i)\.ssh[/\\]|id_rsa|id_ed25519|authorized_keys|\.aws[/\\]|\.git-credentials|\.npmrc|\.pypirc|"
        r"\.docker[/\\]config\.json|login\s+data|keychain|\.claude[/\\]\.credentials|\.codex[/\\]auth\.json"),
     "touches credential files (SSH keys, cloud or registry tokens, agent logins)"),
]
SILENCED_RE = re.compile(r"(?i)>\s*/dev/null|>\s*nul\b|\|\s*out-null|\s-s(?:S|L|f)*\b|--silent|-q\b|--quiet")

REROUTE_ENV = re.compile(
    r"(?i)(?:_BASE_URL|_API_BASE|_API_URL|_ENDPOINT)$|^(?:HTTPS?_PROXY|ALL_PROXY|NODE_OPTIONS|"
    r"NODE_TLS_REJECT_UNAUTHORIZED|PYTHONPATH|PYTHONSTARTUP|LD_PRELOAD|GIT_SSH_COMMAND|BASH_ENV|"
    r"PATH|CLAUDE_CODE_USE_BEDROCK|CLAUDE_CODE_USE_VERTEX)$|^DYLD_")
SECRET_ENV = re.compile(rf"(?i)^{SECRET_NAME}$")
BROAD_ALLOW = re.compile(
    r"(?i)^(?:Bash|Bash\(\s*\*?\s*\)|Bash\(:\*\)|WebFetch|PowerShell|PowerShell\(\*\))$|"
    r"^(?:Bash|PowerShell)\(\s*(?:curl|wget|bash|sh|zsh|python3?|node|npx|bunx|uvx|pwsh|powershell|iex|eval|sudo|ssh|scp|docker|rm)\b[^)]*[*]")


def command_flags(text: str, where: str = "", is_script: bool = False) -> list[dict]:
    out, seen = [], set()
    prefix = f"{where}: " if where else ""
    for rule_id, rx, reason in COMMAND_RULES:
        if rule_id not in seen and rx.search(text):
            seen.add(rule_id)
            out.append({"id": rule_id, "reason": prefix + reason})
    hosts = sorted({h for h in (u.rsplit("@", 1)[-1].lower() for u in URL_RE.findall(text))
                    if h.split(":")[0] not in LOCAL_HOSTS and "{" not in h})
    if is_script and "credential-files" in seen and not hosts:
        # A script that merely names credential paths (a secrets-blocking hook, say) is not a lead.
        out = [f for f in out if f["id"] != "credential-files"]
    if hosts:
        quiet = " with its output silenced" if SILENCED_RE.search(text) else ""
        out.append({"id": "remote-host",
                    "reason": f"{prefix}contacts {', '.join(redact(h) for h in hosts[:3])} every time it runs{quiet}; "
                              "confirm you know why it needs the network"})
    return out


def unpinned_package(command, args) -> str | None:
    """Return the package spec if this MCP launcher pulls an unpinned package from a registry."""
    toks = [str(a) for a in ([command] if command else []) + (args if isinstance(args, list) else [])]
    toks = [t for t in toks if t]
    if not toks:
        return None
    if len(toks) == 1 and " " in toks[0]:
        toks = toks[0].split()
    exe = re.sub(r"\.(cmd|exe|bat)$", "", os.path.basename(toks[0]).lower())
    rest = toks[1:]
    if exe == "cmd" and rest and rest[0].lower() == "/c":
        return unpinned_package(None, rest[1:])
    if exe in ("pnpm", "yarn") and rest[:1] == ["dlx"]:
        kind, rest = "npm", rest[1:]
    elif exe == "pipx" and rest[:1] == ["run"]:
        kind, rest = "py", rest[1:]
    elif exe in ("npx", "bunx", "pnpx"):
        kind = "npm"
    elif exe == "uvx":
        kind = "py"
    else:
        return None
    pkg, it = None, iter(rest)
    for t in it:
        if t in ("--from", "-p", "--package"):
            pkg = next(it, None)
            break
        if t.startswith("-"):
            continue
        pkg = t
        break
    if not pkg or pkg.startswith((".", "/", "~")) or re.match(r"^[A-Za-z]:[\\/]", pkg):
        return None
    if kind == "npm":
        name = pkg[1:] if pkg.startswith("@") else pkg
        ver = name.rsplit("@", 1)[1] if "@" in name else ""
        pinned = bool(re.match(r"\d", ver))
    else:
        pinned = "==" in pkg or bool(re.search(r"@\s*\d", pkg))
    return None if pinned else pkg


# --------------------------------------------------------------------------- parsing

def read_text(path: Path, limit: int = MAX_BYTES) -> str | None:
    """Text file access. Read mode, size-capped."""
    try:
        if path.stat().st_size > limit:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def strip_jsonc(text: str) -> str:
    """Drop // and /* */ comments and trailing commas, respecting strings (VS Code files allow both)."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def parse(path: Path, text: str):
    if path.suffix == ".toml":
        if tomllib is None:
            raise ValueError("tomllib unavailable (Python < 3.11)")
        return tomllib.loads(text)
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(strip_jsonc(text))


def render(value, show: bool, secret_map: bool = False, sep: str = ", ") -> str:
    if isinstance(value, dict) and secret_map:
        parts = []
        for k, v in value.items():
            shown = v if show else (v if _is_reference(str(v)) else REDACTED)
            parts.append(f"{k}={shown if isinstance(shown, str) else json.dumps(shown)}")
        text = "{" + ", ".join(parts) + "}"
    elif isinstance(value, list):
        text = sep.join(str(v) if not isinstance(v, (dict, list)) else json.dumps(v) for v in value)
    else:
        text = value if isinstance(value, str) else json.dumps(value)
    return text if show else redact(text)


def category(path: str, key: str, agent_file: str) -> str:
    if agent_file == "tasks.json":
        return "task"
    if key in HELPER_KEYS:
        return "helper"
    if path.startswith("statusLine"):
        return "statusline"
    if path.startswith("hooks") or ".hooks" in path or key == "notify":
        return "hook"
    if key in ("env",):
        return "env"
    if key in ("enableAllProjectMcpServers", "enabledMcpjsonServers"):
        return "mcp-approval"
    if key in ("extraKnownMarketplaces", "enabledPlugins"):
        return "plugin"
    if key in ("allow", "additionalDirectories", "defaultMode", "approval_policy", "sandbox_mode",
               "disableAllHooks", "allowedTools"):
        return "permission"
    if key == "base_url":
        return "endpoint"
    return "other"


def env_flags(env: dict, show_ctx: str = "") -> list[dict]:
    out = []
    for k, v in env.items():
        sv = "" if v is None else str(v)
        if REROUTE_ENV.search(str(k)):
            host = URL_RE.search(sv)
            to = f" to {redact(host.group(1).rsplit('@', 1)[-1])}" if host else ""
            out.append({"id": "endpoint-override",
                        "reason": f"{show_ctx}sets {k}{to}, which changes where the agent's traffic goes or what code it loads"})
        if sv and not _is_reference(sv) and (SECRET_ENV.match(str(k)) or redact(sv, blobs=False) != sv):
            out.append({"id": "secret-in-config",
                        "reason": f"{show_ctx}{k} holds a literal credential in this file; if it was ever committed, rotate it"})
    return out


class Scanner:
    def __init__(self, show: bool):
        self.show = show

    def item(self, cat, path, value, flags, key=""):
        sep = " " if key in ("command", "args", "notify") else ", "
        return {"category": cat, "path": redact(path),
                "value": render(value, self.show, key in SECRET_MAPS, sep), "flags": flags}

    def scripts_in(self, text: str, base: Path, root: Path) -> list[dict]:
        """Read local scripts a command points at (inside the scanned root only) and flag them too."""
        out = []
        cleaned = re.sub(r"\$\{?(?:CLAUDE_PROJECT_DIR|workspaceFolder|PWD)\}?[/\\]?", "", text)
        for tok in re.findall(r"[\w.\-/\\]+\.(?:sh|bash|ps1|py|js|mjs|cjs|ts|bat|cmd|rb|pl)\b", cleaned):
            tok = tok.lstrip("/\\")
            for cand in ((base / tok), (root / tok)):
                try:
                    p = cand.resolve()
                    p.relative_to(root.resolve())
                except (ValueError, OSError):
                    continue
                if p.is_file():
                    body = read_text(p)
                    if body:
                        rel = p.relative_to(root.resolve()).as_posix()
                        out += command_flags(body, f"its script {rel}", is_script=True)
                    break
        return out

    def server(self, path: str, name: str, cfg, base: Path, root: Path) -> dict:
        if not isinstance(cfg, dict):
            return self.item("mcp", f"{path}.{name}", cfg, [])
        flags = []
        cmd, args = cfg.get("command"), cfg.get("args") or []
        line = " ".join(str(x) for x in ([cmd] if cmd else []) + (args if isinstance(args, list) else [args]))
        shown = {}
        if line:
            shown["run"] = line
        for k in ("url", "serverUrl", "httpUrl", "type", "transport"):
            if cfg.get(k):
                shown[k] = cfg[k]
        pkg = unpinned_package(cmd, args)
        if pkg:
            flags.append({"id": "unpinned-package", "reason":
                          f"runs {redact(pkg)} from the registry at whatever version is newest, so a new release changes what runs"})
        if line:
            flags += [f for f in command_flags(line) if f["id"] != "remote-host"]
            flags += self.scripts_in(line, base, root)
        text = " ".join(f"{k}: {v}" for k, v in shown.items())
        for mk in SECRET_MAPS:
            m = cfg.get(mk)
            if isinstance(m, dict) and m:
                flags += env_flags(m) if mk == "env" else []
                if mk != "env":
                    for hk, hv in m.items():
                        hv = "" if hv is None else str(hv)
                        credential_like = (SECRET_ENV.match(str(hk)) or str(hk).lower() == "cookie"
                                           or redact(hv, blobs=False) != hv)
                        if hv and credential_like and not _is_reference(hv):
                            flags.append({"id": "secret-in-config",
                                          "reason": f"header {hk} holds a literal value in this file; if it is a credential and was committed, rotate it"})
                text += f" {mk}: {render(m, self.show, True)}"
        val = text if self.show else redact(text)
        return {"category": "mcp", "path": redact(f"{path}.{name}"), "value": val, "flags": flags}

    def task(self, path: str, t, base: Path, root: Path) -> dict:
        if not isinstance(t, dict):
            return self.item("task", path, t, [])
        parts = []
        for scope in (t, t.get("windows") or {}, t.get("linux") or {}, t.get("osx") or {}):
            cmd, args = scope.get("command", ""), scope.get("args") or []
            parts.append(" ".join(str(x) for x in [cmd] + (args if isinstance(args, list) else [args]) if x))
        line = " ; ".join(x for x in parts if x)
        run_on = (t.get("runOptions") or {}).get("runOn", "")
        flags = []
        if run_on == "folderOpen":
            flags.append({"id": "runs-on-open",
                          "reason": "runs automatically when the folder is opened in VS Code or Cursor"})
        flags += command_flags(line) + self.scripts_in(line, base, root)
        label = t.get("label", "")
        val = f"[{label}] {line}" + (f"  (runOn: {run_on})" if run_on else "")
        return {"category": "task", "path": redact(path), "value": val if self.show else redact(val), "flags": flags}

    def walk(self, obj, fname: str, base: Path, root: Path, path: str = ""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else str(k)
                if k in SERVER_CONTAINERS and isinstance(v, dict) and fname != "tasks.json":
                    for name, cfg in v.items():
                        yield self.server(p, name, cfg, base, root)
                elif k == "tasks" and fname == "tasks.json" and isinstance(v, list):
                    for i, t in enumerate(v):
                        yield self.task(f"{p}[{i}]", t, base, root)
                elif k in LEAF_KEYS:
                    if v in ([], {}, "", None):
                        continue
                    yield self.leaf(p, k, v, fname, base, root)
                else:
                    yield from self.walk(v, fname, base, root, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from self.walk(v, fname, base, root, f"{path}[{i}]")

    def leaf(self, p, k, v, fname, base, root) -> dict:
        cat = category(p, k, fname)
        flags: list[dict] = []
        raw = v if isinstance(v, str) else " ".join(map(str, v)) if isinstance(v, list) else json.dumps(v)
        if cat in RUNNABLE and k not in SECRET_MAPS:
            flags += command_flags(raw) + self.scripts_in(raw, base, root)
        if k in SECRET_MAPS and isinstance(v, dict):
            flags += env_flags(v)
        if k == "enableAllProjectMcpServers" and v is True:
            flags.append({"id": "auto-approve-mcp", "reason":
                          "approves every MCP server any .mcp.json in the project declares, including ones added by a later pull"})
        if k == "defaultMode" and str(v) == "bypassPermissions":
            flags.append({"id": "bypass-permissions", "reason": "the agent runs every tool without asking"})
        if k == "approval_policy" and str(v) == "never":
            flags.append({"id": "bypass-permissions", "reason": "Codex never asks before running commands"})
        if k == "sandbox_mode" and str(v) == "danger-full-access":
            flags.append({"id": "bypass-permissions", "reason": "Codex runs with the sandbox off"})
        if k == "disableAllHooks" and v is False and fname != "settings.local.json":
            flags.append({"id": "hooks-reenabled", "reason":
                          "explicitly turns hooks back on, which overrides a user who turned them off"})
        if k == "base_url" and isinstance(v, str):
            flags.append({"id": "endpoint-override", "reason": "points a model provider at a custom endpoint"})
        if k in ("allow", "allowedTools") and isinstance(v, list):
            for rule in v:
                r = str(rule)
                if BROAD_ALLOW.search(r.strip()):
                    flags.append({"id": "broad-allow", "reason":
                                  f"{redact(r)} lets the agent run that without asking"})
                if redact(r, blobs=False) != r:
                    flags.append({"id": "secret-in-config", "reason":
                                  "an allow rule contains what looks like a credential (approved commands are saved verbatim); rotate it"})
        if k in ("extraKnownMarketplaces",):
            flags.append({"id": "plugin-source", "reason":
                          "adds a plugin marketplace; plugins can ship their own hooks and MCP servers"})
        if cat not in ("env",) and k not in SECRET_MAPS and redact(raw, blobs=False) != raw and \
                not any(f["id"] == "secret-in-config" for f in flags):
            flags.append({"id": "secret-in-config", "reason":
                          "contains what looks like a credential written into the file; if it was committed, rotate it"})
        return self.item(cat, p, v, flags, k)


# --------------------------------------------------------------------------- driving

HIDDEN_RE = re.compile("[\u200b\u202a-\u202e\u2061-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
# Emoji flag sequences legitimately use tag characters after a black flag; drop those first.
FLAG_EMOJI_RE = re.compile("\U0001f3f4[\U000e0020-\U000e007f]+")
INLINE_SHELL_RE = re.compile(r"!`|^\s*```!|^hooks:|^\s*allowed-tools:")


def repo_base(path: Path) -> Path:
    return path.parent.parent if path.parent.name in CONFIG_DIRS else path.parent


def match_target(path: Path) -> str | None:
    return TARGETS.get((path.parent.name, path.name)) or TARGETS.get(("", path.name))


def scan_config(path: Path, agent: str, root: Path, scanner: Scanner, display: str) -> dict:
    rec = {"path": display, "agent": agent, "items": []}
    text = read_text(path)
    if text is None:
        rec["items"].append({"category": "unreadable", "path": "", "value": "",
                             "flags": [{"id": "unreadable", "reason": "could not read (too large or no access); inspect by hand"}]})
        return rec
    try:
        data = parse(path, text)
    except ValueError:
        rec["items"].append({"category": "unparsed", "path": "", "value": "",
                             "flags": [{"id": "unparsed", "reason": "could not parse; read it by hand (a broken file can still run)"}]})
        return rec
    rec["items"] = list(scanner.walk(data, path.name, repo_base(path), root))
    return rec


def is_instruction(path: Path, parts: tuple) -> bool:
    if path.name in INSTRUCTION_FILES:
        return True
    if path.suffix not in (".md", ".mdc"):
        return False
    # Only files an agent loads as instructions: skills, commands, agents and rules folders.
    for i, d in enumerate(parts[:-1]):
        if d in AGENT_DIRS and i + 1 < len(parts) - 1 and parts[i + 1] in INSTRUCTION_SUBDIRS:
            return True
    return False


def scan_markdown(path: Path, rel: str, scanner: Scanner) -> dict | None:
    # This skill's own docs describe the patterns it looks for, so they would flag themselves.
    if re.search(r"(^|/)agent-config-audit/", rel.replace("\\", "/")):
        return None
    text = read_text(path)
    if not text:
        return None
    lines, flags = [], []
    hidden = len(HIDDEN_RE.findall(FLAG_EMOJI_RE.sub("", text.lstrip("\ufeff"))))
    if hidden:
        flags.append({"id": "hidden-characters", "reason":
                      f"{hidden} invisible character(s): text the agent reads and you cannot see on screen"})
    in_skill_dir = re.search(r"(^|/)\.claude/(skills|commands|agents)/", rel)
    if in_skill_dir:
        for n, line in enumerate(text.splitlines(), 1):
            if INLINE_SHELL_RE.search(line):
                shown = (line.strip() if scanner.show else redact(line.strip()))[:160]
                lf = command_flags(line)
                if re.search(r"allowed-tools:.*\bBash\b(?!\()", line):
                    lf.append({"id": "broad-allow", "reason": "grants unrestricted shell while the skill is active"})
                lines.append({"line": n, "text": shown if scanner.show else redact(shown), "flags": lf})
                flags += lf
    if not lines and not flags:
        return None
    return {"path": rel, "lines": lines, "flags": flags}


# --------------------------------------------------------------------------- dependencies

HOME: Path | None = None  # tests point this at a fake home directory


def home_dir() -> Path:
    return HOME or Path.home()


# Releases known to carry malware. (ecosystem, normalized name, versions, what happened)
KNOWN_COMPROMISED = [
    ("pypi", "agent-framework", {"1.26.1", "1.26.2"},
     "Microsoft agent-framework releases that shipped a .pth credential stealer (2026-11-17)"),
]
MANIFESTS = {"package.json": "npm", "pyproject.toml": "pypi", "Pipfile": "pypi", "Cargo.toml": "cargo",
             "go.mod": "go", "Gemfile": "rubygems"}
REQUIREMENTS_RE = re.compile(r"(?i)^requirements[\w.\-]*\.txt$")
LOCKFILES = {"package-lock.json": "npm", "npm-shrinkwrap.json": "npm", "pnpm-lock.yaml": "npm", "yarn.lock": "npm",
             "bun.lock": "npm", "bun.lockb": "npm", "uv.lock": "pypi", "poetry.lock": "pypi", "pdm.lock": "pypi",
             "Pipfile.lock": "pypi", "Cargo.lock": "cargo", "go.sum": "go", "Gemfile.lock": "rubygems"}
LOCK_NAMES = {"npm": "package-lock.json, pnpm-lock.yaml, yarn.lock or bun.lock",
              "pypi": "uv.lock, poetry.lock, Pipfile.lock or fully pinned requirements",
              "cargo": "Cargo.lock", "go": "go.sum", "rubygems": "Gemfile.lock"}
LOCK_MAX_BYTES = 60_000_000
# .pth files that ship with ordinary tooling. Any other .pth that runs code is a lead.
WELL_KNOWN_PTH = re.compile(
    r"(?i)^(?:distutils-precedence|_virtualenv|easy-install|setuptools|pywin32|virtualenv_path_extensions|"
    r"a1_coverage|coverage|matplotlib|_distutils_hack|__editable__\..*|.*-nspkg)\.pth$")
GATEWAY_FILE_RE = re.compile(
    r"(?i)^(?:docker-)?compose[\w.\-]*\.ya?ml$|^\.env\.(?:example|sample|template|dist)$|litellm[\w.\-]*\.ya?ml$|^config\.ya?ml$")
GATEWAY_KEY_RE = re.compile(r"(?<![\w\-])sk-1234\d*(?![\w\-])")
GATEWAY_HINT_RE = re.compile(r"(?i)litellm|master[_\-]?key")


def norm_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _name_re(name: str) -> re.Pattern:
    body = r"[-_.]".join(re.escape(p) for p in name.split("-"))
    return re.compile(rf"(?i)(?<![\w.\-/]){body}(?![\w\-]|\.\w)")


def _ver_re(v: str) -> re.Pattern:
    return re.compile(rf"(?<![\w.]){re.escape(v)}(?![\w.]|\.\d)")


def compromised_in_text(text: str, eco: str, mode: str) -> list[str]:
    """Known-bad name+version pins in a lockfile or requirements text. mode: line | block."""
    hits = []
    for e, name, versions, _ in KNOWN_COMPROMISED:
        if e != eco:
            continue
        for m in _name_re(name).finditer(text):
            window = text[m.end(): m.end() + 400]
            for v in versions:
                ev = re.escape(v)
                exact = [
                    rf"\s*(?:\[[^\]\n]*\])?\s*===?\s*{ev}(?![\w.])",          # requirements, pyproject: ==1.26.1
                    rf"[@/]{ev}(?![\w.])",                                      # pnpm, bun, npm keys: @1.26.1
                ]
                if mode == "block":
                    exact += [
                        rf"[\"']?\s*\r?\n\s*version\s*=\s*[\"']{ev}[\"']",     # TOML locks: name, then version
                        rf"@[^\n]*:\s*\r?\n\s+version:?\s+[\"']?{ev}(?![\w.])",  # yarn: header, then version
                    ]
                if any(re.match(p, window) for p in exact):
                    hits.append(f"{name} {v}")
    return sorted(set(hits))


def compromised_in_json_lock(text: str, eco: str) -> list[str]:
    """package-lock.json, npm-shrinkwrap.json, node_modules/.package-lock.json, Pipfile.lock."""
    try:
        data = json.loads(text)
    except ValueError:
        return compromised_in_text(text, eco, "block")
    found = []
    entries = []
    if isinstance(data, dict):
        for key in ("packages", "dependencies"):
            for k, v in (data.get(key) or {}).items() if isinstance(data.get(key), dict) else []:
                if isinstance(v, dict):
                    entries.append((k.rsplit("node_modules/", 1)[-1], str(v.get("version", ""))))
        for key in ("default", "develop"):
            for k, v in (data.get(key) or {}).items() if isinstance(data.get(key), dict) else []:
                if isinstance(v, dict):
                    entries.append((k, str(v.get("version", "")).lstrip("=")))
    for e, name, versions, _ in KNOWN_COMPROMISED:
        if e == eco:
            found += [f"{name} {ver}" for n, ver in entries if norm_name(n) == name and ver in versions]
    return sorted(set(found))


def compromised_flag(file_label: str, hits: list[str]) -> dict:
    notes = {f"{n} {v}": why for _, n, vs, why in KNOWN_COMPROMISED for v in vs}
    why = "; ".join(sorted({notes.get(h, "") for h in hits} - {""}))
    return {"id": "known-compromised", "reason":
            f"{file_label} pins {', '.join(hits)}: {why}. Remove it, and rotate every key this machine could reach "
            "if it was ever installed"}


def requirements_unpinned(text: str) -> int:
    n = 0
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            n += 1
    return n


def has_dependencies(path: Path, text: str | None) -> bool:
    if text is None:
        return True
    name = path.name
    try:
        if name == "package.json":
            d = json.loads(text)
            return any(isinstance(d.get(k), dict) and d.get(k)
                       for k in ("dependencies", "devDependencies", "optionalDependencies"))
        if name == "pyproject.toml":
            if tomllib is None:
                return True
            d = tomllib.loads(text)
            proj = d.get("project") or {}
            poetry = ((d.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            return bool(proj.get("dependencies") or proj.get("optional-dependencies") or d.get("dependency-groups")
                        or [k for k in poetry if k != "python"])
        if name == "Cargo.toml":
            if tomllib is None:
                return True
            d = tomllib.loads(text)
            return bool(d.get("dependencies") or d.get("dev-dependencies") or d.get("workspace"))
        if name == "go.mod":
            return bool(re.search(r"(?m)^\s*require\b", text))
    except (ValueError, AttributeError):
        return True
    return True


def read_bytes(path: Path, limit: int) -> bytes | None:
    """Binary read, size-capped. Used only for .git/index."""
    try:
        if path.stat().st_size > limit:
            return None
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def git_index_path(repo: Path) -> Path | None:
    dotgit = repo / ".git"
    if dotgit.is_dir():
        return dotgit / "index"
    if dotgit.is_file():
        text = read_text(dotgit, 10_000) or ""
        m = re.match(r"\s*gitdir:\s*(.+?)\s*$", text)
        if m:
            gd = Path(m.group(1))
            return (gd if gd.is_absolute() else repo / gd) / "index"
    return None


def site_packages(venv: Path) -> list[Path]:
    out = []
    if (venv / "Lib" / "site-packages").is_dir():
        out.append(venv / "Lib" / "site-packages")
    try:
        for d in os.listdir(venv / "lib"):
            if d.startswith("python") and (venv / "lib" / d / "site-packages").is_dir():
                out.append(venv / "lib" / d / "site-packages")
    except OSError:
        pass
    return out


def scan_venv(venv: Path, label: str) -> list[dict]:
    """Installed metadata of known-bad releases, and .pth files that run code at every Python start."""
    flags = []
    pypi_names = {n.replace("-", "_") for e, n, _, _ in KNOWN_COMPROMISED if e == "pypi"}
    for sp in site_packages(venv):
        try:
            entries = os.listdir(sp)
        except OSError:
            continue
        for e in entries:
            low = e.lower()
            if low.endswith(".dist-info") and any(low.startswith(n) for n in pypi_names):
                meta = read_text(sp / e / "METADATA", 5_000_000) or ""
                name = re.search(r"(?m)^Name:\s*(\S+)", meta)
                ver = re.search(r"(?m)^Version:\s*(\S+)", meta)
                if name and ver:
                    for eco, n, vs, _ in KNOWN_COMPROMISED:
                        if eco == "pypi" and norm_name(name.group(1)) == n and ver.group(1) in vs:
                            flags.append(compromised_flag(f"{label} (installed)", [f"{n} {ver.group(1)}"]))
            elif low.endswith(".pth") and not WELL_KNOWN_PTH.match(e):
                body = read_text(sp / e, 5_000_000) or ""
                if re.search(r"(?m)^\s*import[\s;]", body):
                    flags.append({"id": "suspicious-pth", "reason":
                                  f"{label}: {e} is not a standard .pth file and runs code every time Python starts in "
                                  "this environment (the agent-framework stealer used this trick). Read it by hand"})
    return flags


def scan_projects(root: Path, walked: list) -> list[dict]:
    """Dependency, venv, git-index and gateway-key checks over the directories scan_root walked."""
    projects: dict[str, dict] = {}
    locks_by_dir: dict[Path, set] = {}
    manifests: list[tuple[Path, str]] = []

    def proj(d: Path) -> dict:
        rel = d.relative_to(root).as_posix() if d != root else "."
        return projects.setdefault(rel, {"path": rel, "manifests": [], "lockfiles": [], "venvs": 0, "flags": []})

    for here, dirnames_all, filenames in walked:
        for d in dirnames_all:
            sub = here / d
            if (sub / "pyvenv.cfg").is_file():
                p = proj(here)
                p["venvs"] += 1
                p["flags"] += scan_venv(sub, (sub.relative_to(root).as_posix()))
        if ".git" in dirnames_all or ".git" in filenames:
            idx = git_index_path(here)
            data = read_bytes(idx, 200_000_000) if idx else None
            if data and b".claude/settings.local.json\x00" in data:
                proj(here)["flags"].append({"id": "local-settings-tracked", "reason":
                    ".claude/settings.local.json is tracked by git, so every command approved with \"don't ask again\" "
                    "(secrets included) is pushed with the repo"})
        if "node_modules" in dirnames_all:
            hidden_lock = here / "node_modules" / ".package-lock.json"
            text = read_text(hidden_lock, LOCK_MAX_BYTES) if hidden_lock.is_file() else None
            hits = compromised_in_json_lock(text, "npm") if text else []
            if hits:
                proj(here)["flags"].append(compromised_flag("node_modules (installed)", hits))
        for f in filenames:
            p = here / f
            rel = p.relative_to(root).as_posix()
            if f in LOCKFILES:
                eco = LOCKFILES[f]
                locks_by_dir.setdefault(here, set()).add(eco)
                proj(here)["lockfiles"].append(f)
                if f == "bun.lockb":
                    continue
                text = read_text(p, LOCK_MAX_BYTES)
                if text:
                    hits = (compromised_in_json_lock(text, eco) if f.endswith(".json") or f == "Pipfile.lock"
                            else compromised_in_text(text, eco, "line" if f == "bun.lock" else "block"))
                    if hits:
                        proj(here)["flags"].append(compromised_flag(rel, hits))
            elif f in MANIFESTS:
                manifests.append((p, MANIFESTS[f]))
                proj(here)["manifests"].append(f)
                if f in ("pyproject.toml", "Pipfile"):
                    text = read_text(p)
                    hits = compromised_in_text(text or "", "pypi", "line")
                    if hits:
                        proj(here)["flags"].append(compromised_flag(rel, hits))
            elif REQUIREMENTS_RE.match(f):
                text = read_text(p) or ""
                proj(here)["manifests"].append(f)
                hits = compromised_in_text(text, "pypi", "line")
                if hits:
                    proj(here)["flags"].append(compromised_flag(rel, hits))
                loose = requirements_unpinned(text)
                if loose:
                    manifests.append((p, "pypi-req"))
                else:
                    locks_by_dir.setdefault(here, set()).add("pypi")
            if GATEWAY_FILE_RE.match(f):
                text = read_text(p) or ""
                if GATEWAY_KEY_RE.search(text) and GATEWAY_HINT_RE.search(text):
                    proj(here)["flags"].append({"id": "default-gateway-key", "reason":
                        f"{rel} sets an AI gateway key to the documented LiteLLM default (sk-1234). Anyone who can reach "
                        "the gateway can spend through it; set a long random key"})

    for path, eco in manifests:
        kind = "pypi" if eco == "pypi-req" else eco
        d, covered = path.parent, False
        while True:
            if kind in locks_by_dir.get(d, set()):
                covered = True
                break
            if d == root or root not in d.parents:
                break
            d = d.parent
        if covered:
            continue
        text = read_text(path)
        if eco != "pypi-req" and not has_dependencies(path, text):
            continue
        rel = path.relative_to(root).as_posix()
        extra = f" ({requirements_unpinned(text or '')} unpinned line(s))" if eco == "pypi-req" else ""
        proj(path.parent)["flags"].append({"id": "no-lockfile", "reason":
            f"{rel} has dependencies but no lockfile{extra} (expected {LOCK_NAMES[kind]}), so every install takes "
            "the newest release; that is how a poisoned release reaches you"})
    return [p for p in projects.values() if p["manifests"] or p["flags"] or p["venvs"] or p["lockfiles"]]


# --------------------------------------------------------------------------- history

HISTORY_RULES = [
    ("anthropic", r"sk-ant-[A-Za-z0-9_\-]{40,}"),  # real keys run ~100 chars; shorter is a fragment or a fake
    ("openrouter", r"sk-or-v1-[A-Za-z0-9]{32,}"),
    ("openai", r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{32,}"),
    ("github", r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}"),
    ("aws", r"AKIA[0-9A-Z]{16}"),
    ("slack", r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    ("google", r"AIza[0-9A-Za-z_\-]{35}"),
    ("stripe", r"(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
    ("private-key", r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?:\\n|\\r|\s)+[A-Za-z0-9+/=]{40,}"),
    ("jwt", r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("bearer", r"Bearer\s+[A-Za-z0-9._~+/\-]{30,}=*"),
]
HISTORY_RE = re.compile(r"(?:(?<![A-Za-z0-9_\-])|(?<=\\[nrt]))(?:" + "|".join(f"(?P<{t.replace('-', '_')}>{p})" for t, p in HISTORY_RULES) + ")")
SPECIFIC_RE = {t: re.compile(p) for t, p in HISTORY_RULES if t != "bearer"}
# Transcripts are large, so lines are scanned as bytes: one cheap pass for where a token could
# start, then the full patterns only at those spots.
HISTORY_RE_B = re.compile(HISTORY_RE.pattern.encode())
CANDIDATE_RE_B = re.compile(rb"sk-|[sr]k_live_|gh[pousr]_|github_pat_|AKIA|xox[abprs]-|AIza|-----BEGIN|Bearer\s|eyJ")
PLACEHOLDER_RE = re.compile(r"(?i)xxxx|your|example|dummy|placeholder|redacted|0000000|1234567|abcdefgh")
TIMESTAMP_RE = re.compile(rb'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2})')


def find_secrets(line: bytes):
    end = 0
    for c in CANDIDATE_RE_B.finditer(line):
        if c.start() < end:
            continue
        m = HISTORY_RE_B.match(line, c.start())
        if m:
            end = m.end()
            yield m
MAX_LINE = 4_000_000
MAX_LIST = 25


def mangle(path: str) -> str:
    """How Claude Code names a project's transcript folder: every non-alphanumeric character becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def folder_matches(name: str, prefix: str) -> bool:
    n, p = name.lower(), prefix.lower().rstrip("-")
    return n == p or n.startswith(p + "-")


def _classify(kind: str, value: str) -> tuple[str, str] | None:
    """Return (type, secret) for a hit, or None if it looks like a placeholder."""
    if kind == "bearer":
        value = re.sub(r"^Bearer\s+", "", value)
        if _is_reference(value):
            return None
        for t, rx in SPECIFIC_RE.items():
            if rx.fullmatch(value):
                kind = t
                break
    if kind == "private-key":
        return kind, value
    body = re.sub(r"^(?:sk-(?:ant-(?:[a-z]+\d+-)?|or-v1-|proj-|svcacct-|admin-)?|(?:sk|rk)_live_|gh[a-z]_|github_pat_|"
                  r"xox[a-z]-|AIza|AKIA)", "", value)
    if len(set(body)) < 10 or PLACEHOLDER_RE.search(value):
        return None
    if kind == "bearer" and not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)):
        return None
    return kind, value


def history_files(only: str | None) -> list[tuple[str, Path]]:
    """(group label, file) for every transcript in scope."""
    home = home_dir()
    out = []
    projects = home / ".claude" / "projects"
    prefix = mangle(only) if only else None
    try:
        folders = sorted(os.scandir(projects), key=lambda e: e.name) if projects.is_dir() else []
    except OSError:
        folders = []
    for entry in folders:
        if not entry.is_dir() or (prefix and not folder_matches(entry.name, prefix)):
            continue
        for dp, _, fns in os.walk(entry.path):
            out += [(f"~/.claude/projects/{entry.name}", Path(dp) / f) for f in fns if f.endswith(".jsonl")]
    sessions = home / ".codex" / "sessions"
    if sessions.is_dir():
        for dp, _, fns in os.walk(sessions):
            for f in fns:
                if not f.endswith(".jsonl"):
                    continue
                p = Path(dp) / f
                if prefix:
                    cwd = codex_cwd(p)
                    if not cwd or not folder_matches(mangle(cwd), prefix):
                        continue
                out.append(("~/.codex/sessions", p))
    hist = home / ".codex" / "history.jsonl"
    if not prefix and hist.is_file():
        out.append(("~/.codex/history.jsonl", hist))
    return out


def codex_cwd(path: Path) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline(MAX_LINE)
    except OSError:
        return None
    m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', first)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except ValueError:
        return None


def scan_history(only: str | None, max_seconds: float) -> dict:
    """Secrets pasted into or printed in agent sessions. Values are never kept in the report."""
    start = time.monotonic()
    files = history_files(only)
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    files.sort(key=lambda gp: -mtime(gp[1]))  # newest first, so a time cap drops the oldest
    groups: dict[str, dict] = {}
    for label, _ in files:
        groups.setdefault(label, {"folder": label, "files": 0, "scanned": 0, "unique": {}, "occurrences": {},
                                  "newest": "", "examples": [], "_seen": set()})["files"] += 1
    scanned = skipped_long = 0
    distinct: set = set()

    capped = False
    for label, path in files:
        if time.monotonic() - start >= max_seconds:

            capped = True
            break
        g = groups[label]
        g["scanned"] += 1
        scanned += 1
        try:
            fh = open(path, "rb")
        except OSError:
            continue
        with fh:
            n = 0
            while True:
                line = fh.readline(MAX_LINE)
                if not line:
                    break
                n += 1
                if len(line) >= MAX_LINE and not line.endswith(b"\n"):
                    skipped_long += 1
                    while True:
                        rest = fh.readline(MAX_LINE)
                        if not rest or rest.endswith(b"\n"):
                            break
                    continue
                for m in find_secrets(line):
                    res = _classify(m.lastgroup.replace("_", "-"), m.group(0).decode("ascii", "replace"))
                    if not res:
                        continue
                    kind, value = res
                    g["occurrences"][kind] = g["occurrences"].get(kind, 0) + 1
                    ts = TIMESTAMP_RE.search(line)
                    day = ts.group(1).decode() if ts else time.strftime("%Y-%m-%d", time.localtime(mtime(path)))
                    g["newest"] = max(g["newest"], day)
                    key = (kind, value)
                    if key in g["_seen"]:
                        continue
                    g["_seen"].add(key)
                    g["unique"][kind] = g["unique"].get(kind, 0) + 1
                    distinct.add(key)
                    if len(g["examples"]) < MAX_LIST:
                        g["examples"].append({"type": kind, "prefix": value[:4] + "****", "file": path.name,
                                              "line": n, "date": day})
    out_groups = []
    total = len(distinct)  # a key seen in several folders counts once here
    for g in groups.values():
        g.pop("_seen")
        out_groups.append(g)
    out_groups.sort(key=lambda g: (-sum(g["unique"].values()), g["folder"]))
    flags = []
    for g in out_groups:
        if g["unique"]:
            kinds = ", ".join(f"{v} {k}" for k, v in sorted(g["unique"].items(), key=lambda kv: -kv[1]))
            flags.append({"id": "secret-in-history", "reason":
                          f"{g['folder']}: {kinds} (newest {g['newest']}); rotate each one, then delete or redact the transcript"})
    return {"scope": only or "all projects", "files_total": len(files), "files_scanned": scanned,
            "long_lines_skipped": skipped_long, "capped": capped, "seconds": round(time.monotonic() - start, 1),
            "unique_secrets": total, "folders": [g for g in out_groups if g["unique"]] , "folders_total": len(out_groups),
            "flags": flags}


# --------------------------------------------------------------------------- extensions

KNOWN_BAD_EXTENSIONS = {
    ("anthropic.claude-code", "2.1.312"): "fake copy of the Claude Code extension seen in Cursor's marketplace cache",
    ("anthropic.claude-code", "2.1.313"): "fake copy of the Claude Code extension seen in Cursor's marketplace cache",
}
EXTENSION_DIRS = [(".vscode/extensions", "VS Code"), (".cursor/extensions", "Cursor"),
                  (".windsurf/extensions", "Windsurf")]
EXT_RE = re.compile(r"^(?P<id>[A-Za-z0-9][\w\-]*\.[A-Za-z0-9][\w.\-]*?)-(?P<ver>\d+\.\d+\.\d+)(?P<rest>[\w.\-]*)$")


def scan_extensions() -> list[dict]:
    out = []
    for rel, editor in EXTENSION_DIRS:
        d = home_dir() / rel
        if not d.is_dir():
            continue
        try:
            names = [e.name for e in os.scandir(d) if e.is_dir()]
        except OSError:
            continue
        flags = []
        for name in sorted(names):
            m = EXT_RE.match(name)
            if not m:
                continue
            why = KNOWN_BAD_EXTENSIONS.get((m.group("id").lower(), m.group("ver")))
            if why:
                flags.append({"id": "known-bad-extension", "reason":
                              f"{name}: {why}. Uninstall it, then rotate every key the editor could reach"})
        out.append({"editor": editor, "path": "~/" + rel, "count": len(names), "flags": flags})
    return out


# --------------------------------------------------------------------------- driving (cont.)

def scan_root(root: Path, scanner: Scanner) -> tuple[list, list, list]:
    configs, docs, walked = [], [], []
    root = root.expanduser()
    if root.is_file():
        agent = match_target(root) or "unknown"
        return [scan_config(root, agent, root.parent, scanner, root.name)], [], []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        walked.append((here, list(dirnames), list(filenames)))
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg")))
        for f in sorted(filenames):
            p = here / f
            rel = p.relative_to(root).as_posix()
            agent = match_target(p)
            if agent:
                configs.append(scan_config(p, agent, root, scanner, rel))
            elif is_instruction(p, p.relative_to(root).parts):
                d = scan_markdown(p, rel, scanner)
                if d:
                    docs.append(d)
    return configs, docs, scan_projects(root, walked)


def scan_user(scanner: Scanner) -> list:
    home = home_dir()
    out = []
    for rel, agent in USER_FILES:
        p = home / rel
        if p.is_file():
            out.append(scan_config(p, agent, p.parent, scanner, "~/" + rel))
    return out


def all_flag_lists(report: dict) -> list[list]:
    lists = [it["flags"] for c in report["configs"] for it in c["items"]]
    lists += [d["flags"] for d in report["instructions"]]
    lists += [p["flags"] for p in report.get("projects", [])]
    lists += [e["flags"] for e in report.get("extensions") or []]
    if report.get("history"):
        lists += [report["history"]["flags"]]
    return lists


def summarize(report: dict) -> dict:
    cats, flags = {}, {}
    for c in report["configs"]:
        for it in c["items"]:
            cats[it["category"]] = cats.get(it["category"], 0) + 1
    flagged = 0
    for fl in all_flag_lists(report):
        if fl:
            flagged += 1 if fl is not (report.get("history") or {}).get("flags") else len(fl)
        for f in fl:
            flags[f["id"]] = flags.get(f["id"], 0) + 1
    projects = report.get("projects", [])
    out = {"config_files": len(report["configs"]), "entries": sum(cats.values()), "by_category": cats,
           "instruction_files_with_hits": len(report["instructions"]),
           "projects_with_manifests": sum(1 for p in projects if p["manifests"]),
           "flagged_entries": flagged, "flags": flags}
    if report.get("extensions") is not None:
        out["extensions"] = sum(e["count"] for e in report["extensions"])
    if report.get("history"):
        h = report["history"]
        out["history"] = {"files": h["files_total"], "scanned": h["files_scanned"], "unique_secrets": h["unique_secrets"],
                          "capped": h["capped"], "seconds": h["seconds"]}
    return out


ADVICE = ("Stolen AI keys get resold and run up bills (LLMjacking): give each tool its own key with a spend limit, "
          "and never expose an AI gateway (LiteLLM, Ollama, Open WebUI) with a default key.")


def print_text(report: dict) -> None:
    print(f"agent-config-audit (read-only) on: {', '.join(report['roots'])}")
    print("values redacted; pass --show-values to see them" if report["redacted"]
          else "WARNING: --show-values is on; secrets below are printed as-is (history hits stay redacted)")
    for c in report["configs"]:
        print(f"\n== {c['path']}  [{c['agent']}]")
        if not c["items"]:
            print("   (nothing that runs)")
        for it in c["items"]:
            label = f"{it['path']}: " if it["path"] else ""
            print(f"   {it['category']:<12} {label}{it['value']}")
            for f in it["flags"]:
                print(f"   {'':<12} !! {f['id']}: {f['reason']}")
    if report["instructions"]:
        print("\n== skill, command and instruction files that run shell, grant tools, declare hooks, or hide text")
        for d in report["instructions"]:
            print(f"   {d['path']}")
            for ln in d["lines"]:
                print(f"      {ln['line']}: {ln['text']}")
            for f in d["flags"]:
                print(f"      !! {f['id']}: {f['reason']}")
    if report.get("projects"):
        print("\n== dependencies (manifests, lockfiles, virtualenvs, git index)")
        for p in report["projects"]:
            parts = []
            if p["manifests"]:
                parts.append("manifests: " + ", ".join(sorted(set(p["manifests"]))))
            if p["lockfiles"]:
                parts.append("lockfiles: " + ", ".join(sorted(set(p["lockfiles"]))))
            if p["venvs"]:
                parts.append(f"venvs: {p['venvs']}")
            print(f"   {p['path']}  " + "; ".join(parts))
            for f in p["flags"]:
                print(f"      !! {f['id']}: {f['reason']}")
    if report.get("extensions") is not None:
        print("\n== editor extensions")
        if not report["extensions"]:
            print("   (no VS Code, Cursor or Windsurf extension folders)")
        for e in report["extensions"]:
            print(f"   {e['path']}  [{e['editor']}]  {e['count']} installed")
            for f in e["flags"]:
                print(f"      !! {f['id']}: {f['reason']}")
    h = report.get("history")
    if h:
        cap = "  CAPPED: oldest files not scanned, raise --history-max-seconds" if h["capped"] else ""
        print(f"\n== conversation history ({h['scope']}): {h['files_scanned']} of {h['files_total']} transcript file(s) "
              f"in {h['folders_total']} folder(s), {h['seconds']}s{cap}")
        if h["long_lines_skipped"]:
            print(f"   {h['long_lines_skipped']} line(s) over {MAX_LINE // 1_000_000} MB skipped")
        if not h["folders"]:
            print("   no high-confidence secrets found")
        for g in h["folders"]:
            kinds = ", ".join(f"{v} {k}" for k, v in sorted(g["unique"].items(), key=lambda kv: -kv[1]))
            print(f"   {g['folder']}  {g['files']} file(s); unique secrets: {kinds}; newest hit {g['newest']}")
            for ex in g["examples"]:
                print(f"      {ex['type']:<12} {ex['prefix']}  {ex['file']}:{ex['line']}  ({ex['date']})")
            more = sum(g["unique"].values()) - len(g["examples"])
            if more > 0:
                print(f"      ... and {more} more")
        for f in h["flags"]:
            print(f"   !! {f['id']}: {f['reason']}")
    s = report["summary"]
    print("\n== summary")
    cats = ", ".join(f"{v} {k}" for k, v in sorted(s["by_category"].items(), key=lambda kv: -kv[1])) or "none"
    print(f"   {s['config_files']} config file(s), {s['entries']} entries: {cats}")
    print(f"   {s['instruction_files_with_hits']} skill/instruction file(s) with shell, tool grants, hooks or hidden text")
    print(f"   {s['projects_with_manifests']} folder(s) with dependency manifests")
    if "extensions" in s:
        print(f"   {s['extensions']} editor extension(s) installed")
    if "history" in s:
        hs = s["history"]
        print(f"   history: {hs['scanned']} of {hs['files']} transcript file(s), {hs['unique_secrets']} unique secret(s)"
              f"{' (capped)' if hs['capped'] else ''}")
    if s["flags"]:
        fl = ", ".join(f"{k} {v}" for k, v in sorted(s["flags"].items(), key=lambda kv: -kv[1]))
        print(f"   {s['flagged_entries']} flagged: {fl}")
    else:
        print("   0 flagged. That is not the same as safe: read every hook and server above.")
    print(f"\n   {ADVICE}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only audit of what coding-agent config can run.")
    ap.add_argument("roots", nargs="*", default=["."], help="repo, folder of repos, or a single config file")
    ap.add_argument("--user", action="store_true",
                    help="also read user-level config and installed editor extensions in your home directory")
    ap.add_argument("--history", action="store_true",
                    help="scan every Claude Code and Codex transcript for pasted or printed secrets")
    ap.add_argument("--history-for", metavar="REPO",
                    help="scan only the transcripts of this repo (and its worktrees)")
    ap.add_argument("--history-max-seconds", type=float, default=300.0,
                    help="stop the history scan after this long, newest files first (default 300)")
    ap.add_argument("--json", action="store_true", help="print structured JSON")
    ap.add_argument("--show-values", action="store_true",
                    help="print config env values and tokens unredacted (history hits are always redacted)")
    a = ap.parse_args(argv)

    scanner = Scanner(show=a.show_values)
    configs, docs, projects, roots = [], [], [], []
    for r in a.roots:
        root = Path(r).expanduser()
        if not root.exists():
            print(f"no such path: {r}", file=sys.stderr)
            return 2
        roots.append(str(root))
        c, d, p = scan_root(root, scanner)
        configs += c
        docs += d
        if len(a.roots) > 1:
            for proj in p:
                proj["path"] = f"{root.name}/{proj['path']}"
        projects += p
    report = {"roots": roots, "redacted": not a.show_values, "configs": configs, "instructions": docs,
              "projects": projects}
    if a.user:
        roots.append("~ (user config)")
        configs += scan_user(scanner)
        report["extensions"] = scan_extensions()
    if a.history or a.history_for:
        only = str(Path(a.history_for).expanduser().resolve()) if a.history_for else None
        report["history"] = scan_history(only, a.history_max_seconds)
    report["advice"] = ADVICE
    report["summary"] = summarize(report)
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
