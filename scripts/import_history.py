"""Import historical fitness records using LLM parsing.

Usage:
    uv run python -m scripts.import_history [LINE_USER_ID]

Requires .env with at minimum:
    LLM_API_KEY=your_api_key
    LLM_MODEL=gemini/gemini-2.0-flash   (or other supported model)
    DATABASE_URL=sqlite+aiosqlite:///data/fitness.db
"""

import os

# Allow running without LINE credentials (not needed for import)
os.environ.setdefault("LINE_CHANNEL_SECRET", "import_dummy")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "import_dummy")

import asyncio
import logging
from pathlib import Path

from src.services.import_records import run_import

RAW_RECORD_PATH = Path(__file__).parent.parent / "specs" / "spec-001" / "raw-fitness-record"


async def main(line_user_id: str) -> None:
    from scripts.seed import run_seed

    await run_seed()

    text = RAW_RECORD_PATH.read_text(encoding="utf-8")
    counts = await run_import(line_user_id, text)
    print(
        f"Done: new={counts['new']}, already_existed={counts['already_existed']}, "
        f"llm_failed={counts['llm_failed']}, total={counts['total']}"
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    line_uid = sys.argv[1] if len(sys.argv) > 1 else "IMPORT_USER"
    asyncio.run(main(line_uid))
