"""Historical record import via LLM parsing."""

import asyncio
import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy import select

from src.db.database import async_session
from src.db.models import TrainingSession
from src.llm.client import chat_completion
from src.llm.tool_executor import execute_tool
from src.llm.tools import TOOLS
from src.services.user import get_or_create_user
from src.services.workout import save_raw_record

logger = logging.getLogger(__name__)

# Optional `(self)` / `(coach)` / `(other)` tag right after the date.
# No tag -> DEFAULT_SESSION_TYPE.
DATE_RE = re.compile(
    r"^(\d{4})/(\d{2})/(\d{2})(?:\s+\((self|coach|other)\))?\s*$"
)
DEFAULT_SESSION_TYPE = "self_training"
_TAG_TO_SESSION_TYPE = {
    "self": "self_training",
    "coach": "coach",
    "other": "other",
}

IMPORT_SYSTEM_PROMPT = """\
You are importing historical workout records into a database.
Parse the workout text and call the appropriate tools.

Rules:
- Use log_strength_training for exercise data
- Use log_user_condition for body condition/posture/weakness observations
- The date AND session_type are given in the prompt. Always use both in the
  log_strength_training tool call exactly as provided — do NOT infer
  session_type from the workout content.
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
) -> list[tuple[date, str, str]]:
    """Split text into (date, body, session_type) tuples.

    Each block starts with `YYYY/MM/DD` optionally followed by
    `(self|coach|other)`. Missing tag falls back to DEFAULT_SESSION_TYPE.
    """
    cutoff = date.today() - timedelta(days=cutoff_years * 365)
    blocks: list[tuple[date, str, str]] = []
    current_date: date | None = None
    current_session_type: str = DEFAULT_SESSION_TYPE
    current_lines: list[str] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        m = DATE_RE.match(line)
        if m:
            if current_date and current_lines:
                blocks.append(
                    (current_date, "\n".join(current_lines), current_session_type)
                )
            current_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            tag = m.group(4)
            current_session_type = (
                _TAG_TO_SESSION_TYPE[tag] if tag else DEFAULT_SESSION_TYPE
            )
            current_lines = []
        elif line:
            current_lines.append(line)

    if current_date and current_lines:
        blocks.append((current_date, "\n".join(current_lines), current_session_type))

    # Filter by cutoff
    filtered = [(d, b, st) for d, b, st in blocks if d >= cutoff]
    if len(filtered) < len(blocks):
        logger.info(
            "Filtered out %d blocks older than %s",
            len(blocks) - len(filtered), cutoff,
        )
    return filtered


async def import_block(
    db,
    user_id: int,
    training_date: date,
    block_text: str,
    session_type: str = DEFAULT_SESSION_TYPE,
) -> bool:
    prompt = (
        f"Date: {training_date.isoformat()}\n"
        f"session_type: {session_type}\n\n"
        f"Workout record:\n{block_text}"
    )

    messages = [
        {"role": "system", "content": IMPORT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await chat_completion(messages=messages, tools=TOOLS)
    except Exception:
        logger.exception("LLM call failed for %s", training_date)
        return False

    if not response.choices:
        logger.warning("LLM returned no choices for %s", training_date)
        return False

    message = response.choices[0].message
    if not message.tool_calls:
        logger.warning("No tool calls for %s", training_date)
        return False

    for tc in message.tool_calls:
        args = json.loads(tc.function.arguments)
        if tc.function.name in ("log_strength_training", "log_user_condition"):
            args["date"] = training_date.isoformat()
        # Force the import-side session_type onto strength logs so the LLM
        # can't quietly downgrade an "教練課" block to "self_training".
        if tc.function.name == "log_strength_training":
            args["session_type"] = session_type

        result = await execute_tool(db, user_id, tc.function.name, args)
        logger.info("  %s -> %s", tc.function.name, result[:200])

    await save_raw_record(db, user_id, block_text, "workout", source="historical_import")
    return True


async def run_import(
    line_user_id: str,
    raw_text: str,
    cutoff_years: int = DEFAULT_CUTOFF_YEARS,
) -> dict[str, int]:
    """Import historical records from raw text.

    Idempotent on a per-date basis: any block whose date already has a
    `training_sessions` row for this user is skipped (no LLM call, no
    INSERTs). To re-import a corrected version of an existing date, use
    /admin/delete-records first.

    Returns counts: {"new", "already_existed", "llm_failed", "total"}.
    """
    blocks = parse_date_blocks(raw_text, cutoff_years)
    logger.info("Found %d date blocks to import", len(blocks))

    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, line_user_id)
            user_id = user.id

            block_dates = [d for d, _, _ in blocks]
            existing = set()
            if block_dates:
                result = await db.execute(
                    select(TrainingSession.date).where(
                        TrainingSession.user_id == user_id,
                        TrainingSession.date.in_(block_dates),
                    )
                )
                existing = {row for row in result.scalars().all()}

    new_blocks = sorted(
        ((d, b, st) for d, b, st in blocks if d not in existing),
        key=lambda triple: triple[0],
    )
    already_existed = len(blocks) - len(new_blocks)
    if already_existed:
        logger.info("Skipping %d blocks whose date already has a session", already_existed)

    success = 0
    for i, (d, block, session_type) in enumerate(new_blocks):
        logger.info(
            "[%d/%d] Importing %s (%s) ...", i + 1, len(new_blocks), d, session_type
        )

        async with async_session() as db:
            async with db.begin():
                ok = await import_block(db, user_id, d, block, session_type)
                if ok:
                    success += 1

        if i < len(new_blocks) - 1:
            await asyncio.sleep(LLM_RATE_LIMIT_SEC)

    llm_failed = len(new_blocks) - success
    counts = {
        "new": success,
        "already_existed": already_existed,
        "llm_failed": llm_failed,
        "total": len(blocks),
    }
    logger.info("Import done: %s", counts)
    return counts
