"""Daily push notification with LLM-generated greeting."""

import logging

from sqlalchemy import select

from src.db.database import async_session
from src.db.models import DailyInteraction
from src.line.handler import push_text
from src.llm.client import chat_completion
from src.services.chat_history import save_message
from src.services.recommender import build_recommendation_context
from src.services.user import get_user_by_line_id
from src.utils.time import timestamp, today

logger = logging.getLogger(__name__)

DAILY_PUSH_PROMPT = """\
You are a personal fitness assistant LINE Bot.
Generate a short, friendly morning greeting in Traditional Chinese.

Based on the user's recent training context below, ask what their plan is for today.
Include these options naturally in your message:
- self training / coach session / rest / other exercise

Keep it under 100 characters. Be warm and encouraging.
If they trained hard recently, acknowledge it. If they rested, that's fine too.

Context:
{context}"""


async def send_daily_push(line_user_id: str) -> None:
    """Send LLM-generated daily push and create daily_interaction record."""
    async with async_session() as db:
        async with db.begin():
            user = await get_user_by_line_id(db, line_user_id)
            if not user:
                logger.warning("User not found for daily push: %s", line_user_id)
                return

            # Skip if already sent today (prevents duplicate from race conditions)
            existing = await db.execute(
                select(DailyInteraction).where(
                    DailyInteraction.user_id == user.id,
                    DailyInteraction.date == today(),
                )
            )
            if existing.first():
                logger.info("Daily push already sent to %s today, skipping", line_user_id)
                return

            context = await build_recommendation_context(db, user.id)
            greeting = await _generate_greeting(context)

            # Persist the push: both the daily_interactions audit row
            # (push_sent_at + bot_suggestion) and the chat_messages
            # entry so the LLM sees its own greeting when the user
            # replies later in the day.
            interaction = DailyInteraction(
                user_id=user.id,
                date=today(),
                push_sent_at=timestamp(),
                bot_suggestion=greeting,
            )
            db.add(interaction)
            await save_message(db, user.id, "assistant", greeting)

    await push_text(line_user_id, greeting)
    logger.info("Daily push sent to %s", line_user_id)


async def _generate_greeting(context: str) -> str:
    """Use LLM to generate a context-aware daily greeting."""
    prompt = DAILY_PUSH_PROMPT.format(context=context)
    messages: list[dict] = [  # type: ignore[type-arg]
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Generate today's morning greeting."},
    ]

    try:
        response = await chat_completion(messages=messages)
        content = response.choices[0].message.content
        return content or _fallback_greeting()
    except Exception:
        logger.exception("Failed to generate daily greeting")
        return _fallback_greeting()


def _fallback_greeting() -> str:
    return "早安！今天有什麼運動計畫呢？自主訓練、教練課、還是休息日？"
