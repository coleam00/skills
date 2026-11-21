# Remediation

Fixes for what the audit finds, grouped by who applies them. Offer the ones that match
the findings; do not paste the whole file at the user.

## Opening a repo you did not write

1. Scan it first, from a session started outside it.
2. Open it with hooks off: `claude --settings '{"disableAllHooks": true}'`, or a file
   containing `{"disableAllHooks": true}` passed as `claude --settings <file>` (easier in
   Windows PowerShell, which mangles inline JSON quoting). `disableAllHooks` in user
   settings alone does not protect you: project settings take precedence and can set it
   back to `false`.
3. To ignore the project's settings files entirely, `claude --setting-sources user`.
4. Inside the session, review `/hooks` and `/mcp` before re-enabling anything.
5. Start agents inside a project folder, never in `~` or `~/Downloads`.

## Headless runs and CI

`claude -p` and the Agent SDK do not show the trust dialog, so a repo's committed hooks
and MCP servers run without a prompt. Never run them over a repo you did not write
without `--bare` (skips hooks from settings and plugins) or `--setting-sources user`.
In CI, never give an agent that reads issues or pull requests both shell access and
publish credentials.

## Hooks, tasks and scripts

- Remove a malicious entry from **every** file that carries one. Worms have planted a
  `.claude/settings.json` hook and a `.vscode/tasks.json` `folderOpen` task that each
  relaunch the other; cleaning one leaves a live path.
- VS Code and Cursor: keep workspace trust on (`"security.workspace.trust.enabled": true`)
  and stop automatic tasks with `"task.allowAutomaticTasks": "off"` in user settings
  (the default is `"on"`).
- A hook that needs the network should say why in a comment or the README. If nobody can
  say, remove it.

## MCP servers

- Pin every registry package: `npx -y some-server@1.4.2`, `uvx --from some-server==1.4.2 some-server`.
- Set `enableAllProjectMcpServers` to `false` (or remove it) and approve servers one by
  one with `enabledMcpjsonServers`.
- Reference secrets by environment variable (`"${API_KEY}"`) instead of writing them
  into `.mcp.json`.

## Permissions

- Allow exact commands or narrow patterns (`Bash(npm run test)`), never bare `Bash`,
  `Bash(curl *)` or interpreter wildcards.
- Approve patterns, not one-off commands that contain a secret: an approved command is
  saved verbatim, secret included.
- Deny the agent's file tools access to credentials in `~/.claude/settings.json`:

  ```json
  { "permissions": { "deny": ["Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)", "Read(~/.ssh/**)", "Read(~/.aws/**)"] } }
  ```

- Keep secrets out of the session entirely. Put them in an .env file the agent never
  opens, and have the agent load them from the environment in code
  (`os.environ["API_KEY"]`, `process.env.API_KEY`). Never paste a live key into a prompt:
  agent sessions are stored.
- Enforce it with a hook, not a rule. `references/secrets-guard-hook.py` is a PreToolUse
  hook that blocks every route to a credential (env files, SSH keys, `.pem`, `.aws`,
  `.netrc`, dumping the process environment) and `rm -rf`, and allows a committed
  `.env.example`. Copy it to `.claude/hooks/pre_tool_use_secrets.py` and register it:

  ```json
  { "hooks": { "PreToolUse": [ { "matcher": "Read|Edit|MultiEdit|Write|NotebookEdit|Bash|PowerShell|Grep|Glob",
    "hooks": [ { "type": "command", "command": "uv run ${CLAUDE_PROJECT_DIR}/.claude/hooks/pre_tool_use_secrets.py", "timeout": 15 } ] } ] } }
  ```

  Tested on Claude Code 2.1.330 on Windows (2026-11-21): asked to read the env file,
  the agent was blocked and did not try to work around it; asked to call an API with
  the key, it wrote code that loads it from the environment.
- Lock out bypass mode: `{ "permissions": { "disableBypassPermissionsMode": "disable" } }`.
- On macOS, Linux and WSL2, turn on the sandbox with `/sandbox`. It does not run on
  native Windows.

## Secrets in config

1. **Rotate first.** A secret that was ever committed is still in git history, so
   untracking the file does not un-leak it.
2. `git rm --cached .claude/settings.local.json`, add `**/.claude/settings.local.json`
   to `.gitignore`, commit.
3. `git ls-files | grep settings.local.json` should print nothing afterwards.

`local-settings-tracked` is fixed by steps 2 and 3, but only after step 1: a command
approved with "don't ask again" is saved verbatim, so assume every key in the file leaked.

