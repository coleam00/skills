---
name: agent-config-audit
description: Read-only audit of everything a repository's coding-agent config can run on its own - Claude Code hooks, status lines and helper commands, MCP servers, Codex and Cursor hooks, Gemini CLI settings, VS Code folder-open tasks, plugin marketplaces, permission allow rules, MCP auto-approval, and skills that run inline shell - then explains each risky entry in plain words and how to fix it. Flags downloads piped to a shell, encoded commands, endpoint overrides such as ANTHROPIC_BASE_URL, unpinned MCP packages, broad allow rules and credentials written into config, and never prints secret values. Use when the user says "audit my agent config", "what runs when I open this repo", "check my repos for malicious hooks", "is this repo safe to open", before trusting or opening a cloned repo, after pulling changes to .claude, .mcp.json, .codex, .cursor or .vscode, or after a supply-chain incident.
argument-hint: "[path to a repo, or a folder of repos]"
---

# Agent Config Audit

Coding agents run commands from files that live in the repo. A hook in
`.claude/settings.json`, a server in `.mcp.json`, a `folderOpen` task in
`.vscode/tasks.json`: each one executes with the user's full access, and a `git pull`
can add one. In November 2026 Google's threat intelligence group reported attackers
editing `.claude/settings.json` in internal repos "so that when users started up Claude
Code, it would automatically trigger the download" of a backdoor. No agent was hacked.
The tool did what its config said.

The split that matters: **instruction files** (`CLAUDE.md`, `AGENTS.md`, rules, skills)
can only persuade. **Settings files** run code. This skill inventories the second kind
and checks the first for hidden text.

## Ground rules

- **Audit from outside the repo.** Starting an agent inside a repo already ran its
  `SessionStart` hooks and connected its MCP servers. Pass the path from a session
  started somewhere else. If this session was started inside the target, say so in the
  report: the audit still finds problems, but it can no longer prevent the first run.
- **Never run anything found.** No hook commands, no fetching the URLs, no `npx` of a
  listed package. To read an encoded payload, decode it to text and never pipe it
  anywhere.
- **Never show a secret.** The scanner redacts by default. Do not `cat` a config file
  into the conversation, since that bypasses redaction; quote only the lines needed.
  Use `--show-values` only when the user explicitly asks on their own machine, and
  still never repeat a value back.
- **Report, then fix on approval.** Do not edit or delete config during the audit.

## Step 1: pick the target

Use the path the user gave. With none, ask, and offer the current directory. A single
repo is the usual case; a folder of repos works too (the scanner walks it, skipping
`node_modules`, `.git`, virtualenvs and build output). When the user means "my agent
config" in general, add `--user` to include `~/.claude`, `~/.claude.json`, `~/.codex`,
`~/.cursor` and `~/.gemini`.

## Step 2: run the scanner

```bash
python <skill>/scripts/agent_config_audit.py <path> [--user] [--json]
```

Stdlib only, Python 3.8+ (3.11+ to parse Codex TOML), strictly read-only. Read its
output, never its source. It lists every entry that can run or grant something, marks
suspicious ones with `!!`, and ends with counts. A large folder takes a while; a
single repo takes seconds.

## Step 3: judge every entry

The flags are deliberately few, so each deserves a sentence in the report. Treat them as
leads, then read the entry itself.

