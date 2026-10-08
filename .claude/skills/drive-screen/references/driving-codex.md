# Driving Codex

Use this branch for Codex CLI, desktop tasks, and app-server integrations.
`screenctl.py` can manipulate a visible window, but the bundled transcript
watcher and `autodrive.py` understand Claude Code records only. Pointing them at a
Codex repository does not select or monitor its Codex session.

## Choose the supported surface

For an existing desktop task, use the host's task inspection and continuation
controls with its exact task ID. Read its status and requested artifacts after
completion. The desktop app, bundled runtime, and terminal CLI can have different
versions; identify the surface you are actually operating.

For a new scripted run, resolve `codex` through `PATH`, check `codex --version`,
`codex exec --help`, and `codex exec resume --help`. Preserve the configured model,
authentication, and permission contract. Use the Codex companion's installation
policy when one is provided by the host. The example below needs a Git repository
and an existing prompt file; review the prompt before launching it.

```bash
run_dir="$(mktemp -d /tmp/drive-codex.XXXXXX)"
run_status=0
codex exec -C "$REPO" --sandbox read-only --json \
  -o "$run_dir/final.txt" - < "$PROMPT_FILE" \
  > "$run_dir/events.jsonl" 2> "$run_dir/stderr.log" || run_status=$?
```

`run_status` works in Bash and zsh; `status` is a read-only zsh parameter.
Use `--sandbox workspace-write` only when the task authorizes edits. A sandbox
flag does not replace host approval rules. `--full-auto` is deprecated in the
checked CLI generation. Check installed help rather than adding bypass flags
when an operation is refused.

## Establish completion

Parse complete JSON lines from this invocation's event file. Keep stderr
separate so progress and diagnostics do not corrupt JSON parsing.

- Capture `thread.started.thread_id` for the actual session identity.
- Require a successful process exit and a terminal `turn.completed` event for
  this invocation. Empty logs, truncated lines, unknown formats, or missing
  terminal events are inconclusive. Inspect errors; a terminal `turn.failed` or
  unrecovered transport error is failure, not completion.
- Read `final.txt` and check the requested artifact or behavior. A completed
  model turn can still report a blocker or unfinished task.
- Retain only requested evidence, then clean up this run's temporary directory.

`-o` stores the last assistant message, not the full transcript. Do not parse
private Codex rollout files as if they were the supported event stream.

To continue a persistent run, use its exact emitted UUID. Put shared exec options
before the resume subcommand; use that version's help for accepted flags:

```bash
codex exec -C "$REPO" --sandbox read-only resume --json \
  -o "$run_dir/resumed-final.txt" "$THREAD_ID" - < "$FOLLOWUP_FILE" \
  > "$run_dir/resumed-events.jsonl" 2> "$run_dir/resumed-stderr.log"
```

Capture and validate the resumed process exit and events in the same way.
`--last` can pick another concurrent session. `--ephemeral` does not persist a new
session for later resumption. Claude's `--session-id` and `CLAUDE*` environment
cleanup are not Codex equivalents.

## Approvals and app-server events

For an integration that needs interactive approvals, use the supported app-server
request/response contract. Inspect each request's target, payload, and available
decisions. Command, file, network, and connector requests are distinct; a quiet
log or default Enter selection cannot identify them. Follow the host's approval
mechanism and honor a denial across UI, terminal, and API routes.

The two event protocols have different names and completion semantics:

| Interface | Completion event | What to inspect |
|---|---|---|
| `codex exec --json` | `turn.completed` / `turn.failed` | This process's final event, exit status, response, and artifacts |
| App-server JSON-RPC | `turn/completed` | Matching thread/turn IDs and `turn.status`: `completed`, `interrupted`, or `failed` |

The app-server method name alone is not success. For example,
`turn/completed` with `turn.status = "interrupted"` records cancellation.

## Read-audit limits

Codex can receive `AGENTS.md` at startup without a file-read tool call. Supplied
context, skills, shell commands, MCP tools, and child agents are additional input
paths. An absent `Read` or `cat` event cannot establish that the model never saw a
file. For recall experiments, record all supplied inputs and describe the limits
of the observed events.

## Sources

Verified against CLI 0.154.0 help and official documentation on 2026-09-15:

- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [App-server](https://learn.chatgpt.com/docs/app-server)
- [AGENTS.md instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
