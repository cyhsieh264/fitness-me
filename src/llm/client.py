import logging

import litellm

from src.config import settings

litellm.drop_params = True

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
TIMEOUT_SECONDS = 30

# Errors we should NOT retry on. Retrying just burns more quota or repeats
# a known-bad credential. We re-raise so callers can surface a friendly
# "service paused" reply.
NON_RETRYABLE = (litellm.RateLimitError, litellm.AuthenticationError)


async def chat_completion(
    messages: list[dict],  # type: ignore[type-arg]
    tools: list[dict] | None = None,  # type: ignore[type-arg]
) -> litellm.ModelResponse:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response: litellm.ModelResponse = await litellm.acompletion(
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                messages=messages,
                tools=tools,
                temperature=0.3,
                timeout=TIMEOUT_SECONDS,
                # Gemini 2.5 Flash thinking-mode tuning.
                # - default (no flag): thinking burns the whole budget and the
                #   response often comes back empty (finish_reason=stop).
                # - reasoning_effort="disable": fixes empty output but the model
                #   starts echoing previous assistant turns into the new reply,
                #   apparently losing turn-discrimination without any thinking.
                # - reasoning_effort="minimal": small thinking budget — enough
                #   to keep turn context straight, not enough to starve output.
                #   Empirically the right band for our 2-turn tool-call pattern.
                reasoning_effort="minimal",
                max_tokens=2048,
            )
            return response
        except NON_RETRYABLE:
            # Quota / auth — propagate immediately, do not retry.
            raise
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning("LLM call attempt %d failed: %s, retrying...", attempt, e)
            else:
                logger.error("LLM call failed after %d attempts: %s", MAX_RETRIES, e)

    raise last_error  # type: ignore[misc]
