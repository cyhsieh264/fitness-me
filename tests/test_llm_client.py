"""Tests for the LLM client's retry / empty-response re-sampling logic.

Gemini 2.5 Flash intermittently returns finish_reason=stop with neither text
content nor tool calls. chat_completion should re-sample such responses while
attempts remain, retry on transient exceptions, and never crash the caller.
"""

import types

import pytest

from src.llm import client


def _resp(content=None, tool_calls=None, has_choices=True):
    """Build a minimal stand-in for a litellm ModelResponse."""
    message = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = types.SimpleNamespace(message=message, finish_reason="stop")
    return types.SimpleNamespace(choices=[choice] if has_choices else [])


def _patch_sequence(monkeypatch, responses):
    """Patch litellm.acompletion to yield each response in turn; count calls."""
    state = {"n": 0}

    async def fake_acompletion(**_kwargs):
        i = state["n"]
        state["n"] += 1
        item = responses[i]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client.litellm, "acompletion", fake_acompletion)
    return state


async def test_resamples_empty_then_returns_usable(monkeypatch):
    state = _patch_sequence(monkeypatch, [_resp(), _resp(), _resp(content="hello")])
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 3
    assert result.choices[0].message.content == "hello"


async def test_all_empty_returns_last_without_raising(monkeypatch):
    state = _patch_sequence(monkeypatch, [_resp(), _resp(), _resp()])
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    # Exhausts retries and hands back the empty response so the caller's
    # canned fallback kicks in rather than raising.
    assert state["n"] == client.MAX_RETRIES
    assert client._is_usable(result) is False


async def test_tool_call_only_is_usable(monkeypatch):
    state = _patch_sequence(
        monkeypatch, [_resp(tool_calls=[types.SimpleNamespace(id="t1")])]
    )
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 1
    assert client._is_usable(result) is True


async def test_retries_transient_exception(monkeypatch):
    state = _patch_sequence(monkeypatch, [RuntimeError("timeout"), _resp(content="ok")])
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 2
    assert result.choices[0].message.content == "ok"


async def test_no_choices_is_resampled(monkeypatch):
    state = _patch_sequence(
        monkeypatch, [_resp(has_choices=False), _resp(content="recovered")]
    )
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 2
    assert result.choices[0].message.content == "recovered"


async def test_non_retryable_propagates_immediately(monkeypatch):
    state = _patch_sequence(
        monkeypatch, [client.litellm.AuthenticationError("bad key", "gemini", "x")]
    )
    with pytest.raises(client.litellm.AuthenticationError):
        await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 1


async def test_retry_steps_down_reasoning_effort(monkeypatch):
    """Step the thinking budget DOWN on retry: low -> minimal -> disable, with
    output room (max_tokens) always above the thinking budget so thinking can't
    starve the answer. Lock the sequence in so a casual edit to ATTEMPT_OVERRIDES
    that reintroduces the starve-the-output / leak-prone config fails here.
    """
    seen_efforts: list[str] = []
    seen_max_tokens: list[int] = []

    async def fake_acompletion(**kwargs):
        seen_efforts.append(kwargs.get("reasoning_effort"))
        seen_max_tokens.append(kwargs.get("max_tokens"))
        return _resp()  # always empty, forces all 3 attempts

    monkeypatch.setattr(client.litellm, "acompletion", fake_acompletion)
    await client.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert seen_efforts == ["low", "minimal", "disable"]
    assert seen_max_tokens == [3072, 2048, 1024]


# A leaked tool-call dumped into text instead of a structured function call.
_LEAKED = "```tool_code\nprint(default_api.update_daily_plan(user_plan='rest'))\n```"


def test_leaked_scaffolding_is_not_usable():
    """Content that is leaked tool-call grammar must count as unusable, so the
    retry loop re-samples it before the handler ever sees it."""
    assert client._is_usable(_resp(content=_LEAKED)) is False
    # A real structured tool call alongside is still usable.
    assert (
        client._is_usable(
            _resp(content=_LEAKED, tool_calls=[types.SimpleNamespace(id="t1")])
        )
        is True
    )


async def test_resamples_leaked_then_returns_clean(monkeypatch):
    """The one-shot-LINE guarantee: a leak on attempt 1 is re-sampled and the
    clean completion is what comes back — the leak never escapes the client."""
    state = _patch_sequence(
        monkeypatch, [_resp(content=_LEAKED), _resp(content="好的，今天休息！")]
    )
    result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert state["n"] == 2
    assert result.choices[0].message.content == "好的，今天休息！"
