import logging

import litellm

from src.config import settings

litellm.drop_params = True

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30

# Per-attempt parameter overrides. We LEAD with real reasoning budget so the
# model can actually think like a coach (weigh the member's data, pick what to
# say) instead of pattern-matching a canned reply — attempt 1 gets full effort
# plus headroom so thinking doesn't starve the output.
#
# The ladder still steps DOWN on retry as a recovery mechanism: identical
# retries at the same budget tend to repeat the same Gemini Flash failure mode
# (finish_reason=stop with empty content because thinking burned the budget
# before any output). So if attempt 1 comes back empty, attempt 2 drops the
# budget, and attempt 3 disables thinking entirely to guarantee SOMETHING ships.
ATTEMPT_OVERRIDES: list[dict] = [  # type: ignore[type-arg]
    {"reasoning_effort": "high",    "max_tokens": 4096},  # attempt 1: reason fully
    {"reasoning_effort": "low",     "max_tokens": 2048},  # attempt 2: step down
    {"reasoning_effort": "disable", "max_tokens": 1024},  # attempt 3: guarantee output
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