## Dependencies

- **`no-lockfile`:** commit a lockfile and install from it (`npm ci`, `pnpm install
  --frozen-lockfile`, `bun install --frozen-lockfile`, `uv sync --locked`,
  `poetry install`, `cargo build --locked`). For a plain `requirements.txt`, pin every
  line with `==`, ideally with `--require-hashes`.
- **Wait out new releases.** Most poisoned releases are pulled within days, so refuse
  anything younger than that: pnpm `minimumReleaseAge` in `pnpm-workspace.yaml` (minutes,
  for example `10080` for a week), uv `exclude-newer` in `pyproject.toml` under `[tool.uv]`
  or `--exclude-newer <date>`, npm `--before <date>`. Update deliberately, then re-run
  this scan.
- **`known-compromised`:** remove the version, pin a clean one, delete and recreate the
  virtualenv or `node_modules`. If it was ever installed or imported, follow "When a hook
  already ran" below: the agent-framework stealer ran from a `.pth` file at every Python
  start, before any of your code.
- **`suspicious-pth`:** read the file by hand (do not run Python in that environment
  first, since that executes it). If nobody can say which package installed it, delete
  the virtualenv and treat the machine as exposed.

## Secrets in conversation history (`secret-in-history`)

1. **Rotate the key first.** The transcript sits on disk in plain text and may already
   have been copied by a backup, a sync tool or malware.
2. Then delete the transcript file the scanner named (`~/.claude/projects/<folder>/<file>`
   or `~/.codex/sessions/...`), or redact the value in it. Never open it in the agent to
   do this: that puts the secret back into a new session.
3. Shorten retention: Claude Code's `cleanupPeriodDays` in `~/.claude/settings.json`
   deletes old transcripts automatically.
4. Stop pasting keys into prompts. Put them in an env file the agent never reads (the
   secrets guard hook above enforces that) and have code load them from the environment.

## Editor extensions (`known-bad-extension`)

1. Uninstall it from the editor, then delete its folder under `~/.vscode/extensions`,
   `~/.cursor/extensions` or `~/.windsurf/extensions` if it remains.
2. Rotate every key the editor could reach: model API keys, GitHub tokens, cloud
   credentials in the workspace.
3. Install extensions only from the publisher's verified listing, and check the
   publisher name, not just the display name.

## Stolen AI keys (LLMjacking)

- **One key per tool, each with a spend limit** set at the provider (Anthropic, OpenAI and
  OpenRouter all support per-key or per-workspace limits). A leaked key then costs at
  most its limit, and you know which tool leaked it.
- **Never expose an AI gateway with a default key.** LiteLLM's documented master key
  `sk-1234` (`default-gateway-key`), Ollama listening on `0.0.0.0:11434` with no auth, and
  Open WebUI with sign-up left open are all found by scanners within hours. Bind to
  localhost or put real auth in front, and set a long random key.
- Turn on usage alerts so a spike is noticed the same day.

## Teams

- **CODEOWNERS on agent config**, plus branch protection requiring code-owner review:

  ```
  /.claude/   @org/security
  /.mcp.json  @org/security
  /.codex/    @org/security
  /.cursor/   @org/security
  /.vscode/   @org/security
  /AGENTS.md  @org/security
  /CLAUDE.md  @org/security
  ```

- **Managed settings** for Claude Code: `allowManagedHooksOnly: true` blocks user,
  project, local and plugin hooks; add `allowManagedMcpServersOnly` or
  `allowedMcpServers` / `deniedMcpServers`, `disableBypassPermissionsMode: "disable"`
  and `strictKnownMarketplaces`. Check the current settings reference before rolling
  these out; the set evolves.
- Run secret scanning over `.claude/`, `.cursor/` and `.gemini/` in pre-commit and CI,
  with a custom rule for passwords inside command strings, and turn on push protection.
- Run this scanner in CI on pull requests that touch agent config, and fail review on
  any `!!` line nobody has explained.

## When a hook already ran

If a startup hook or `folderOpen` task fetched and ran something:

1. Treat the machine as compromised. Disconnect it from anything sensitive.
2. Rotate every credential the user could reach (cloud, GitHub, npm, model API keys,
   SSH keys) **from a different, clean machine**.
3. Look for persistence the payload may have left: new entries in
   `~/.ssh/authorized_keys`, scheduled tasks, LaunchAgents, systemd units, shell
   profile edits, and agent config in other repos on the machine (scan the whole code
   folder with this skill).
4. Removing the repo or extension is not enough on its own; follow the incident
   response process of whoever owns the machine.
