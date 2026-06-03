import json
import logging
import re
import time
from datetime import date

import litellm
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
from src.llm.prompts import PromptContext, build_system_prompt
from src.llm.tool_executor import execute_tool
from src.llm.tools import TOOLS
from src.llm.vision import classify_and_parse_image
from src.services.chat_history import get_recent_messages, save_message
from src.services.goals import get_active_goals
from src.services.images import save_image
from src.services.profile import get_profile_summary
from src.services.recommender import (
    get_pending_daily_interaction,
    save_bot_suggestion,
    update_daily_plan,
)
from src.services.user import get_or_create_user
from src.services.workout import save_raw_record
from src.utils.time import today

logger = logging.getLogger(__name__)

LINE_MESSAGE_MAX_LENGTH = 5000
REPLY_TOKEN_TIMEOUT_SEC = 25

# Max rounds where the model may call tools before we force a prose answer.
# Lets the model investigate adaptively (query -> see result -> query again)
# instead of guessing every tool call up front in one blind batch. Bounded so
# a confused model can't loop forever — worst case is MAX_TOOL_ROUNDS tool
# calls plus one summary turn.
MAX_TOOL_ROUNDS = 3

SERVICE_PAUSED_MESSAGE = (
    "目前暫停提供服務（API 配額或認證異常），請稍後再試或聯絡管理員。"
)

# Used when the LLM returns no choices / empty content. Better than "..." —
# gives the user something to react to instead of a dead-end.
EMPTY_RESPONSE_MESSAGE = "AI 助手暫時不想說話，可以稍後再試一次。"

# Turn-2 prompts. Writes get a terse confirmation; queries must list every
# row the tool returned — gating on user push-back is what got us into the
# "drip-fed" mess in spec-004.
TURN2_PROMPT_WRITE = (
    "請用繁體中文簡短摘要剛剛記錄的內容（1-3 行）。"
    "若有 PR、目標達成、或值得提醒的觀察就一起講。"
    "如果只是純資料記錄，回一句確認即可。"
)

TURN2_PROMPT_QUERY = (
    "請用繁體中文，依工具回傳的資料回答使用者的問題。先判斷他要的是「清單」"
    "還是「判斷」：\n"
    "- 清單型（列出 / 有哪些 / 最近紀錄）：每一筆都列出，含動作名、重量/組數、"
    "日期、session_type（self_training→自主訓練 / coach→教練課 / other→其他），"
    "同類動作按動作分組，不要刪節。\n"
    "- 判斷型（哪個最好 / 最突出 / 進步最多 / 我適合什麼 / 哪裡該加強）：不要倒"
    "清單，先排序比較挑出 1-3 個重點，給結論再附一句理由（進步幅度、相對體重、"
    "對照一般人常模）。像教練講重點，不要像報表。\n"
    "- 工具沒回的紀錄絕對不要編造。找不到就說找不到，並建議用更廣的關鍵詞 "
    "或 muscle_group 再查一次。"
)

# Bot-side insurance for daily-push replies: when the LLM returns silence
# (empty content + no tool calls) AND a daily push is pending, we run this
# tiny keyword classifier ourselves so the user is never met with the canned
# EMPTY_RESPONSE_MESSAGE on their morning reply. Ordering matters — first
# match wins. Lowercased before comparison.
_DAILY_PUSH_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("rest", ("休息", "沒練", "不練", "不想練", "rest", "off", "痠痛", "酸痛")),
    ("coach", ("教練", "pt ", " pt", "上課")),
    ("self_training", ("自己練", "自主", "自己", "solo")),
]

_DAILY_PUSH_FALLBACK_REPLY = {
    "rest": "好喔，今天休息！記得伸展放鬆，多補水 💧",
    "coach": "好的，教練課加油！上課前先做好暖身 🔥",
    "self_training": "好喔，自主訓練！動作品質第一，避開近兩天練過的肌群。",
    "other": "好喔，記得多喝水、保持心情愉快！",
}


def _classify_daily_push(text: str) -> str:
    """Map a free-text daily-push reply to one of the four plans.

    Used only as a fallback when the LLM produces nothing — see the
    `_process_with_llm` empty-response branches. "other" is the catch-all so
    we always have something to call update_daily_plan with.
    """
    needle = text.lower()
    for plan, keywords in _DAILY_PUSH_KEYWORDS:
        if any(kw in needle for kw in keywords):
            return plan
    return "other"


