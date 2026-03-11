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
import json
import logging
import re
from datetime import date
from pathlib import Path

from src.db.database import async_session
from src.llm.client import chat_completion
from src.llm.tool_executor import execute_tool
from src.llm.tools import TOOLS
from src.services.user import get_or_create_user
from src.services.workout import save_raw_record

logger = logging.getLogger(__name__)

RAW_RECORD_PATH = Path(__file__).parent.parent / "specs" / "spec-001" / "raw-fitness-record"

DATE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")

IMPORT_SYSTEM_PROMPT = """\
You are importing historical workout records into a database.
Parse the workout text and call the appropriate tools.

Rules:
- Use log_strength_training for exercise data
- Use log_user_condition for body condition/posture/weakness observations
- The date is given in the prompt. Always use it in the tool call.
- All sessions are type "coach" (personal training records)
- "空" = bodyweight (omit weight_value, set weight_type to "bodyweight")
- "each" = weight_type "per_side"
- "練習槓" = empty standard barbell (~20kg total). "練習槓+Nkg each" = 20 + N*2 total
- Continuation lines (start with number/+) are additional set groups for the previous exercise
- "round" = num_sets
- "sec" -> duration_sec, "min" -> duration_sec * 60
- "Wod 30:30*N" = circuit with 30s work / 30s rest. Following lines are circuit exercises.
  -> Log as a single exercise "WOD Circuit" with duration_sec and num_sets
- Parenthetical notes are technique cues -> put in exercise notes, not as separate exercises
- Lines describing body observations (e.g. "左骨盆較高", "調整深蹲發力不均") -> log_user_condition
- Band notation "黑+綠" -> weight_type "band", band_info "black+green"
- X上/X下 (e.g. 5上, 9下) are bench height settings, not weight. Ignore them.
- For weight ranges like "34-38kg", use the higher value
- For rep ranges like "8-12", set reps_min and reps_max

IMPORTANT: Only respond with tool calls. No text response."""


def parse_date_blocks(text: str) -> list[tuple[date, str]]:
    blocks = []
    current_date = None
    current_lines: list[str] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        m = DATE_RE.match(line)
        if m:
            if current_date and current_lines:
                blocks.append((current_date, "\n".join(current_lines)))
            current_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            current_lines = []
        elif line:
            current_lines.append(line)

    if current_date and current_lines:
        blocks.append((current_date, "\n".join(current_lines)))

    return blocks


async def import_block(db, user_id: int, training_date: date, block_text: str) -> bool:
    prompt = f"Date: {training_date.isoformat()}\n\nWorkout record:\n{block_text}"

    messages = [
        {"role": "system", "content": IMPORT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await chat_completion(messages=messages, tools=TOOLS)
    except Exception:
        logger.exception("LLM call failed for %s", training_date)
        return False

    message = response.choices[0].message
    if not message.tool_calls:
        logger.warning("No tool calls for %s", training_date)
        return False

    for tc in message.tool_calls:
        args = json.loads(tc.function.arguments)
        if tc.function.name == "log_strength_training":
            args["date"] = training_date.isoformat()

        result = await execute_tool(db, user_id, tc.function.name, args)
        logger.info("  %s -> %s", tc.function.name, result[:200])

    await save_raw_record(db, user_id, block_text, "workout", source="historical_import")
    return True


async def run_import(line_user_id: str):
    # Seed exercises and muscle groups first
    from scripts.seed import run_seed

    await run_seed()

    text = RAW_RECORD_PATH.read_text(encoding="utf-8")
    blocks = parse_date_blocks(text)
    logger.info("Found %d date blocks to import", len(blocks))

    # Ensure user exists
    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, line_user_id)
            user_id = user.id

    success = 0
    for i, (d, block) in enumerate(blocks):
        logger.info("[%d/%d] Importing %s ...", i + 1, len(blocks), d)

        async with async_session() as db:
            async with db.begin():
                ok = await import_block(db, user_id, d, block)
                if ok:
                    success += 1

        # Rate limit between LLM calls (Gemini free tier: 15 RPM)
        await asyncio.sleep(4)

    logger.info("Import complete! %d/%d records imported.", success, len(blocks))


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    line_uid = sys.argv[1] if len(sys.argv) > 1 else "IMPORT_USER"
    asyncio.run(run_import(line_uid))
