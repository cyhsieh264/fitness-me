import logging

import litellm

from src.config import settings

litellm.drop_params = True

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
TIMEOUT_SECONDS = 30


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
            )
            return response
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning("LLM call attempt %d failed: %s, retrying...", attempt, e)
            else:
                logger.error("LLM call failed after %d attempts: %s", MAX_RETRIES, e)

    raise last_error  # type: ignore[misc]
