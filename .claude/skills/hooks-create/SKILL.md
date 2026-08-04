---
name: hooks-create
description: Author a working Claude Code hook from a plain-English description of what it should guarantee or do. You describe the behavior ("never let the agent edit my migrations", "don't stop until the tests pass", "log every command"); this skill picks the right lifecycle event, writes the hook script, and wires it into .claude/settings.json. Use when you want a deterministic guarantee or automation in your AI Layer and don't want to write the hook by hand. The meta-tool for the hooks primitive.
argument-hint: [what-the-hook-should-do]
---

# Create Hook: Turn an Idea Into a Working Claude Code Hook

**What the user wants the hook to do**: $ARGUMENTS

If that is filled in, treat it as the behavior spec and start from it. Don't re-ask what they already told you;
only ask to pin down the gaps (the exact paths / commands / patterns, and whether it must *block*). If it is
blank, start by asking what the hook should guarantee or do (Workflow step 1).

## What a hook is (30-second intro)

A **hook** is deterministic code that fires automatically on a Claude Code **lifecycle event** — before a tool
runs, after it runs, when the agent tries to finish, when a session starts, and so on. Unlike a skill or a
subagent, **the agent does not choose to invoke a hook** — it fires whether the model "remembers" or not. That is
the whole point: a rule *asks* the agent to behave; a hook **guarantees** it, at the tooling layer the model
can't talk its way around.

The user brings the **idea** ("the agent should never read my `.env`"); this skill writes the **code** and wires
it in. They don't need to know Python.

**It's all composition** — a hook is just a small script the harness runs at a defined moment, configured in
`.claude/settings.json`. You're adding one more deterministic guarantee to the AI Layer.

## The one thing to get right: which event, and can it block?

The behavior the user wants maps to **one** lifecycle event. Pick by *when* it should fire and *whether it must
stop something*:

| The user wants to… | Event | Can it block? |
|---|---|---|
| **Stop the agent from doing something** (read a secret, edit a protected path, run a destructive command) | **PreToolUse** ⭐ | **Yes** — block the tool before it runs |
| **React after an action** (auto-format an edited file, log a command, inject context) | **PostToolUse** | No — the tool already ran; observe / format / inject only |
| **Guarantee work isn't "done" until a check passes** (don't stop until tests/lint/types are green) | **Stop** (or **SubagentStop**) | **Yes** — block the stop and send the agent back to work |
| **Gate or scan the user's prompt** before the model sees it | **UserPromptSubmit** | **Yes** — block the prompt; can also inject context |
| **Load context every time a session starts** | **SessionStart** | No — inject context only |
| **Get notified when the agent needs you / finishes** | **Notification** (or **Stop**) | No — side-effect only (desktop/Slack/sound) |
| **Snapshot state before context compaction** | **PreCompact** | No |

> **Pre = guarantee/gate. Post = react/log.** If the user's goal is "make sure X never happens" or "don't finish
> until Y," it's a *blocking* hook (PreToolUse / Stop / UserPromptSubmit). If it's "do Z when W happens," it's an
> *observe/react* hook (PostToolUse / SessionStart / Notification).

## Required reading (do this first)

The hook event list and the exact stdin/stdout contract **evolve** — don't rely on a snapshot. Before writing,
**fetch the current docs** and confirm the event name, its input fields, and its control protocol:

- Hooks reference: https://code.claude.com/docs/en/hooks
- Hooks guide (examples): https://code.claude.com/docs/en/hooks-guide

Use `WebFetch` on these and verify against what you're about to write. If the fetch fails, proceed from the
canonical events in the table above and **say so** in your report so the user can double-check.

## The execution protocol (how a hook talks to Claude Code)

- **Input:** Claude Code passes a JSON object on **stdin** — always includes `session_id`, `cwd`,
  `hook_event_name`; event-specific fields like `tool_name` + `tool_input` (tool events), `prompt`
  (UserPromptSubmit), `source` (SessionStart).
