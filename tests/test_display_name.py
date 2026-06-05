"""Display-name backfill: fetch the LINE profile name for users missing one.

Webhook events carry only the user id, so display_name needs an explicit
Get Profile call. The backfill must be best-effort: an API failure logs and
moves on — never blocks the message flow.
"""

import types

from src.line import handler
from src.llm.prompts import build_system_prompt, PromptContext


class _FakeApi:
    def __init__(self, api_client):
        pass

    async def get_profile(self, line_user_id: str):
        return types.SimpleNamespace(display_name="佳儀")


class _FailingApi:
    def __init__(self, api_client):
        pass

    async def get_profile(self, line_user_id: str):
        raise RuntimeError("user blocked the bot")


async def test_backfill_sets_missing_display_name(monkeypatch):
    monkeypatch.setattr(handler, "AsyncMessagingApi", _FakeApi)
    user = types.SimpleNamespace(display_name=None)
    await handler._backfill_display_name(user, "U_TEST_001")
    assert user.display_name == "佳儀"


async def test_backfill_skips_user_with_name(monkeypatch):
    """No Get Profile call when the name is already known."""

    def _explode(*args, **kwargs):
        raise AssertionError("Get Profile must not be called")

    monkeypatch.setattr(handler, "AsyncMessagingApi", _explode)
    user = types.SimpleNamespace(display_name="既有名字")
    await handler._backfill_display_name(user, "U_TEST_001")
    assert user.display_name == "既有名字"


async def test_backfill_swallows_api_failure(monkeypatch):
    monkeypatch.setattr(handler, "AsyncMessagingApi", _FailingApi)
    user = types.SimpleNamespace(display_name=None)
    await handler._backfill_display_name(user, "U_TEST_001")
    assert user.display_name is None


def test_display_name_renders_in_system_prompt():
    ctx = PromptContext(
        today_iso="2026-06-05",
        timezone="Asia/Taipei",
        profile_summary={"display_name": "佳儀", "latest_weight_kg": 55.0},
        latest_weight_recorded=True,
    )
    assert "- display_name: 佳儀" in build_system_prompt(ctx)
