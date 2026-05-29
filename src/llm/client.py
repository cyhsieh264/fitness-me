import logging

import litellm

from src.config import settings

litellm.drop_params = True

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30

# Per-attempt parameter overrides. Identical retries with the same
# reasoning budget tend to hit the same Gemini 2.5 Flash failure mode
# (finish_reason=stop with empty content because thinking burns the
# budget before any output is emitted). Stepping the budget down on each
# retry trades reasoning quality for "actually returns something".
# Attempt-3 also caps max_tokens to discourage runaway thinking.
ATTEMPT_OVERRIDES: list[dict] = [  # type: ignore[type-arg]
    {"reasoning_effort": "low",     "max_tokens": 2048},  # attempt 1
    {"reasoning_effort": "minimal", "max_tokens": 2048},  # attempt 2
    {"reasoning_effort": "disable", "max_tokens": 1024},  # attempt 3
]
MAX_RETRIES = len(ATTEMPT_OVERRIDES)

# Errors we should NOT retry on. Retrying just burns more quota or repeats
# a known-bad credential. We re-raise so callers can surface a friendly
# "service paused" reply.
NON_RETRYABLE = (litellm.RateLimitError, litellm.AuthenticationError)


def _is_usable(response: litellm.ModelResponse) -> bool:
    """Whether the response carries something a caller can act on.

    Gemini 2.5 Flash intermittently returns finish_reason=stop with neither
    text content nor tool calls. Such a response is dead weight — callers can
    only fall back to a canned message — so we treat it as retryable.
    """
    if not response.choices:
        return False
    message = response.choices[0].message
    return bool(message.content or message.tool_calls)


async def chat_completion(
    messages: list[dict],  # type: ignore[type-arg]
    tools: list[dict] | None = None,  # type: ignore[type-arg]
) -> litellm.ModelResponse:
    last_error: Exception | None = None

    for attempt, overrides in enumerate(ATTEMPT_OVERRIDES, start=1):
        try:
            response: litellm.ModelResponse = await litellm.acompletion(
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                messages=messages,
                tools=tools,
                temperature=0.3,
                timeout=TIMEOUT_SECONDS,
                **overrides,
            )
        except NON_RETRYABLE:
            # Quota / auth — propagate immediately, do not retry.
            raise
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning("LLM call attempt %d failed: %s, retrying...", attempt, e)
            else:
                logger.error("LLM call failed after %d attempts: %s", MAX_RETRIES, e)
            continue

        # Re-sample empty responses while attempts remain; on the final
        # attempt hand the empty response back so the caller's fallback
        # message still kicks in rather than raising.
        if _is_usable(response) or attempt == MAX_RETRIES:
            return response
        logger.warning(
            "LLM returned unusable (empty) response on attempt %d/%d "
            "(effort=%s) — retrying with stepped-down params",
            attempt,
            MAX_RETRIES,
            overrides.get("reasoning_effort"),
        )

    raise last_error  # type: ignore[misc]
