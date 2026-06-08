"""Guard against Gemini leaking its tool-call grammar into the reply text.

Background: Gemini Flash intermittently fails to emit a structured function
call and instead dumps the call — plus its private chain-of-thought — into the
message content as a ```tool_code fence + `default_api.<tool>(...)` + `thought`
block. Shipping that text leaks internal tool names and reasoning to the user.

These tests lock in two layers of defense:
  1. contains_tool_scaffolding -> the handler discards such a turn and routes
     it to the empty-response fallback (so a daily-push reply still records the
     plan and answers with a clean canned line).
  2. strip_model_scaffolding -> the outbound chokepoint scrubs any residual
     scaffolding, so no code path can leak it to LINE.
"""

import types

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DailyInteraction, User
from src.line import handler
from src.line.handler import _build_messages
from src.llm.sanitize import contains_tool_scaffolding, strip_model_scaffolding
from src.utils.time import timestamp, today

# The exact shape observed in production: a tool_code fence, a default_api call,
# a leaked `thought` block running straight into the real reply (no separator).
LEAKED_REPLY = (
    "```tool_code\n"
    "print(default_api.update_daily_plan(user_plan='rest', "
    "user_response='今天下雨休息'))\n"
    "```\n"
    "thought\n"
    "The user explicitly states they want to rest.好的，今天下雨就好好休息吧！\n"
    "\n"
    "休息日可以做些輕度的伸展，多補充水分喔。"
)

# Substrings that must NEVER reach the user.
_FORBIDDEN = ["default_api", "tool_code", "tool_outputs", "print("]


def _assert_no_leak(text: str) -> None:
    for marker in _FORBIDDEN:
        assert marker not in text, f"leaked {marker!r} in: {text!r}"


class TestContainsToolScaffolding:
    def test_detects_production_sample(self):
        assert contains_tool_scaffolding(LEAKED_REPLY)

    def test_detects_default_api_call(self):
        assert contains_tool_scaffolding(
            "print(default_api.log_cardio(cardio_type='running'))"
        )

    def test_detects_bare_tool_code_label(self):
        # The case after strip_markdown has already eaten the ``` fence.
        assert contains_tool_scaffolding("tool_code\nprint(default_api.foo())")

    def test_detects_tool_outputs_fence(self):
        assert contains_tool_scaffolding("```tool_outputs\n{...}\n```")

    def test_normal_reply_is_clean(self):
        assert not contains_tool_scaffolding(
            "好的，今天休息！記得伸展放鬆，多補水 💧"
        )

    def test_workout_notation_is_clean(self):
        assert not contains_tool_scaffolding("深蹲 40kg*10*4\n臥推 9kg each*12*3")

    def test_image_tag_is_clean(self):
        assert not contains_tool_scaffolding(
            "上次的 InBody:\n[IMAGE:https://example.com/i/1/abc123]"
        )


class TestStripModelScaffolding:
    def test_removes_fenced_block_keeps_real_reply(self):
        out = strip_model_scaffolding(LEAKED_REPLY)
        _assert_no_leak(out)
        assert "好好休息吧" in out
        assert "輕度的伸展" in out

    def test_removes_unterminated_fence_to_eof(self):
        text = (
            "```tool_code\n"
            "print(default_api.update_daily_plan(user_plan='rest'))"
        )
        assert strip_model_scaffolding(text).strip() == ""

    def test_removes_bare_default_api_line(self):
        text = "好的！\nprint(default_api.log_cardio(cardio_type='running'))\n收工"
        out = strip_model_scaffolding(text)
        _assert_no_leak(out)
        assert "好的！" in out
        assert "收工" in out

    def test_clean_reply_untouched(self):
        text = "深蹲 40kg*10*4\n臥推 9kg each*12*3"
        assert strip_model_scaffolding(text) == text


class TestBuildMessagesScrubsScaffolding:
    """End-to-end: even if the handler missed it, the send chokepoint is clean."""

    def test_leaked_reply_never_reaches_a_message(self):
        messages = _build_messages(LEAKED_REPLY)
        for m in messages:
            _assert_no_leak(getattr(m, "text", ""))
        # The genuine reply tail still survives.
        joined = "\n".join(getattr(m, "text", "") for m in messages)
        assert "好好休息吧" in joined


@pytest.fixture
async def pending_push(db: AsyncSession, user: User) -> DailyInteraction:
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


def _scaffold_response() -> types.SimpleNamespace:
    """A litellm-shaped response carrying leaked scaffolding as content."""
    message = types.SimpleNamespace(content=LEAKED_REPLY, tool_calls=None)
    choice = types.SimpleNamespace(message=message, finish_reason="stop")
    return types.SimpleNamespace(choices=[choice])


async def test_leaked_reply_with_pending_push_records_plan_and_stays_clean(
    db: AsyncSession,
    user: User,
    pending_push: DailyInteraction,
    monkeypatch,
):
    """The production scenario: leaked scaffolding on a daily-push reply must
    record the plan via the fallback and answer with a clean canned line —
    never the leaked text."""

    async def fake_chat_completion(**_kwargs):
        return _scaffold_response()

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)

    reply = await handler._process_with_llm(db, user.id, "今天下雨休息")

    _assert_no_leak(reply)
    assert reply == handler._DAILY_PUSH_FALLBACK_REPLY["rest"]

    await db.refresh(pending_push)
    assert pending_push.user_plan == "rest"
    assert pending_push.responded_at is not None


async def test_leaked_reply_without_pending_push_falls_back_clean(
    db: AsyncSession,
    user: User,
    monkeypatch,
):
    """No pending push -> nothing to record -> the canned EMPTY message, but
    crucially never the leaked scaffolding."""

    async def fake_chat_completion(**_kwargs):
        return _scaffold_response()

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)

    reply = await handler._process_with_llm(db, user.id, "幫我看看深蹲紀錄")

    _assert_no_leak(reply)
    assert reply == handler.EMPTY_RESPONSE_MESSAGE
