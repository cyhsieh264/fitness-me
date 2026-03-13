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

```bash
uv run python -m scripts.import_history <LINE_USER_ID>
```

Parses `specs/spec-001/raw-fitness-record` using LLM. Seeds exercise DB first if needed.

## Admin API

Requires `ADMIN_TOKEN` env var. All requests must include `X-Admin-Token` header.

### Download database

```bash
curl -o fitness.db https://your-server.com/admin/download-db \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Returns a consistent SQLite snapshot of the current database.

### Import historical records (remote)

File upload (recommended):

```bash
curl -X POST https://your-server.com/admin/import-history \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "line_user_id=U..." \
  -F "file=@records.txt"
```

Or JSON body:

```bash
curl -X POST https://your-server.com/admin/import-history \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"line_user_id": "U...", "raw_text": "..."}'
```

Records older than 2 years are automatically skipped (configurable via `cutoff_years`).

## Test

```bash
uv run pytest
```

## Deploy

Configured for Railway. See `railway.toml` and `Dockerfile`.
