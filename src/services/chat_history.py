"""Chat message history for multi-turn LLM conversations."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatMessage
from src.utils.time import days_ago_ts, timestamp, today_start_ts

# Reduced from 10 (20 messages) to 6 (12 messages). Gemini 2.5 Flash was
# echoing older assistant turns into new replies when the history was long;
# tighter context fits both Flash's stronger turn discrimination and our
# pattern of short LINE-chat interactions.
MAX_HISTORY_TURNS = 6


async def get_recent_messages(
    db: AsyncSession,
    user_id: int,
) -> list[dict[str, str]]:
    """Get today's recent chat messages (up to MAX_HISTORY_TURNS pairs)."""
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.created_at >= today_start_ts(),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_TURNS * 2)
    )
    rows = list(reversed(result.scalars().all()))

    return [{"role": r.role, "content": r.content} for r in rows]


async def save_message(
    db: AsyncSession,
    user_id: int,
    role: str,
    content: str,
) -> None:
    """Save a single chat message."""
    db.add(ChatMessage(user_id=user_id, role=role, content=content, created_at=timestamp()))


async def cleanup_old_messages(db: AsyncSession, days: int = 7) -> int:
    """Delete chat messages older than N days. Returns deleted count."""
    cutoff = days_ago_ts(days)
    result = await db.execute(delete(ChatMessage).where(ChatMessage.created_at < cutoff))
    return result.rowcount  # type: ignore[attr-defined,no-any-return]
