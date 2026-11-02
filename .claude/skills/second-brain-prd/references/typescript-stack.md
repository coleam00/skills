# TypeScript Stack

The runtime, the packages and the gotchas for everything in `architecture-reference.md`. Use `.ts` file names and kebab-case paths throughout the PRD (`memory-flush.ts`, `memory-search.ts`, `heartbeat.ts`).

## Runtime

- **Node 22.22.2 or newer on the 22 line, or 24.15 or newer** (what `node-notifier` 12 requires). It runs `.ts` files directly by stripping types, so there is no build step and no `tsx`.
  `node .claude/scripts/heartbeat.ts` just works. The code has to stay erasable: no `enum`, no parameter properties,
  no `namespace`. Set `erasableSyntaxOnly` and `verbatimModuleSyntax` in `tsconfig.json` so the compiler enforces it. A bare import of
  a type crashes at runtime under type stripping, so write `import type`. Import local files with their `.ts`
  extension and set `allowImportingTsExtensions`.
- **`package.json`** with `"type": "module"` at the repo root. `tsc --noEmit` is the type check. It never emits.
- **Hooks** are plain commands in `.claude/settings.json`: `node "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.ts"`, so a changed working directory can't break them.

## Packages

| Concern | Package or approach |
|---|---|
| Agent runtime | `@anthropic-ai/claude-agent-sdk` (`query()` returns an async iterable of messages) |
| Embeddings | `@huggingface/transformers`, model `Xenova/all-MiniLM-L6-v2`, `dtype: "q8"`, `pooling: "mean"`, `normalize: true`. 384 dimensions, and it runs locally |
| SQLite | `better-sqlite3`, plus `sqlite-vec` (`sqliteVec.load(db)`) and FTS5, which is built in |
| Postgres (VPS) | `pg` with `pgvector`, tsvector + GIN for keywords |
| Gmail / Calendar / Drive | `googleapis` |
| Slack | `@slack/web-api`, and `@slack/bolt` for the chat interface |
| GitHub | `@octokit/rest` |
| Linear | `@linear/sdk` |
| Data models | a TypeScript `interface`, plus `zod` where data crosses a trust boundary |
| File locking | `proper-lockfile`, with `realpath: false` (the file may not exist yet) and `retries` set |
| Retries | a small `withRetry()` helper, no library needed |
| Atomic writes | write to a `.tmp` file, then `fs.renameSync()` |
| Background flush | `spawn(process.execPath, [script], { detached: true, stdio: "ignore", windowsHide: true }).unref()` |
| Notifications | `node-notifier` |
| Environment | `process.env`, loaded with `process.loadEnvFile()` |
| Hook recursion guard | `process.env.CLAUDE_INVOKED_BY` |
| Named deliverables | `buildSnapshot()`, `diffSnapshot()`, `withFileLock()`, `withRetry()`, `DANGEROUS_BASH_PATTERNS` |
| Integration template | `integrations/integration-template.ts` |
| Vault merge driver | `.claude/scripts/git-merge-concat.ts`, run with `node` and registered with `git config` |

## File layout

- `.claude/hooks/session-start.ts`
- `.claude/hooks/pre-compact-flush.ts`
- `.claude/hooks/session-end-flush.ts`
- `.claude/hooks/block-secrets.ts`
- `.claude/scripts/memory-flush.ts`
- `.claude/scripts/db.ts`, `embeddings.ts`
- `.claude/scripts/memory-index.ts`, `memory-search.ts`
- `.claude/scripts/heartbeat.ts`, `memory-reflect.ts`
- `.claude/scripts/shared.ts`, `sanitize.ts`
- `.claude/scripts/integrations/registry.ts`, `query.ts`, `integration-template.ts`
- `.claude/scripts/guardrail.ts`, `notify.ts`
- `.claude/hooks/command-guard.ts`
- `.claude/chat/main.ts`, `engine.ts`, `session-store.ts`, `adapters/platform-adapter.ts`, `adapters/slack.ts`

## Gotchas found by running this stack

- **sqlite-vec takes a `BigInt` rowid.** Binding a plain JS number to `rowid` on a `vec0` insert throws in
  `better-sqlite3`. Use `BigInt(id)`, and bind the vector as a `Buffer` over the `Float32Array`.
- **FTS5 `MATCH` throws on raw user text.** Quote each search term before you pass it in, or a hyphen in the query
  becomes a syntax error at runtime.
- **Score hybrid search over a fixed candidate pool, and give every candidate its real cosine score.** If a keyword
  hit outside the vector top-k gets a vector score of 0, an exact identifier can never rank first. Read its cosine
  with `vec_distance_cosine` by rowid. Divide bm25 by the best hit (min-max scaling scores the weakest real match 0).
  Tie the pool to a constant, not to `--limit`, or the ranking changes with the limit.
- **Quoted FTS5 terms mean AND.** Join them with `OR` and drop stop words, or a natural-language query matches nothing.
- **The first embedding call downloads the model.** Set `env.cacheDir` to a folder under `.claude/data/` so a hook or
  a scheduled run doesn't download it to a surprising place, and load it lazily so nothing that skips search pays
  the few seconds of startup.
- **Pass long prompts over stdin, not argv.** On Windows the argv limit is about 32K characters and a heartbeat
  prompt passes that. Give `query()` an async iterable of user messages instead of a string for anything built from
  integration data.
- **`allowedTools` does not restrict on its own.** It auto-approves the tools you list. For a pure reasoning call
  (memory flush, guardrail), also pass `tools: []` and `settingSources: []`, so the model has no tools and doesn't load
  your project's hooks or skills. For a heartbeat or reflection, pass `settingSources: ["project"]` so your project's security hooks load, and
  add a `PreToolUse` hook through the SDK `hooks` option to block writes to `SOUL.md`.
- **Hooks that print to stdout are injecting context.** Node's experimental warnings go to stderr, so they don't
  pollute it, but any stray `console.log` in a `SessionStart` hook ends up in the agent's context.
- **Auth.** The SDK uses your Claude Code login when no API key is set, so log in with `claude` once. Set
  `ANTHROPIC_API_KEY` only if you want API billing. Say which one the user is on in the PRD's cost estimate.

## Design principle

TypeScript gathers data, Claude reasons. Deterministic code handles auth and fetching, and the model only ever sees data.
