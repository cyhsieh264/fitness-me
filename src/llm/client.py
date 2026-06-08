import logging

import litellm

from src.config import settings
from src.llm.sanitize import contains_tool_scaffolding

litellm.drop_params = True

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30

# Per-attempt parameter overrides for Gemini's thinking config (litellm maps
# reasoning_effort -> thinkingBudget). Two facts drive this ladder:
#
# 1. Thinking tokens are drawn from the SAME max_tokens budget as the answer.
#    Leading with high (thinkingBudget≈4096) and max_tokens=4096 lets thinking
#    starve the output to nothing — the empty-completion failure mode. So every
#    rung keeps max_tokens well ABOVE the thinking budget, leaving room to
#    actually answer.
# 2. reasoning_effort low/medium/high all set includeThoughts=True, i.e. they
#    ask Gemini to RETURN its reasoning — the raw material of the tool_code /
#    thought leak. We never read reasoning_content, so thoughts buy us nothing
#    and only add leak surface. Stepping down to "disable" (includeThoughts=
#    False, no thinking) removes that surface entirely.
#
# The ladder also recovers on retry: a leaked or empty attempt re-samples with
# LESS thinking (see _is_usable), and identical-budget retries tend to repeat
# the same Flash failure — so each rung steps down. Attempt 3 disables thinking
# outright to guarantee a clean, leak-free completion ships.
ATTEMPT_OVERRIDES: list[dict] = [  # type: ignore[type-arg]
    {"reasoning_effort": "low",     "max_tokens": 3072},  # think lightly, ample output room
    {"reasoning_effort": "minimal", "max_tokens": 2048},  # step down
    {"reasoning_effort": "disable", "max_tokens": 1024},  # no thinking -> no leak, guarantee output
]
MAX_RETRIES = len(ATTEMPT_OVERRIDES)

# Errors we should NOT retry on. Retrying just burns more quota or repeats
# a known-bad credential. We re-raise so callers can surface a friendly
# "service paused" reply.
NON_RETRYABLE = (litellm.RateLimitError, litellm.AuthenticationError)


def _is_usable(response: litellm.ModelResponse) -> bool:
    """Whether the response carries something a caller can act on.

    Unusable (and therefore re-sampled while attempts remain) when EITHER:
    - Gemini 2.5 Flash returned finish_reason=stop with neither text nor tool
      calls — dead weight, callers could only fall back to a canned message; or
    - the model leaked its tool-call grammar into the text instead of emitting
      a real function call (see sanitize.contains_tool_scaffolding). Because
      LINE replies are one-shot, re-sampling NOW — before the handler ships
      anything — is how we turn an internal-disclosure bug into a silent retry
      the user never sees. A genuine tool_calls payload is always usable.
    """
    if not response.choices:
        return False
    message = response.choices[0].message
    if message.tool_calls:
        return True
    content = message.content or ""
    if not content:
        return False
    return not contains_tool_scaffolding(content)


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
