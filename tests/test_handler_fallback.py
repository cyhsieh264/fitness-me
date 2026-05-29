"""Spec-004 §7.6.4: rule-based daily-push fallback when LLM returns empty.

The contract: if Gemini returns silence AND there's a pending daily push,
the handler must (a) classify the user's text into a plan, (b) call
update_daily_plan so the push is no longer "pending", and (c) reply with
a stock zh-TW line. Never let the user see EMPTY_RESPONSE_MESSAGE in this
state.
"""

import types

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DailyInteraction, User
from src.line import handler
from src.utils.time import timestamp, today


def _empty_response() -> types.SimpleNamespace:
    """A litellm-shaped response that the handler should treat as 'silence'."""
    message = types.SimpleNamespace(content=None, tool_calls=None)
    choice = types.SimpleNamespace(message=message, finish_reason="stop")
    return types.SimpleNamespace(choices=[choice])


@pytest.fixture
async def pending_push(db: AsyncSession, user: User) -> DailyInteraction:
    """Seed a 'morning push went out, user hasn't replied yet' row."""
    di = DailyInteraction(
        user_id=user.id,
        date=today(),
        push_sent_at=timestamp(),
        user_plan=None,
        user_response=None,
        responded_at=None,
    )
    db.add(di)
    await db.flush()
    return di


@pytest.mark.parametrize(
    "user_text,expected_plan",
    [
        ("肌肉酸痛 休息", "rest"),
        ("今天休息一下", "rest"),
        ("今天教練課", "coach"),
        ("PT 11:00", "coach"),
        ("自己練", "self_training"),
        ("自主訓練", "self_training"),
        ("約朋友打網球", "other"),
    ],
)
def test_classify_daily_push_keywords(user_text: str, expected_plan: str):
    assert handler._classify_daily_push(user_text) == expected_plan


async def test_empty_llm_with_pending_push_records_plan_and_replies(
    db: AsyncSession,
    user: User,
    pending_push: DailyInteraction,
    monkeypatch,
):
    async def fake_chat_completion(**_kwargs):
        return _empty_response()

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)

    reply = await handler._process_with_llm(db, user.id, "肌肉酸痛 休息")

    assert reply == handler._DAILY_PUSH_FALLBACK_REPLY["rest"]

    await db.refresh(pending_push)
    assert pending_push.user_plan == "rest"
    assert pending_push.user_response == "肌肉酸痛 休息"
    assert pending_push.responded_at is not None


async def test_empty_llm_without_pending_push_falls_back_to_canned(
    db: AsyncSession,
    user: User,
    monkeypatch,
):
    """No pending push -> no plan to classify -> the canned EMPTY message."""

    async def fake_chat_completion(**_kwargs):
        return _empty_response()

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)

    reply = await handler._process_with_llm(db, user.id, "肌肉酸痛 休息")
    assert reply == handler.EMPTY_RESPONSE_MESSAGE


async def test_empty_llm_with_pending_push_other_plan(
    db: AsyncSession,
    user: User,
    pending_push: DailyInteraction,
    monkeypatch,
):
    """Unclassifiable wording still records *something* — never leaves the
    interaction pending forever."""

    async def fake_chat_completion(**_kwargs):
        return _empty_response()

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)

    reply = await handler._process_with_llm(db, user.id, "今天看心情")
    assert reply == handler._DAILY_PUSH_FALLBACK_REPLY["other"]

    await db.refresh(pending_push)
    assert pending_push.user_plan == "other"
    assert pending_push.responded_at is not None
