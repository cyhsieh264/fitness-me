"""Tests for chat message history."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatMessage, User
from src.services.chat_history import cleanup_old_messages, get_recent_messages, save_message
from src.utils.time import days_ago_ts


async def test_save_and_get_messages(db: AsyncSession, user: User):
    await save_message(db, user.id, "user", "Hello")
    await save_message(db, user.id, "assistant", "Hi there!")
    await db.flush()

    messages = await get_recent_messages(db, user.id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


async def test_get_messages_respects_limit(db: AsyncSession, user: User):
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        await save_message(db, user.id, role, f"msg {i}")
    await db.flush()

    messages = await get_recent_messages(db, user.id)
    assert len(messages) <= 20  # MAX_HISTORY_TURNS * 2


async def test_cleanup_old_messages(db: AsyncSession, user: User):
    # Add an old message (8 days ago)
    old_msg = ChatMessage(user_id=user.id, role="user", content="old", created_at=days_ago_ts(8))
    db.add(old_msg)

    # Add a recent message
    await save_message(db, user.id, "user", "recent")
    await db.flush()

    deleted = await cleanup_old_messages(db, days=7)
    assert deleted == 1

    messages = await get_recent_messages(db, user.id)
    assert len(messages) == 1
    assert messages[0]["content"] == "recent"