async def _empty_response_fallback(
    db: AsyncSession,
    user_id: int,
    text: str,
    has_pending_daily_push: bool,
) -> str:
    """Pick the best fallback reply when the LLM produced nothing.

    Daily-push branch: classify by keyword, record the plan via
    update_daily_plan, and reply with a stock zh-TW line for that plan.
    Anywhere else: fall back to EMPTY_RESPONSE_MESSAGE — there's no signal
    to act on.
    """
    if not has_pending_daily_push:
        return EMPTY_RESPONSE_MESSAGE

    plan = _classify_daily_push(text)
    try:
        await update_daily_plan(db, user_id, plan, text)
    except Exception:
        logger.exception("Daily-plan fallback update failed (plan=%s)", plan)
        # Don't bail — still give the user a coherent reply even if the
        # bookkeeping write failed; they can re-state later.
    reply = _DAILY_PUSH_FALLBACK_REPLY[plan]
    try:
        await save_bot_suggestion(db, user_id, reply)
    except Exception:
        logger.exception("save_bot_suggestion failed in fallback")
    return reply


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


async def _process_with_llm(
    db: AsyncSession,
    user_id: int,
    text: str,
    *,
    image_category: str | None = None,
) -> str:
    """Run a single LLM turn (text or image-synthetic).

    image_category is the vision-classifier label when this turn was triggered
    by a photo, so the prompt assembler can include image-specific sections
    (INBODY_REPORTS, IMAGE_EXTRACTION) only when relevant.
    """
    profile = await get_profile_summary(db, user_id)
    active_goals = await get_active_goals(db, user_id)
    pending = await get_pending_daily_interaction(db, user_id)
    has_pending_daily_push = pending is not None

    ctx = PromptContext(
        today_iso=today().isoformat(),
        timezone=settings.timezone,
        profile_summary=profile,
        active_goals=active_goals,
        has_pending_daily_push=has_pending_daily_push,
        image_in_flight=image_category,
        latest_weight_recorded=bool(profile.get("latest_weight_kg")),
    )
    system_prompt = build_system_prompt(ctx)

    history = await get_recent_messages(db, user_id)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]  # type: ignore[type-arg]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    # Multi-round tool-calling loop. Each round the model may call tools, read
    # the results, and decide its next move (query -> see result -> query
    # again, or compose several queries before answering). It ends a round with
    # NO tool calls once it's ready to answer in prose. Bounded by
    # MAX_TOOL_ROUNDS so a confused model can't loop forever.
    final_reply: str | None = None
    accumulated_tool_calls: list = []  # type: ignore[type-arg]
    has_db_write = False
    has_query = False
    has_daily_plan = False

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        try:
            response = await chat_completion(messages=messages, tools=TOOLS)
        except (litellm.RateLimitError, litellm.AuthenticationError):
            logger.exception("LLM quota / auth error — pausing service reply")
            return SERVICE_PAUSED_MESSAGE
        except Exception:
            logger.exception("LLM call failed on round %d", round_num)
            if round_num == 1:
                return "Something went wrong, please try again."
            break  # tool work already done — fall through to the summary nudge

        # Gemini may return empty choices entirely.
        if not response.choices:
            logger.warning(
                "LLM round %d returned no choices for text=%r", round_num, text[:200]
            )
            if round_num == 1:
                reply = await _empty_response_fallback(
                    db, user_id, text, has_pending_daily_push
                )
                await save_message(db, user_id, "user", text)
                await save_message(db, user_id, "assistant", reply)
                return reply
            break

        message = response.choices[0].message
        tool_calls = message.tool_calls
        finish_reason = getattr(response.choices[0], "finish_reason", "?")

        if not tool_calls:
            # Model is done calling tools — this turn's content is the answer.
            if message.content:
                final_reply = message.content
            elif round_num == 1:
                logger.warning(
                    "LLM returned empty response (finish_reason=%s) for user text "
                    "preview=%r",
                    finish_reason,
                    text[:200],
                )
                final_reply = await _empty_response_fallback(
                    db, user_id, text, has_pending_daily_push
                )
            # Empty content after tool work falls to the summary nudge below.
            break

        # Model wants tools: record the assistant turn, then run this batch.
        messages.append(message.model_dump())
        accumulated_tool_calls.extend(tool_calls)
        for tc in tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning("Malformed tool arguments: %s", tc.function.arguments)
                arguments = {}

            logger.info("Tool call (round %d): %s(%s)", round_num, tc.function.name, arguments)

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
            if tool_name.startswith("query_"):
                has_query = True
            if tool_name == "update_daily_plan":
                has_daily_plan = True

    # Save raw record if any DB write happened (skip for daily plan updates).
    if has_db_write and not has_daily_plan:
        record_type = _infer_record_type(accumulated_tool_calls)
        await save_raw_record(db, user_id, text, record_type)

    # If the model never settled into a prose answer — it hit the round cap
    # still wanting tools, or went silent right after tool results — force a
    # final text-only summary. Gemini Flash reliably returns empty when given
    # just `[tool_call, tool_result]` and expected to summarize implicitly, so
    # an explicit nudge (and dropping tools) gets a real answer out.
    if final_reply is None:
        if has_query and not has_db_write:
            summary_nudge = TURN2_PROMPT_QUERY
        else:
            summary_nudge = TURN2_PROMPT_WRITE
        messages.append({"role": "user", "content": summary_nudge})
        try:
            response2 = await chat_completion(messages=messages)
        except (litellm.RateLimitError, litellm.AuthenticationError):
            logger.exception("LLM quota / auth error on summary turn — pausing")
            return SERVICE_PAUSED_MESSAGE
        except Exception:
            logger.exception("LLM summary turn failed")
            return "Recorded, but failed to generate summary."

        if not response2.choices or not response2.choices[0].message.content:
            finish_reason_2 = (
                getattr(response2.choices[0], "finish_reason", "?")
                if response2.choices
                else "no-choices"
            )
            logger.warning("LLM summary turn returned empty (finish_reason=%s)", finish_reason_2)
            final_reply = "已記錄完成。"
        else:
            final_reply = response2.choices[0].message.content

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

