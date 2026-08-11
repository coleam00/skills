# Hooks

Six hooks I actually run, as copy-in files.

A rule *asks* the agent to behave. A hook **guarantees** it. Your rules file is guidance the model reads,
weighs against everything else in context, and follows most of the time. A hook is code the harness runs on a
lifecycle event, whether the model remembers it or not. The agent never chooses to invoke a hook, which is
precisely why a hook can guarantee anything at all.

The decision is one line:

> **If the consequence of the agent ignoring it is a minor annoyance, write a rule.
> If the consequence is a production incident, a leaked secret, or a broken deploy, write a hook.**

Most people's AI Layer is 90% rules and 0% hooks. That is backwards for the handful of things that must be
true every single time.

## Why this matters more than it sounds

There is a measurement behind this, not just a preference. In [Agentic Harness
Engineering](https://arxiv.org/abs/2604.25850) a research team let an agent rewrite its own harness for ten
rounds and measured which layer earned the gain. The system prompt it wrote for itself was genuinely good, 9 KB
of well-reasoned rules. Swapped into the baseline **on its own it scored below doing nothing** (67.4% against a
69.7% seed). Every point of the improvement came from the other layers: memory, tools, and middleware, which is
to say, from enforcement rather than instruction.

The arc inside that repo is the whole argument. The prompt already said "do not destroy verified state." The
agent ignored it. So at iteration 5 the loop wrote a guard into the shell tool that intercepted the destructive
command. It gave itself an override token. Three rounds later it took the override away from itself.

Rules got ignored. Guards did not.

## What ships here

| File | Event | What it does | Blocks? |
|---|---|---|---|
| `pre_tool_use_secrets.py` | **PreToolUse** | Refuses any route to a credential (env file, ssh keys, `.pem`, `.aws`, `.netrc`, or dumping the process environment) and refuses `rm -rf`. Committed `.env.example` is allowed. | **Yes** |
| `pre_tool_use_dependencies.py` | **PreToolUse** | Declared file coupling, enforced. The agent cannot edit a file until it has read that file's dependencies this session. | **Yes** (or injects) |
| `post_tool_use_log.py` | **PostToolUse** | Appends one JSONL line per tool call to `logs/agent-actions.jsonl`. A greppable audit trail of everything the agent did. | No |
| `session_start_context.py` | **SessionStart** | Injects what is true *today*: branch, uncommitted files, recent commits, plus any working-notes file. | No |
| `stop_tests_must_pass.py` | **Stop** | Runs your test command when the agent tries to finish. Red, and it blocks the stop and hands back the failures. | **Yes** |
| `stop_notify.py` | **Stop** | Native desktop notification when the turn ends, so you can walk away. | No |

That split is the mental model: **pre = gate, post = log.** Pre-hooks fire before the action, so they can stop
it. Post-hooks fire after, so all they can do is observe and react.

## Install

```bash
# from your project root
mkdir -p .claude/hooks
cp path/to/skills/hooks/*.py .claude/hooks/
cp path/to/skills/hooks/settings.json.example .claude/settings.json   # or merge the "hooks" block
```

If you already have a `.claude/settings.json`, **merge** the `hooks` block rather than replacing the file.
Hooks from different settings files merge; they do not overwrite each other.

Then pick your two edits:

- `stop_tests_must_pass.py` → set `TEST_COMMAND` to your actual test command.
- `pre_tool_use_dependencies.py` → copy `dependencies.example.json` to `.claude/hooks/dependencies.json` and
  declare your own couplings. **Until that file exists this hook allows everything**, so it is safe to install
  before you have configured it.

Commit `.claude/settings.json`. That is how the whole team inherits the same guarantees.

## Prove they work

Never trust a hook you have only read. A hook that always blocks and a hook that never blocks look identical
until the moment one of them fires wrong. Feed each one a payload and check the exit code:

```bash
# should BLOCK (exit 2)
echo '{"session_id":"t","cwd":".","tool_name":"Read","tool_input":{"file_path":".env"}}' \
  | uv run .claude/hooks/pre_tool_use_secrets.py; echo "exit=$?"

# should ALLOW (exit 0)
echo '{"session_id":"t","cwd":".","tool_name":"Read","tool_input":{"file_path":"README.md"}}' \
  | uv run .claude/hooks/pre_tool_use_secrets.py; echo "exit=$?"
```

For `stop_tests_must_pass.py` you must check **both** directions: exit 0 while the suite is green, exit 2 once
you deliberately break a test. If it exits 2 in both states your test command is not resolving — see the venv
note below, which is the cause roughly every time.

## The five things that will bite you

**1. The venv trap.** This is the one that wastes an afternoon. A hook runs under `uv run` in a throwaway
environment that has none of your project's packages, and it is not your shell, so your project's `.venv` was
never on `PATH` either. Strip uv's venv and `python` falls through to some global interpreter with the wrong
packages. Either way the hook exits 2 on a green suite and blames an unrelated module — it looks like a real
failure. `stop_tests_must_pass.py` handles both halves in `_project_env()`; steal it.

**2. `@file` mentions bypass PreToolUse entirely.** When you type `@config/secrets.yml` in your prompt, the file
is attached without a tool call, so no PreToolUse hook fires. Your guard covers what the *agent* reaches for,
not what *you* hand it.

**3. `additionalContext` must be nested.** It goes inside `hookSpecificOutput`, never at the top level. Put it
at the top level and Claude Code silently ignores it. No error, no warning, it just does not arrive.

**4. Hooks run in a non-interactive shell.** No `~/.zshrc`, no `~/.bashrc`. A tool that is only on `PATH`
because of your shell profile works when you test by hand and fails when the hook runs it. And if your profile
prints anything at startup, that text mixes into the hook's stdout and breaks JSON parsing.

**5. A `Stop` hook without a loop guard is an infinite loop.** It blocks the stop, the agent works, tries to
stop, gets blocked again, forever. Check `stop_hook_active` and stand down when it is true. Both `Stop` hooks
here do.

Debugging: `claude --debug` shows hook execution, and `CLAUDE_CODE_DEBUG_LOG_LEVEL=verbose` shows matcher
counts, which answers "did my matcher actually match."

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Allow. stdout is parsed for JSON on the events that accept it. |
| `2` | **Block.** stderr goes back to the agent as the reason, so it adapts. |
| anything else | Non-blocking error. Shown to you, execution continues. |

Exit `1` is the trap: it means "error," and Claude Code logs it and carries on. If you meant to block and you
exit 1, nothing is blocked and you will not be told.

Only some events honor a block: `PreToolUse`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`,
`PostToolBatch`, and a few others. `PostToolUse` cannot block, because the tool already ran.

## Beyond command hooks

Every hook here is a `command` hook, a script that gets JSON on stdin. There are four other handler types worth
knowing about, configured the same way in `settings.json`:

- **`prompt`** — send the event to a fast model and get an allow/deny back. For judgments a regex cannot make
  ("does this commit message describe what actually changed?").
- **`agent`** — spawn a subagent with real tools that can read the codebase before deciding. Expensive and
  slow; reserve it for gates worth a minute.
- **`http`** — POST the event to a server. This is how you enforce one policy across a whole org from one place.
- **`mcp_tool`** — call a tool on an MCP server you already have connected.

Command hooks are still the right default: they are instant, free, and you can read them.

## Two things to know

**Hooks run real code, automatically, with your credentials, with no sandbox.** Review a hook the way you
review a CI script. Only run hooks you have read and trust. Same caution as an MCP server.

**Coverage is yours.** The hook is guaranteed to *run*. What it *catches* is only as good as the check you
wrote. `pre_tool_use_secrets.py` covers three routes to a secret: the env file, the other credential files, and
the process environment. That third one matters more than it looks, because a guard that blocks the env *file*
but not the *environment* is mostly theatre when the same values are sitting right there in the shell.

What it deliberately does not cover is the two-step route: nothing stops the agent writing a script that reads
the environment and then running it, because the run looks innocent. Closing that means inspecting the
*content* of `Write` and `Edit` calls, not just the path, which roughly triples the size of the file. If you
are guarding something that matters, that is the next thing to add.

## Write your own without writing Python

Use the [`hooks-create`](../.claude/skills/hooks-create/SKILL.md) skill. Describe the guarantee in plain
English and it picks the event, writes the script, wires `settings.json`, and tests it:

```
/hooks-create "never let the agent edit anything under db/migrations/"
/hooks-create "run ruff on every python file the moment it's edited"
/hooks-create "ping me on Slack when the agent needs my input"
```

## Portability

Not a Claude Code party trick. Codex and Cursor use the same shape (a script, JSON on stdin, exit 2 to block);
Gemini CLI does the same job by reading a structured JSON decision instead of the exit code; Pi and opencode
run hooks in-process as plugins. Learn it once and it transfers, the same way `AGENTS.md` became the shared
rules file.
