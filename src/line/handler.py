import json
import logging
import re
import time

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    ImageMessage,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.whitelist import is_user_allowed
from src.config import settings
from src.db.database import async_session
from src.llm.client import chat_completion
from src.llm.prompts import SYSTEM_PROMPT
from src.llm.tool_executor import execute_tool
from src.llm.tools import TOOLS
from src.llm.vision import classify_and_parse_image
from src.services.chat_history import get_recent_messages, save_message
from src.services.goals import get_active_goals
from src.services.images import save_image
from src.services.profile import get_profile_summary
from src.services.recommender import get_pending_daily_interaction, save_bot_suggestion
from src.services.user import get_or_create_user
from src.services.workout import save_raw_record

logger = logging.getLogger(__name__)

LINE_MESSAGE_MAX_LENGTH = 5000
REPLY_TOKEN_TIMEOUT_SEC = 25

DAILY_PUSH_CONTEXT = """

DAILY PUSH RESPONSE:
A daily push greeting was sent to the user this morning. They are now replying.
Determine their plan from their reply and call update_daily_plan:
- Training/workout alone -> user_plan = "self_training"
- Coach/trainer session -> user_plan = "coach"
- Rest/off day -> user_plan = "rest"
- Other sports/activities -> user_plan = "other"

If the result includes recommendation_context (for self_training), use it to suggest
a workout plan. Consider which muscle groups were trained recently (avoid same muscles
within 48h), any active conditions, and their fitness goals.
"""

configuration = Configuration(access_token=settings.line_channel_access_token)


async def handle_text_message(event: MessageEvent) -> None:
    start = time.monotonic()
    line_user_id = event.source.user_id
    text = event.message.text
    reply_token = event.reply_token

    if not is_user_allowed(line_user_id):
        await _reply_text(reply_token, "Sorry, you are not authorized to use this bot.")
        return

    logger.info("Message from %s: %s", line_user_id, text)

    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, line_user_id)
            reply = await _process_with_llm(db, user.id, text)

    await _send_reply(line_user_id, reply_token, reply, start)


async def _process_with_llm(db: AsyncSession, user_id: int, text: str) -> str:
    system_prompt = SYSTEM_PROMPT

    # Inject user profile into system prompt
    profile = await get_profile_summary(db, user_id)
    profile_parts = [f"- {k}: {v}" for k, v in profile.items() if v is not None]
    if profile_parts:
        system_prompt += "\n\nUSER PROFILE:\n" + "\n".join(profile_parts)

    # Inject active goals into system prompt
    active_goals = await get_active_goals(db, user_id)
    if active_goals:
        goal_lines = []
        for g in active_goals:
            line = f"- [id={g['id']}] ({g['category']}) {g['description']}"
            if g.get("target_value"):
                line += f" target={g['target_value']}{g.get('target_unit', '')}"
            goal_lines.append(line)
        system_prompt += "\n\nACTIVE GOALS:\n" + "\n".join(goal_lines)

    # Check for pending daily push interaction
    pending = await get_pending_daily_interaction(db, user_id)
    if pending:
        system_prompt += DAILY_PUSH_CONTEXT

    # Build messages with chat history
    history = await get_recent_messages(db, user_id)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]  # type: ignore[type-arg]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    try:
        response = await chat_completion(messages=messages, tools=TOOLS)
    except Exception:
        logger.exception("LLM call failed")
        return "Something went wrong, please try again."

    message = response.choices[0].message
    tool_calls = message.tool_calls

    if not tool_calls:
        reply = message.content or "..."
        await save_message(db, user_id, "user", text)
        await save_message(db, user_id, "assistant", reply)
        return reply

    # Execute tool calls and collect results
    messages.append(message.model_dump())

    has_db_write = False
    has_daily_plan = False
    for tc in tool_calls:
        try:
            arguments = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            logger.warning("Malformed tool arguments: %s", tc.function.arguments)
            arguments = {}

        logger.info("Tool call: %s(%s)", tc.function.name, arguments)

        tool_name = tc.function.name or ""
        result = await execute_tool(db, user_id, tool_name, arguments)

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            }
        )

        if tool_name.startswith(("log_", "update_", "resolve_", "manage_goal")):
            has_db_write = True
        if tool_name == "update_daily_plan":
            has_daily_plan = True

    # Save raw record if any DB write happened (skip for daily plan updates)
    if has_db_write and not has_daily_plan:
        record_type = _infer_record_type(tool_calls)
        await save_raw_record(db, user_id, text, record_type)

    # Turn 2: LLM generates final response from tool results
    try:
        response2 = await chat_completion(messages=messages)
    except Exception:
        logger.exception("LLM turn 2 failed")
        return "Recorded, but failed to generate summary."

    final_reply = response2.choices[0].message.content or "Done."

    # Save bot suggestion if daily plan was updated
    if has_daily_plan:
        await save_bot_suggestion(db, user_id, final_reply)

    # Persist this turn's conversation
    await save_message(db, user_id, "user", text)
    await save_message(db, user_id, "assistant", final_reply)

    return final_reply


