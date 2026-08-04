---
name: setup-ai-tutor
description: Sets up and starts the AI Tutor project locally (environment file, dependencies, database, migrations, and dev server). Use when standing up the AI Tutor for the first time on a new machine or after a fresh clone. This is sample-project specific; adapt it when you install the AI Layer into your own project.
---

# Set Up the AI Tutor Locally

Run the following commands to set up and start the AI Tutor locally.

## Input

None required. Run from the repository root.

## Process

### 1. Create Environment File
```bash
cp .env.example .env
```
Creates your local environment configuration from the example template.

### 2. Install Dependencies
```bash
uv sync
```
Installs all Python packages defined in pyproject.toml.

### 3. Start Database
```bash
docker-compose up -d db
```
Starts PostgreSQL in a Docker container.

### 4. Run Database Migrations
```bash
uv run alembic upgrade head
```
Applies all pending database migrations.

### 5. Start Development Server
```bash
uv run uvicorn app.main:app --reload --port 8123
```
Starts the FastAPI server with hot-reload on port 8123.

### 6. Validate Setup

Check that everything is working:

```bash
# Test API health
curl -s http://localhost:8123/health

# Test database connection
curl -s http://localhost:8123/health/db
```

Both should return `{"status":"healthy"}` responses.

## Output

A running local AI Tutor instance.

### Access Points

- Swagger UI: http://localhost:8123/docs
- Health Check: http://localhost:8123/health
- Database: localhost (Docker container)

## Cleanup

To stop services:
```bash
# Stop dev server: Ctrl+C
# Stop database: docker-compose down
```

## Notes

- Port numbers and the exact `docker-compose` service name may differ — check `docker-compose.yml`,
  `.env.example`, and the project README for project-specific values before running.
