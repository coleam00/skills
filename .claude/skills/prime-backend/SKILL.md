---
name: prime-backend
description: Primes the agent with focused understanding of the backend portion of the codebase — API routes, services, data models, and database layer — without loading unrelated frontend code. Use at the start of a session when the work is scoped to API endpoints, business logic, or data access. Optionally pulls external task context from Jira issues and Confluence pages first.
argument-hint: "[jira-issue-keys] [confluence-page-ids]"
---

# Prime Backend: Load Backend Context

## Objective

Build targeted understanding of the backend codebase by analyzing its structure, routes, services, and data layer. Loading only backend context keeps the context window light on complex full-stack codebases. If external task references are provided, load them first so the analysis is anchored to the actual work.

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

### 1. Locate the Backend

List all tracked files to find the backend root:

!`git ls-files`

Common backend roots: `backend/`, `server/`, `api/`, `app/` (FastAPI/Django), `src/` (when project is backend-only). Identify the correct root before proceeding.

### 2. Read Backend Documentation

- Read CLAUDE.md or similar global rules file (for project-wide conventions)
- Read any README inside the backend root
- Read `.claude/references/backend-api-best-practices.md` if it exists — it contains project-specific API conventions

### 3. Identify Key Backend Files

Based on the structure, read:

- Main entry point (`main.py`, `app.py`, `server.ts`, `index.ts`, etc.)
- Route registration / router index (`routes/`, `api/`, `routers/`)
- Core configuration (`pyproject.toml`, `package.json`, `tsconfig.json`)
- Database configuration and ORM setup (`database.py`, `db.ts`, `alembic.ini`)
- Core data models or schemas (`models/`, `schemas/`)
- One or two representative feature slices (route + service + model) to internalize established patterns
- Middleware and dependency injection setup

Skip files outside the backend root unless they define a shared type or contract the backend exposes.

### 4. Understand Current Backend State

Check recent backend-relevant activity:

!`git log -10 --oneline`

!`git status`

Note any open migrations, pending schema changes, or in-progress API changes.

## Output Report

Provide a concise summary covering:

### External Task Context (if loaded)
- Jira issue(s): key, title, one-line goal, acceptance criteria
- Confluence page(s): title and what they specify

### Backend Overview
- Framework and major libraries (FastAPI, Django, Express, NestJS, etc.)
- Language and runtime version
- Database and ORM (PostgreSQL + SQLAlchemy, MongoDB + Mongoose, etc.)

### Directory Map
- Backend root and key sub-directories with one-line purpose each

### Architecture Patterns
- How routes, services, and data access are layered
- Dependency injection or middleware patterns observed
- Error handling approach

### Conventions
- Naming conventions, module organization
- Migration tooling and current migration state
- Testing framework and conventions observed

### Current State
- Active branch, recent backend changes
- Any pending migrations or schema changes
- Any immediate concerns (missing validation, unhandled errors, etc.)

**Make this summary easy to scan - use bullet points and clear headers.**
