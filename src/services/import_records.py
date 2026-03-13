"""Historical record import via LLM parsing."""

import asyncio
import json
import logging
import re
from datetime import date, timedelta

from src.db.database import async_session
from src.llm.client import chat_completion
from src.llm.tool_executor import execute_tool
from src.llm.tools import TOOLS
from src.services.user import get_or_create_user
from src.services.workout import save_raw_record

logger = logging.getLogger(__name__)

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

DEFAULT_CUTOFF_YEARS = 2
LLM_RATE_LIMIT_SEC = 4


def parse_date_blocks(
    text: str,
    cutoff_years: int = DEFAULT_CUTOFF_YEARS,
) -> list[tuple[date, str]]:
    cutoff = date.today() - timedelta(days=cutoff_years * 365)
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

    # Filter by cutoff
    filtered = [(d, b) for d, b in blocks if d >= cutoff]
    if len(filtered) < len(blocks):
        logger.info(
            "Filtered out %d blocks older than %s",
            len(blocks) - len(filtered), cutoff,
        )
    return filtered


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


async def run_import(line_user_id: str, raw_text: str, cutoff_years: int = DEFAULT_CUTOFF_YEARS):
    """Import historical records from raw text. Returns (success, total) counts."""
    blocks = parse_date_blocks(raw_text, cutoff_years)
    logger.info("Found %d date blocks to import", len(blocks))

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

        if i < len(blocks) - 1:
            await asyncio.sleep(LLM_RATE_LIMIT_SEC)

    logger.info("Import complete! %d/%d records imported.", success, len(blocks))
    return success, len(blocks)