def _infer_record_type(tool_calls: list) -> str:  # type: ignore[type-arg]
    names = {getattr(getattr(tc, "function", None), "name", "") for tc in tool_calls}
    if "log_strength_training" in names:
        return "workout"
    if "log_cardio" in names:
        return "cardio"
    if "log_body_composition" in names:
        return "body_comp"
    if "log_user_condition" in names:
        return "condition"
    if "update_user_profile" in names:
        return "profile"
    return "other"


IMAGE_TAG_RE = re.compile(r"\[IMAGE:(https?://\S+)\]")


def _build_messages(text: str) -> list:
    """Parse text into LINE messages, extracting [IMAGE:url] tags as ImageMessages."""
    messages: list = []
    remaining = text
    for match in IMAGE_TAG_RE.finditer(text):
        # Text before the image tag
        before = remaining[: match.start() - (len(text) - len(remaining))]
        before = before.strip()
        if before:
            messages.append(TextMessage(text=_truncate(before)))
        url = match.group(1)
        messages.append(ImageMessage(original_content_url=url, preview_image_url=url))
        remaining = text[match.end():]

    remaining = remaining.strip()
    if remaining:
        messages.append(TextMessage(text=_truncate(remaining)))

    return messages or [TextMessage(text="...")]


async def _send_reply(line_user_id: str, reply_token: str, text: str, start: float) -> None:
    elapsed = time.monotonic() - start
    messages = _build_messages(text)

    if elapsed < REPLY_TOKEN_TIMEOUT_SEC:
        try:
            await _reply_messages(reply_token, messages)
            return
        except Exception:
            logger.warning("Reply token failed after %.1fs, falling back to push", elapsed)

    try:
        await _push_messages(line_user_id, messages)
    except Exception:
        logger.exception("Push message also failed for %s", line_user_id)


def _truncate(text: str) -> str:
    if len(text) <= LINE_MESSAGE_MAX_LENGTH:
        return text
    return text[: LINE_MESSAGE_MAX_LENGTH - 3] + "..."


async def _reply_messages(reply_token: str, messages: list) -> None:
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


async def _reply_text(reply_token: str, text: str) -> None:
    await _reply_messages(reply_token, [TextMessage(text=_truncate(text))])


async def handle_image_message(event: MessageEvent) -> None:
    start = time.monotonic()
    line_user_id = event.source.user_id
    reply_token = event.reply_token
    message_id = event.message.id

    if not is_user_allowed(line_user_id):
        await _reply_text(reply_token, "Sorry, you are not authorized to use this bot.")
        return

    logger.info("Image from %s, message_id=%s", line_user_id, message_id)

    # Download image from LINE
    async with AsyncApiClient(configuration) as api_client:
        blob_api = AsyncMessagingApiBlob(api_client)
        image_bytes = await blob_api.get_message_content(message_id)

    # Classify and parse with vision model
    raw_bytes = bytes(image_bytes)
    parsed = await classify_and_parse_image(raw_bytes)

    if parsed is None:
        await _send_reply(
            line_user_id, reply_token,
            "Sorry, I couldn't process this image. Try sending a clearer photo!", start,
        )
        return

    category = parsed.get("category", "other")
    description = parsed.get("description")

    # Persist image to storage backend + DB record
    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, line_user_id)
            await save_image(
                db,
                user_id=user.id,
                line_user_id=line_user_id,
                category=category,
                message_id=message_id,
                image_bytes=raw_bytes,
                description=description,
            )

            if category == "inbody":
                inbody_text = (
                    f"[InBody report parsed from image]\n"
                    f"Please call log_body_composition with this data: "
                    f"{json.dumps(parsed, ensure_ascii=False)}"
                )
                reply = await _process_with_llm(db, user.id, inbody_text)
            else:
                image_text = (
                    f"[User sent a {category} photo: {description}]\n"
                    f"Image saved. Respond to acknowledge the photo."
                )
                reply = await _process_with_llm(db, user.id, image_text)

    await _send_reply(line_user_id, reply_token, reply, start)


async def _push_messages(user_id: str, messages: list) -> None:
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.push_message(
            PushMessageRequest(to=user_id, messages=messages)
        )


async def push_text(user_id: str, text: str) -> None:
    await _push_messages(user_id, [TextMessage(text=_truncate(text))])
