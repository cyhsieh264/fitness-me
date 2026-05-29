"""Drop all app tables, recreate the schema, and re-seed.

Usage (local SQLite or Supabase Postgres — same command):
    uv run python -m scripts.reset_db                 # interactive confirm
    uv run python -m scripts.reset_db --yes           # skip prompt
    uv run python -m scripts.reset_db --no-seed       # drop+create only

Reads DATABASE_URL from .env, so make sure the .env points at the DB you
actually want to wipe. The script only touches tables declared in
src/db/models.py::Base — Supabase's own schemas (auth, storage, ...) and
any unrelated tables in the same database are left untouched.

NOTE: This does NOT delete files in Supabase Storage. user_images rows will
be gone but their underlying jpgs in the bucket stay. Run `scripts/wipe_storage.py`
(if you write one) or use Supabase Studio's bucket UI to purge those.
"""

import os

# Allow running without LINE credentials.
os.environ.setdefault("LINE_CHANNEL_SECRET", "reset_dummy")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "reset_dummy")

import argparse
import asyncio
import logging
import sys

from src.config import settings
from src.db.database import engine
from src.db.models import Base

logger = logging.getLogger(__name__)


async def reset(skip_seed: bool) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Dropped all app tables")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Recreated schema")

    if skip_seed:
        return

    # Lazy import — seed module imports config too and we want logging set up first.
    from scripts.seed import run_seed

    await run_seed()


def _redact(url: str) -> str:
    """Hide the password segment of a postgres URI before printing."""
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        return f"{scheme}://{user}:***@{host}"
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip the interactive confirm")
    parser.add_argument("--no-seed", action="store_true", help="drop+create only, no seeding")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    target = _redact(settings.database_url)
    print(f"About to DROP & RECREATE all app tables on:\n  {target}")
    if not args.yes:
        confirm = input("Type 'RESET' to proceed: ").strip()
        if confirm != "RESET":
            print("Aborted.")
            sys.exit(1)

    asyncio.run(reset(skip_seed=args.no_seed))
    print("Done.")


if __name__ == "__main__":
    main()
