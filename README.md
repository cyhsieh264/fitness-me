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

### Import historical records (local)

```bash
uv run python -m scripts.import_history <LINE_USER_ID>
```

Parses `specs/spec-001/raw-fitness-record` using LLM. Seeds exercise DB first if needed.

## Storage Backends

`STORAGE_PROVIDER` selects the image store:

- `local`    — writes to `data/images/`. Signed URLs route back through `/images/{key}/{token}` (HMAC).
- `supabase` — uploads to a Supabase Storage bucket. Signed URLs are minted by Supabase.

To swap, change `STORAGE_PROVIDER` and the Supabase env vars; no code changes required.

## Admin API

Requires `ADMIN_TOKEN` env var. All requests must include `X-Admin-Token` header.

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

> Database backups are handled by Supabase (free tier: 7-day point-in-time recovery). For local SQLite dev there is no automated backup.

## Test

```bash
uv run pytest
```

## Deploy

Configured for **Fly.io (Tokyo, `nrt`) + Supabase**.

```bash
fly launch --no-deploy        # one-time, picks app name
fly secrets set \
  LINE_CHANNEL_SECRET=... \
  LINE_CHANNEL_ACCESS_TOKEN=... \
  LLM_API_KEY=... \
  DATABASE_URL='postgresql+asyncpg://postgres.<ref>:<pwd>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres' \
  SUPABASE_URL=https://<ref>.supabase.co \
  SUPABASE_SERVICE_KEY=... \
  SUPABASE_BUCKET=fitness-images \
  ALLOWED_USER_IDS=U... \
  ADMIN_TOKEN=... \
  BASE_URL=https://<your-app>.fly.dev
fly deploy
```

Then point the LINE webhook to `https://<your-app>.fly.dev/webhook`.

The Supabase connection string **must** use the **Session Pooler** (port 5432 on the pooler hostname). Direct (5432) is IPv6-only on the free tier and will fail from Fly; Transaction Pooler (6543) breaks SQLAlchemy's prepared-statement cache.

To run with local-volume storage instead of Supabase Storage, set `STORAGE_PROVIDER=local` and uncomment the `[[mounts]]` block in `fly.toml`.
