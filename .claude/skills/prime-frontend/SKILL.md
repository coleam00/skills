---
name: prime-frontend
description: Primes the agent with focused understanding of the frontend portion of the codebase — components, routing, state management, and styling — without loading unrelated backend code. Use at the start of a session when the work is scoped to UI or client-side features. Optionally pulls external task context from Jira issues and Confluence pages first.
argument-hint: "[jira-issue-keys] [confluence-page-ids]"
---

# Prime Frontend: Load Frontend Context

## Objective

Build targeted understanding of the frontend codebase by analyzing its structure, components, and conventions. Loading only frontend context keeps the context window light on complex full-stack codebases. If external task references are provided, load them first so the analysis is anchored to the actual work.

## Process

### Step 0: Load External Context

**Run this step BEFORE the codebase analysis.** It accepts optional arguments: `[jira-issue-keys] [confluence-page-ids]`.

- Jira keys may be a single key (`ACC-2`) or comma-separated (`ACC-2,ACC-3`).
- Confluence page ids are numeric page ids.

**If Jira issue keys are provided:**

1. Call `mcp__atlassian__getAccessibleAtlassianResources` to obtain the `cloudId`.
2. For each Jira key, call `mcp__atlassian__getJiraIssue` with that `cloudId`, the issue key, and `responseContentFormat: "markdown"`.
3. Treat the returned issue summary, description, and acceptance criteria as the task context for everything that follows.

**If Confluence page ids are provided:**

1. Call `mcp__atlassian__getConfluencePage` for each page id with `contentFormat: "markdown"` (use the `cloudId` from above, fetching it via `mcp__atlassian__getAccessibleAtlassianResources` if it was not already retrieved).
2. Treat the returned page content as supporting context (specs, design docs, requirements).

**If no arguments are provided:** Skip this step entirely and proceed to Step 1.

Briefly summarize any external context loaded before continuing — this frames the rest of the priming.

### 1. Locate the Frontend

List all tracked files to find the frontend root:

!`git ls-files`

Common frontend roots: `frontend/`, `client/`, `web/`, `src/` (when project is frontend-only), `app/` (Next.js). Identify the correct root before proceeding.

### 2. Read Frontend Documentation

- Read CLAUDE.md or similar global rules file (for project-wide conventions)
- Read any README inside the frontend root
- Read `.claude/references/frontend-component-best-practices.md` if it exists — it contains project-specific component conventions

### 3. Identify Key Frontend Files

Based on the structure, read:

- Main entry point (`main.tsx`, `index.tsx`, `app/layout.tsx`, `pages/_app.tsx`, etc.)
- Routing configuration (`router.tsx`, `routes.ts`, `app/` directory for Next.js)
- Global state setup (store, context providers)
- Shared component library root (`components/`, `ui/`)
- Core configuration (`package.json`, `tsconfig.json`, `vite.config.ts`, `next.config.ts`)
- One or two representative feature components to internalize the established patterns

Skip files outside the frontend root unless they define a shared type or contract the frontend depends on.

### 4. Understand Current Frontend State

Check recent frontend-relevant activity:

!`git log -10 --oneline`

!`git status`

Note any open changes in the frontend directory.

## Output Report

Provide a concise summary covering:

### External Task Context (if loaded)
- Jira issue(s): key, title, one-line goal, acceptance criteria
- Confluence page(s): title and what they specify

### Frontend Overview
- Framework and major libraries (React, Vue, Next.js, Tailwind, etc.)
- Component patterns observed (atomic design, feature folders, etc.)
- State management approach

### Directory Map
- Frontend root and key sub-directories with one-line purpose each

### Conventions
- Naming conventions, file co-location rules
- Styling approach
- Testing framework and conventions observed

### Current State
- Active branch, recent frontend changes
- Any immediate concerns (missing types, deprecated patterns, etc.)

**Make this summary easy to scan - use bullet points and clear headers.**
