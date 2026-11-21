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

def read_text(path: Path) -> str | None:
    """The only file access in this script. Read mode, size-capped."""
    try:
        if path.stat().st_size > MAX_BYTES:
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


def scan_root(root: Path, scanner: Scanner) -> tuple[list, list]:
    configs, docs = [], []
    root = root.expanduser()
    if root.is_file():
        agent = match_target(root) or "unknown"
        return [scan_config(root, agent, root.parent, scanner, root.name)], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg")))
        here = Path(dirpath)
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
    return configs, docs


def scan_user(scanner: Scanner) -> list:
    home = Path.home()
    out = []
    for rel, agent in USER_FILES:
        p = home / rel
        if p.is_file():
            out.append(scan_config(p, agent, p.parent, scanner, "~/" + rel))
    return out


def summarize(configs: list, docs: list) -> dict:
    cats, flags = {}, {}
    flagged = 0
    for c in configs:
        for it in c["items"]:
            cats[it["category"]] = cats.get(it["category"], 0) + 1
            if it["flags"]:
                flagged += 1
            for f in it["flags"]:
                flags[f["id"]] = flags.get(f["id"], 0) + 1
    for d in docs:
        if d["flags"]:
            flagged += 1
        for f in d["flags"]:
            flags[f["id"]] = flags.get(f["id"], 0) + 1
    return {"config_files": len(configs), "entries": sum(cats.values()), "by_category": cats,
            "instruction_files_with_hits": len(docs), "flagged_entries": flagged, "flags": flags}


def print_text(report: dict) -> None:
    print(f"agent-config-audit (read-only) on: {', '.join(report['roots'])}")
    print("values redacted; pass --show-values to see them" if report["redacted"]
          else "WARNING: --show-values is on; secrets below are printed as-is")
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
    s = report["summary"]
    print("\n== summary")
    cats = ", ".join(f"{v} {k}" for k, v in sorted(s["by_category"].items(), key=lambda kv: -kv[1])) or "none"
    print(f"   {s['config_files']} config file(s), {s['entries']} entries: {cats}")
    print(f"   {s['instruction_files_with_hits']} skill/instruction file(s) with shell, tool grants, hooks or hidden text")
    if s["flags"]:
        fl = ", ".join(f"{k} {v}" for k, v in sorted(s["flags"].items(), key=lambda kv: -kv[1]))
        print(f"   {s['flagged_entries']} flagged: {fl}")
    else:
        print("   0 flagged. That is not the same as safe: read every hook and server above.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only audit of what coding-agent config can run.")
    ap.add_argument("roots", nargs="*", default=["."], help="repo, folder of repos, or a single config file")
    ap.add_argument("--user", action="store_true", help="also read user-level config in your home directory")
    ap.add_argument("--json", action="store_true", help="print structured JSON")
    ap.add_argument("--show-values", action="store_true", help="print env values and tokens unredacted")
    a = ap.parse_args(argv)

    scanner = Scanner(show=a.show_values)
    configs, docs, roots = [], [], []
    for r in a.roots:
        root = Path(r).expanduser()
        if not root.exists():
            print(f"no such path: {r}", file=sys.stderr)
            return 2
        roots.append(str(root))
        c, d = scan_root(root, scanner)
        configs += c
        docs += d
    if a.user:
        roots.append("~ (user config)")
        configs += scan_user(scanner)
    report = {"roots": roots, "redacted": not a.show_values, "configs": configs,
              "instructions": docs, "summary": summarize(configs, docs)}
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
