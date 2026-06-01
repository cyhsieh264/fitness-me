"""Multi-round tool-calling loop in the handler.

The contract: the model may call tools across up to MAX_TOOL_ROUNDS rounds,
reading each round's results before deciding the next call. It ends by
answering in prose (a round with no tool calls). If it hits the round cap
still wanting tools, the handler forces a final text-only summary turn.
"""

import json
import types

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.line import handler


class _FakeFn:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = _FakeFn(name, json.dumps(arguments))


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self) -> dict:
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (self.tool_calls or [])
            ],
        }


def _resp(content=None, tool_calls=None) -> types.SimpleNamespace:
    msg = _FakeMessage(content=content, tool_calls=tool_calls)
    choice = types.SimpleNamespace(message=msg, finish_reason="stop")
    return types.SimpleNamespace(choices=[choice])


def _query_call(call_id: str, name: str = "query_personal_records") -> _FakeToolCall:
    return _FakeToolCall(call_id, name, {})


async def test_adaptive_multi_round_then_answers(
    db: AsyncSession, user: User, monkeypatch
):
    """Model queries, sees the result, queries again, then answers in prose —
    all within one user turn. No summary nudge needed when it answers itself."""
    scripted = [
        _resp(tool_calls=[_query_call("c1", "query_personal_records")]),
        _resp(tool_calls=[_query_call("c2", "query_exercise_progression")]),
        _resp(content="你的硬舉進步最突出，3 個月加了 15kg。"),
    ]
    calls: list[dict] = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return scripted[len(calls) - 1]

    tool_invocations: list[str] = []

    async def fake_execute_tool(_db, _uid, tool_name, _args):
        tool_invocations.append(tool_name)
        return json.dumps({"records": []})

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(handler, "execute_tool", fake_execute_tool)

    reply = await handler._process_with_llm(db, user.id, "我哪個項目進步最突出？")

    assert reply == "你的硬舉進步最突出，3 個月加了 15kg。"
    # Two tool rounds executed, third round produced the answer.
    assert tool_invocations == ["query_personal_records", "query_exercise_progression"]
    assert len(calls) == 3
    # Every round offered tools — the model answered on its own, no nudge turn.
    assert all(c.get("tools") for c in calls)


async def test_round_cap_forces_summary_turn(
    db: AsyncSession, user: User, monkeypatch
):
    """If the model keeps asking for tools past MAX_TOOL_ROUNDS, the handler
    stops offering tools and forces one final prose summary."""
    scripted = [
        _resp(tool_calls=[_query_call("c1")]),
        _resp(tool_calls=[_query_call("c2")]),
        _resp(tool_calls=[_query_call("c3")]),
        _resp(content="這是依目前資料整理的結論。"),  # forced summary turn
    ]
    calls: list[dict] = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return scripted[len(calls) - 1]

    async def fake_execute_tool(_db, _uid, _name, _args):
        return json.dumps({"records": []})

    monkeypatch.setattr(handler, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(handler, "execute_tool", fake_execute_tool)

    reply = await handler._process_with_llm(db, user.id, "幫我分析一下")

    assert reply == "這是依目前資料整理的結論。"
    # 3 tool rounds + 1 summary turn.
    assert len(calls) == handler.MAX_TOOL_ROUNDS + 1
    # The summary turn must NOT offer tools, and must inject the query nudge.
    summary_call = calls[-1]
    assert not summary_call.get("tools")
    assert summary_call["messages"][-1]["content"] == handler.TURN2_PROMPT_QUERY