- **Output / control:**
  - **`exit 0`** — allow / success. For `UserPromptSubmit` and `SessionStart`, anything printed to **stdout** is
    injected into the agent's context.
  - **`exit 2`** — **block.** The action is prevented and whatever you print to **stderr** is fed back to the
    agent as the reason, so it adapts. (Only blocking-capable events honor this — see the table.)
  - **any other exit code** — non-blocking error; shown to the user, execution continues.
  - **Advanced (optional):** instead of exit codes, print a JSON object on stdout — e.g. `{"decision":"block",
    "reason":"…"}` (Stop), or `{"hookSpecificOutput":{"hookEventName":"PreToolUse",
    "permissionDecision":"deny","permissionDecisionReason":"…"}}`. Prefer the simple exit-code form unless the
    user needs to *modify* input/output or inject context with `additionalContext`. Confirm field names against
    the fetched docs.

## Workflow

### 1. Understand the idea (start from `$ARGUMENTS`; ask only to fill gaps)
Start from what the user already described in `$ARGUMENTS` (the user may not be technical). Pin down two things in
plain language, asking only for what is missing:
- **What** should happen or be prevented, and **when** (before/after an action, at finish, at session start)?
- **How precisely** should it match? ("any `.env` file", "the `migrations/` folder", "`rm -rf`", "my test
  command exits non-zero"). Get the concrete file paths / commands / patterns — the guarantee is only as good as
  what it matches, so don't guess. If the ask is vague, propose a concrete interpretation and confirm.

### 2. Read the docs
Fetch the hooks reference/guide (above) and confirm the target event's name, stdin fields, and control protocol.

### 3. Pick the event (and matcher)
Use the table to choose the single event. Choose a **matcher** that scopes it tightly — for tool events, the
tool name(s) (e.g. `"Bash"`, `"Edit|Write"`, `"mcp__.*"`); empty/`"*"` means every occurrence. Don't fire on
everything if the goal is specific.

### 4. Write the hook script
- Default to a **`uv` single-file Python script** at `.claude/hooks/<event_snake_case>.py` (matches the pack's
  tooling). Use another language only if the user asks.
- Read the JSON from stdin, do the check, and:
  - to **block**: print a clear reason to `stderr` and `sys.exit(2)`;
  - to **allow**: `sys.exit(0)` (optionally print context to stdout for the injecting events).
- **Fail open.** Wrap the body so any unexpected error exits `0` (a broken hook must never brick the user's
  session). The only intentional non-zero exit is the deliberate `exit 2` block.
- Keep it lean and readable — the user will want to tweak the matched paths/commands later.
- If a hook already exists for that event, **extend it** rather than overwrite (add your check; keep theirs).
- **`Stop` / `SubagentStop` only:** check `stop_hook_active` first and `sys.exit(0)` when it is true. Without
  that guard the hook blocks the stop, the agent works, tries to stop again, is blocked again — a loop.

> ### ⚠️ Running a project command from a hook (read this before writing one)
>
> The hook itself runs under **`uv run`, in an isolated ephemeral environment**. Its interpreter is NOT the
> project's interpreter and does NOT have the project's dependencies. So:
>
> - **NEVER** rebuild the command with `sys.executable` or a bare `["python", "-m", "pytest", ...]` list. That
>   runs the *hook's* throwaway python, which has no pytest, no project packages, nothing. The command fails with
>   `No module named …` **every single time** — so a "don't finish until tests pass" hook blocks on green as
>   readily as on red, and reports a nonsense reason. It looks like it works. It does not.
> - **DO** run the user's command **verbatim, as a shell string, in the project directory — with uv's ephemeral
>   venv stripped from the environment.** `shell=True` alone is not enough: `uv run` puts its throwaway
>   interpreter first on `PATH` and sets `VIRTUAL_ENV`, so even a shell command resolves `python` to the wrong
>   one. Copy this helper as-is:
>   ```python
>   TEST_COMMAND = "python -m pytest -q"   # exactly what the user typed; the one line they'll edit
>
>   def _project_env() -> dict:
>       """os.environ minus uv's ephemeral venv, so the project's own tools resolve."""
>       env = os.environ.copy()
>       venv = env.pop("VIRTUAL_ENV", None)
>       if venv:
>           drop = {os.path.join(venv, "Scripts"), os.path.join(venv, "bin")}
>           env["PATH"] = os.pathsep.join(
>               p for p in env.get("PATH", "").split(os.pathsep) if p not in drop
>           )
>       return env
>
>   result = subprocess.run(
>       TEST_COMMAND, shell=True, capture_output=True, text=True,
>       cwd=hook_input.get("cwd"),          # the project root Claude Code passes in
>       env=_project_env(),
>   )
>   ```
>   Put the command in a single named constant at the top of the file so the user can edit one obvious line.
> - If the command must run from a **subdirectory** (a monorepo, or a project whose test config lives deeper —
>   e.g. `app/backend/`), ask for that, and pass it: `cwd=Path(hook_input["cwd"]) / "app/backend"`. Getting this
>   wrong produces a hook that always blocks, which the user will read as "hooks are broken."

### 5. Wire it into settings.json
Edit `.claude/settings.json` (create it if absent). **Merge** into any existing `hooks` block — never clobber
other events or other hooks on the same event. Shape:
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|Read|Bash",
        "hooks": [ { "type": "command", "command": "uv run .claude/hooks/pre_tool_use.py" } ] }
    ]
  }
}
```

### 6. Prove it yourself, then explain and warn

**Run the hook before you hand it over.** Feed it a sample event on stdin and check the exit code — do not ship a
hook you have only read. A hook that always blocks, or never blocks, looks identical to a working one until it
fires at the wrong moment.

```bash
# should ALLOW (exit 0)
echo '{"session_id":"t","cwd":"<project-root>","hook_event_name":"Stop","stop_hook_active":false}' | uv run .claude/hooks/stop.py; echo "exit=$?"
```

- For a **command-running hook** (tests/lint/types), this is mandatory and you must check **both** directions:
  it exits 0 while the command passes, and exits 2 once it genuinely fails. If it exits 2 in both states, the
  command is not resolving — re-read the warning in step 4 about `sys.executable`.
- For a **blocking guard**, feed it one payload that should be blocked and one that should pass.
- If a check comes back wrong, fix the script and re-run before reporting success.

Then:
- Tell the user **what you built**, in plain words: which event, what it guarantees, and the one line they'd
  change to adjust it.
- Give them a **way to prove it** in the agent: for a blocking hook, an action that *should* be blocked ("ask me
  to read the env file — watch it refuse"); for an observe hook, where the output lands (the log, the notification).
- Report what you verified, and say plainly if you could not verify something.
- **Security note (always say this):** a hook runs arbitrary code automatically, with your credentials, on every
  matching event. Review hooks like you review CI config; only run hooks you trust. (Same caution as MCP
  servers.)

## Quality checks

- ✅ The behavior maps to the **right event**, and a blocking goal uses a **blocking-capable** event (PreToolUse /
  Stop / UserPromptSubmit) — not PostToolUse.
- ✅ The **matcher is scoped** to what the user actually meant (not firing on everything by accident).
- ✅ The script **fails open** — any error exits 0; the only `exit 2` is the intended block, with a clear stderr reason.
- ✅ Any **project command runs verbatim via `shell=True` in the project `cwd`** — never rebuilt with
  `sys.executable` or a bare `python` (the hook's own interpreter has none of the project's dependencies).
- ✅ A `Stop` / `SubagentStop` hook honors **`stop_hook_active`** so it cannot loop.
- ✅ `settings.json` was **merged**, not overwritten; existing hooks still present.
- ✅ **You ran the hook** and confirmed it exits 0 when it should allow and 2 when it should block — not just read it.
- ✅ The user got a **plain-English explanation + a test + the security note.**

## Notes

- Hooks are the deterministic floor of the AI Layer — use them for the non-negotiables (secrets, protected paths,
  "don't finish until green"), not for things a rule or skill handles well enough.
- A blocking hook's *coverage* is only as good as its matcher — it guarantees the hook **runs**, but you decide
  what it catches. Be honest with the user about the edges (e.g. a `.env` matcher won't catch a base64'd read).
- Keep hooks fast — they run on the matched event every time. Heavy work belongs in an async hook or a skill.