| Flag | What it means in plain words |
|---|---|
| `pipe-to-shell`, `download-then-run` | Fetches code from the internet and runs it. Whoever controls that server controls the machine, and can change the payload at any time. The single strongest signal. |
| `encoded-payload` | base64 or `-EncodedCommand`: the readable command is a wrapper and the real one is hidden. Legitimate config almost never needs this. |
| `remote-host` | Contacts a host each time it runs. Ask who owns the domain and why a hook needs the network at all. "Silenced output" on top of that is worse. |
| `hidden-process` | A hidden window, `nohup`, `setsid`: keeps running after the agent moves on. |
| `credential-files` | Touches `~/.ssh`, `~/.aws`, `.npmrc`, agent login files. A formatter has no reason to. |
| `endpoint-override` | `ANTHROPIC_BASE_URL`, `*_BASE_URL`, proxies, `NODE_OPTIONS`: routes every prompt, file and key through someone else's server, or changes what code loads. |
| `unpinned-package` | An MCP server run through `npx`, `uvx` or `bunx` with no version, so the next release to that package runs automatically. Check the package exists, is the one intended (typosquats), and pin it. |
| `auto-approve-mcp` | `enableAllProjectMcpServers: true` approves every server in `.mcp.json`, including ones a later pull adds. |
| `bypass-permissions` | `bypassPermissions`, Codex `approval_policy = "never"` or `danger-full-access`: nothing asks before acting. |
| `broad-allow` | Allow rules like `Bash`, `Bash(curl *)`, `Bash(python *)` let the agent run arbitrary code without a prompt. Narrow them to exact commands. |
| `secret-in-config` | A literal key, password or token in env, headers, args or an allow rule. If the file was ever committed, rotating is required, not optional: it is still in git history. |
| `runs-on-open` | A VS Code or Cursor task with `runOn: folderOpen`: runs the moment the folder opens, before any agent starts. |
| `hidden-characters` | Zero-width or tag characters in an instruction file: instructions the agent reads and a reviewer cannot see. |
| `plugin-source` | Adds a plugin marketplace. Plugins ship their own hooks and MCP servers. |
| `hooks-reenabled` | A project file sets `disableAllHooks: false`, overriding a user who turned hooks off. |
| `unparsed`, `unreadable` | The file could not be parsed or read. Read it by hand; a broken file can still run. |

Then read what no flag covers:

- **Every hook on a startup event** (`SessionStart`, `Setup`) and every `statusLine`:
  they run before the user types anything, or constantly.
- **Scripts with innocent names.** The scanner opens scripts that a hook names when
  they sit inside the scanned path, and flags the same patterns in them. Obfuscated
  code passes a pattern check, so read any script that runs at startup.
- **MCP servers nobody recognizes**, and `url` servers on unfamiliar domains.
- **`settings.local.json` committed to git.** It is meant to stay local and often
  holds approved commands with secrets inside them.

**Zero flags is not a clean bill of health.** Say so in the report rather than "no
problems found".

## Step 4: for repos already trusted, read the history

A repo the user already opens daily is where a malicious change lands unnoticed. Show
what changed in the agent config and who changed it:

```bash
git log -p -- .claude .mcp.json .codex .cursor .vscode .gemini AGENTS.md CLAUDE.md
git diff HEAD@{1} -- .claude .mcp.json .codex .cursor .vscode AGENTS.md CLAUDE.md   # since the last pull
git ls-files | grep settings.local.json   # should print nothing
```

The classic sign is a config change inside a commit whose message is about something
else, or from an author who does not normally touch tooling.

## Step 5: report

Lead with the single most serious finding in one sentence, then one short block per
flagged entry: the file, what the entry does, when it runs, why it matters, and the
fix. Then the summary counts. Do not paste the full inventory unless asked. If
something already ran (the session started inside the repo, or a startup hook fetched
a payload), say plainly that the machine should be treated as exposed.

## Step 6: fix

Offer the fixes that match the findings, and apply them only when the user agrees. The
two to say every time:

- **First open of any repo with hooks off:** `claude --settings '{"disableAllHooks": true}'`.
  In Windows PowerShell, put `{"disableAllHooks": true}` in a file and pass its path:
  `claude --settings no-hooks.json`. Setting it in user settings alone is not enough,
  because project settings can turn it back on. `claude --setting-sources user` skips
  project settings entirely.
- **Then review inside the agent** with `/hooks` and `/mcp` before turning hooks back on.

Deny rules, pinning, CODEOWNERS on agent config, managed settings for teams, editor
settings and the cleanup steps after a real compromise are in
`references/remediation.md`. Read it when a finding needs more than the two lines above.

## Resources

- `scripts/agent_config_audit.py`: the scanner. `--json` for structured output,
  `--user` for home-directory config, `--show-values` to disable redaction. Run it;
  do not read it into context.
- `scripts/_test_agent_config_audit.py`: builds a booby-trapped repo and a clean one in
  a temp dir and checks every flag, redaction, and that the scan changes no file. Run
  it after editing the scanner.
- `references/remediation.md`: concrete fixes for individuals and teams, and what to
  do when a hook already ran.