# LLMs habitually emit markdown even when the prompt forbids it, and LINE
# renders plain text only — literal **asterisks** degrade readability. These
# strip the common emphasis / heading / code syntaxes as a safety net behind
# the prompt rule. Single asterisks are deliberately left alone: workout
# notation ("40kg*10*4") uses them legitimately.
_MD_CODE_FENCE_RE = re.compile(r"^```[^\n]*\n?", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_BOLD_UNDERSCORE_RE = re.compile(r"__(.+?)__", re.DOTALL)
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def strip_markdown(text: str) -> str:
    """Flatten markdown the LLM may emit into LINE-friendly plain text.

    Keeps the [IMAGE:url] tag intact (it has no following parenthesis, so
    the link pattern never matches it).
    """
    text = _MD_CODE_FENCE_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_BOLD_UNDERSCORE_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1 \2", text)
    return text


def _build_messages(text: str) -> list:
    """Parse text into LINE messages, extracting [IMAGE:url] tags as ImageMessages."""
    text = strip_markdown(text)
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
    try:
        parsed = await classify_and_parse_image(raw_bytes)
    except (litellm.RateLimitError, litellm.AuthenticationError):
        logger.exception("Vision quota / auth error — pausing service reply")
        await _send_reply(line_user_id, reply_token, SERVICE_PAUSED_MESSAGE, start)
        return

    if parsed is None:
        await _send_reply(
            line_user_id, reply_token,
            "Sorry, I couldn't process this image. Try sending a clearer photo!", start,
        )
        return

    category = parsed.get("category", "other")
    description = parsed.get("description")

    # Prefer the date the vision model OCR'd off the image (e.g. InBody test
    # date) over the upload date. Falls back to today() inside save_image.
    parsed_date: date | None = None
    if parsed.get("date"):
        try:
            parsed_date = date.fromisoformat(parsed["date"])
        except (TypeError, ValueError):
            logger.warning("Vision returned unparseable date: %r", parsed.get("date"))

    # Persist image to storage backend + DB record. Save first so meal/training
    # flows can pass image_id to the structured-logging tools.
    async with async_session() as db:
        async with db.begin():
            user = await get_or_create_user(db, line_user_id)
            saved = await save_image(
                db,
                user_id=user.id,
                line_user_id=line_user_id,
                category=category,
                message_id=message_id,
                image_bytes=raw_bytes,
                description=description,
                image_date=parsed_date,
            )
            image_id = saved["id"]

            payload = json.dumps(parsed, ensure_ascii=False)

            if category == "inbody":
                synthetic = (
                    f"[InBody report parsed from image]\n"
                    f"Please call log_body_composition with this data: {payload}"
                )
            elif category == "meal":
                synthetic = (
                    f"[Meal photo parsed, image_id={image_id}]\n"
                    f"Please call log_meal with this data (include image_id={image_id}): "
                    f"{payload}"
                )
            elif category == "training_sheet":
                synthetic = (
                    f"[Training sheet parsed from image]\n"
                    f"Please call log_strength_training with the exercises array; "
                    f"each exercise's raw_text follows the same '40kg*10*4' grammar "
                    f"as a typed log: {payload}"
                )
            else:
                synthetic = (
                    f"[User just sent a {category} photo: {description}]\n"
                    f"Follow IMAGE CONTEXT in your instructions: combine this with "
                    f"any introducer text in the recent chat history before replying."
                )

            reply = await _process_with_llm(
                db, user.id, synthetic, image_category=category
            )

    await _send_reply(line_user_id, reply_token, reply, start)


async def _push_messages(user_id: str, messages: list) -> None:
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.push_message(
            PushMessageRequest(to=user_id, messages=messages)
        )


async def push_text(user_id: str, text: str) -> None:
    # Daily-push greetings are LLM-generated too — same plain-text rules.
    await _push_messages(user_id, [TextMessage(text=_truncate(strip_markdown(text)))])
