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

- Lock out bypass mode: `{ "permissions": { "disableBypassPermissionsMode": "disable" } }`.
- On macOS, Linux and WSL2, turn on the sandbox with `/sandbox`. It does not run on
  native Windows.

## Secrets in config

1. **Rotate first.** A secret that was ever committed is still in git history, so
   untracking the file does not un-leak it.
2. `git rm --cached .claude/settings.local.json`, add `**/.claude/settings.local.json`
   to `.gitignore`, commit.
3. `git ls-files | grep settings.local.json` should print nothing afterwards.

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
