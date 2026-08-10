# Cole's AI Skills

The skills I actually use to build software with coding agents. Straight out of my `.claude/skills/` folder.

## What this is

A skill is a folder with a `SKILL.md` in it: a name, a description of when to use it, and the procedure the agent
should follow. Your agent loads the description at startup and pulls in the full skill only when the work matches.
That's the whole idea, and it's why skills scale where a 2,000-line `CLAUDE.md` doesn't.

These 33 skills are the AI Layer from my [Agentic Coding course](https://dynamous.ai). They're built around one
loop I run on nearly every ticket:

**prime → plan → implement → validate → review → commit → PR**

Around that loop sit the pieces that feed it (PRD, architecture, epic slicing), the pieces that run it in parallel
(worktrees), and the meta-skills that let you build more of your own AI Layer (rules, hooks, skills, opportunity
scans).

Nothing here is a framework. Each skill is a plain markdown file you can read in two minutes, disagree with, and
edit. That's the point: read them, take the ones that fit how you work, rewrite the rest.

## Bring them in

### As a Claude Code plugin (easiest, stays updated)

Run these two commands inside Claude Code:

```
/plugin marketplace add coleam00/skills
/plugin install skills@cole-medin
```

That's it. All 33 skills, managed and read-only, and `/plugin marketplace update` pulls new ones as I add them.
Plugin skills are namespaced, so you invoke them as `/skills:piv-implement`.

The whole set costs roughly 4,200 tokens of always-on context (just the descriptions; the bodies load only when a
skill fires). Run `claude plugin details skills` to see the per-skill breakdown, and disable the plugin any
time with `/plugin`.

> **If that first command fails with `Permission denied (publickey)`:** the `owner/repo` shorthand prefers SSH,
> and your SSH key isn't authenticating to GitHub. Recent Claude Code versions detect that and fall back to HTTPS
> on their own. If yours doesn't, pass the HTTPS URL directly, which needs no key:
>
> ```
> /plugin marketplace add https://github.com/coleam00/skills.git
> ```
>
> Setting `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` in your environment makes the shorthand use HTTPS permanently.

### As editable files, in any agent

```bash
npx skills add coleam00/skills                             # everything
npx skills add coleam00/skills --list                      # see what's here first
npx skills add coleam00/skills --skill piv-plan-implementation piv-implement piv-validate
```

Add `-g` to install globally (`~/.claude/skills/`) instead of into the current project. This route writes real
files into your repo, so you can edit them, which is what I'd actually recommend once you know which ones you keep
reaching for.

### Or just clone and copy

They're only markdown files:

```bash
git clone https://github.com/coleam00/skills.git
cp -r skills/.claude/skills/piv-implement your-project/.claude/skills/
```

### Or ask your agent

This works fine too:

> Clone https://github.com/coleam00/skills, look at the skills in `.claude/skills/`, and copy the ones
> that fit this project into my `.claude/skills/` folder. Tell me which ones you picked and why.

For the last two, restart your session (or run `/skills`) and they'll show up.

## The skills

**Prime: load the right context, and only that**

| Skill | What it does |
|---|---|
| `prime-codebase` | Orients the agent in a codebase before planning or implementing |
| `prime-backend` | Same, scoped to API routes, services, and the data layer |
| `prime-frontend` | Same, scoped to components, routing, state, and styling |

**Plan: intent before implementation**

| Skill | What it does |
|---|---|
| `plan-create-prd` | Interviews you into a problem-first PRD. Intent, never engineering decisions |
| `plan-architecture` | A working session on *how* to build it: stack, data shape, trade-offs, risks |
| `piv-slice-epic` | Slices an epic plus its architecture into PIV-sized tickets with a dependency graph |
| `plan-create-stories` | Turns a PRD into a real backlog in Jira or GitHub |

**The PIV loop: plan, implement, validate**

| Skill | What it does |
|---|---|
| `piv-plan-implementation` | Deep codebase analysis plus research into a one-pass-ready implementation plan |
| `piv-implement` | Executes that plan task-by-task, validating at every step |
| `piv-validate` | Runs the project's full suite and returns one PASS/FAIL verdict |
| `piv-review-changes` | Pre-commit technical review of what changed |
| `piv-fix-review-findings` | Triages review findings. You decide what gets fixed now vs deferred |
| `piv-commit` | One atomic, conventionally-tagged commit |
| `piv-create-pr` | Pushes the branch and opens the PR with a real body |
| `piv-review-pr` | The agentic gate on an open PR: fresh eyes, severity-ranked, posted to GitHub |
| `piv-run-full-loop` | Chains the core loop end-to-end from a single feature description |

**Issues: diagnose before you fix**

| Skill | What it does |
|---|---|
| `piv-investigate-issue` | Parallel investigation of a GitHub issue into an evidence-backed RCA |
| `piv-implement-issue` | Implements the fix from that RCA, with regression tests |

**Parallel work**

| Skill | What it does |
|---|---|
| `worktree-create` | Spins up N git worktrees, each configured, installed, and health-checked |
| `worktree-merge` | Integrates those branches through one safe integration branch |

**Build your own AI Layer: the meta-skills**

| Skill | What it does |
|---|---|
| `rules-create-global` | Derives a lean root `CLAUDE.md` from your codebase or your specs. The customizable `/init` |
| `rules-check-drift` | Checks whether your rules file is still *true* after recent changes |
| `ablate-ai-layer` | Tests whether your rules still earn their place: strips them, reruns the same task, diffs the two |
| `skills-create` | Authors a new skill, or refactors a fat one into `SKILL.md` plus `references/` |
| `hooks-create` | Turns "never let the agent touch my migrations" into a working hook, wired into settings |
| `opportunity-scan` | Reads how you actually work and recommends what to encode next |
| `system-execution-report` | Reflects on a just-finished implementation: what diverged from the plan |
| `system-evolution-review` | Finds the bugs in your *process*, not your code |
| `second-brain-audit` | Finds facts in your notes that quietly stopped being true, and restructures so they stop |

**Autonomy: hand the whole loop over**

| Skill | What it does |
|---|---|
| `build-dark-factory` | Takes a PRD and builds a repo around it that ships validated code with nobody at the keyboard. All five components, in construction order, plus a deterministic audit of what you built. It encodes the AI coding process you already run rather than replacing it, and it deliberately does not write the PRD: bring one, or make one with `plan-create-prd` first |

**Tools**

| Skill | What it does |
|---|---|
| `agent-browser` | Browser automation for the agent: navigate, fill, click, screenshot, extract |
| `ast-grep` | Structural code search by AST pattern instead of text |
| `setup-ai-tutor` | Stands up the course's sample project. Sample-specific, so adapt it or delete it |

## Using these with other agents

Skills are just markdown. There is no Claude-specific runtime here, so most of this works anywhere a coding agent
can read files.

The `npx skills` CLI installs to 75+ agents (Codex, Cursor, Copilot, Cline, Windsurf, OpenCode, Continue and the
rest) into whatever directory each one expects:

```bash
npx skills add coleam00/skills -a codex
npx skills add coleam00/skills -a cursor -a claude-code
```

If your agent has no skills mechanism at all, the fallback is boring and effective: keep the folder in your repo
and point at it from `AGENTS.md` (or the equivalent), telling the agent to read the matching `SKILL.md` before
starting that kind of work.

Two things to adjust when you port them:

- **Slash-command syntax.** Skills that reference each other by name (`/piv-validate`) assume Claude Code's
  invocation. Elsewhere, say "use the piv-validate skill" instead.
- **`allowed-tools` frontmatter.** A few skills declare it. Other agents ignore the field harmlessly.

## Make them yours

Two things deliberately ship as templates and expect an edit before first use:

- **`piv-validate`** has a placeholder command list. Put your project's real test, type-check, and lint commands
  in it.
- **`piv-commit`** and **`piv-create-pr`** read `.claude/references/conventions.md` if it exists, the first its
  `## commit` section and the second its `## pr` section. Create one and they'll follow your conventions instead
  of guessing.

`piv-review-pr` will hand its deep pass to a `code-reviewer` subagent if you have one in `.claude/agents/`. Without
it, the skill still works, it just does the review inline.

Everything else runs as-is. But read them anyway. A skill you haven't read is just a longer prompt you don't
control.

## License

MIT, see [LICENSE](LICENSE). Take them, fork them, rewrite them.
