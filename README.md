# Fitness-Me

Personal fitness LINE Bot powered by LLM. Tracks workouts, detects PRs, and gives training suggestions.

## Setup

```bash
uv sync
cp .env.example .env
# Edit .env with your credentials
```

## Run

```bash
uv run uvicorn src.main:app --reload
```

## One-Time Scripts

### Seed exercise database

Populates exercises, aliases, and muscle groups. Runs automatically on app startup, but can also be run manually:

```bash
uv run python -m scripts.seed
```

### Import historical records

Parses `specs/spec-001/raw-fitness-record` using LLM and imports into the database. Requires `LLM_API_KEY` in `.env`.

```bash
uv run python -m scripts.import_history <LINE_USER_ID>
```

- Seeds exercise database first if not already done
- 51 date blocks, ~3.5 min total (4s interval for Gemini free tier rate limit)
- Generates `data/fitness.db` with sessions, exercises, sets, PRs, and conditions

## Test

```bash
uv run pytest
```

## Deploy

Configured for Railway. See `railway.toml` and `Dockerfile`.
