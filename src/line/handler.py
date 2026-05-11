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

SERVICE_PAUSED_MESSAGE = (
    "目前暫停提供服務（API 配額或認證異常），請稍後再試或聯絡管理員。"
)

# Used when the LLM returns no choices / empty content. Better than "..." —
# gives the user something to react to instead of a dead-end.
EMPTY_RESPONSE_MESSAGE = "AI 助手暫時不想說話，可以稍後再試一次。"

DAILY_PUSH_CONTEXT = """

DAILY PUSH RESPONSE:
The user is replying to today's morning push. They are stating their PLAN —
they have not done the workout yet. Steps:

1. Call update_daily_plan exactly once with their parsed intent:
   - 自主練 / 健身 / 自己練 / 想練 → user_plan = "self_training"
   - 教練 / 教練課 → user_plan = "coach"
   - 休息 / 不練 / 休 → user_plan = "rest"
   - 跑步 / 登山 / 騎車 / 游泳 / 其他運動 → user_plan = "other"

   **Hedged wording maps to the closest plan, never freeze**:
     "可能會自主練" / "應該會自己練" / "看狀況可能練" → self_training
     "也許會去跑步" → other
     "今天應該休息" → rest
     即使使用者用「可能」「應該」「看心情」等不確定詞，**也要選一個 plan
     繼續流程**，不要追問或返空。

2. **DO NOT** call log_strength_training, log_cardio, or any other
   logging tool here. The user has NOT done the workout yet — they're
   stating intent. Logging fires only when they later report completed
   sets / reps / minutes.

3. Based on user_plan, compose a reply in 繁體中文:

   user_plan = "self_training":
     建議一套今天的菜單，**固定格式**：
     - 🏋️ 重訓 1（複合 / 全身）：譬如深蹲、硬舉、引體向上、滑輪下拉、臥推
     - 🏋️ 重訓 2（局部 / 單關節）：譬如二頭彎舉、三頭下壓、側平舉、腿後彎舉
     - 🚶 有氧（明確機器 + 速度/坡度/時間）：
         例「跑步機快走 30 分鐘，速度 4.5 km/h，坡度 10」
     - 🔥 預估熱量消耗：用 cardio MET × USER PROFILE 的 latest_weight_kg
         在 head 估算（譬如「跑步機快走 30min ≈ 200 大卡」）
     - 🥩 蛋白質目標：依今天菜單 + 目標 + 身體狀況**動態算**，給一個
         具體克數 + 一句為什麼。基準（每 kg 體重）：
         · 一般日：1.4–1.6 g/kg
         · 今天有複合重訓（深蹲/硬舉/臥推/划船）：1.6–2.0 g/kg
         · 活躍目標含減脂 / 降體脂：2.0–2.4 g/kg（增加蛋白質保肌肉）
         · 活躍 condition 有 injury / 復健中：1.6–2.0 g/kg（修復用）
         · 純活動度日（散步、輕度有氧）：1.2–1.4 g/kg
         範例輸出：「今天有複合重訓 + 減脂目標 → 蛋白質目標約 130g
         (54kg × 2.4)，可以拆成早餐蛋白奶昔 ~30g、午餐雞胸 30g、
         晚餐豆腐 + 蛋 ~40g、訓練後乳清 ~30g」

     選動作時考慮：
       • 近 7 天訓練過的肌群 → 避開 48 小時內練過的同肌群
       • 活躍 user_conditions（譬如「左骨盆高」→ 避免單邊重壓；
         「右臀無力」→ 多放單邊臀活化動作如 clamshell、單腿橋）
       • 活躍目標（譬如深蹲突破 → 安排深蹲；體脂下降 → 重訓 volume
         不減 + 有氧強度拉一點）

   user_plan = "coach":
     簡短鼓勵一句、提醒帶水暖身。**不要建議動作**（教練會安排）。

   user_plan = "rest":
     肯定休息也是訓練一部分，提醒輕度拉伸 / 補水 / 蛋白質仍要吃夠。

   user_plan = "other"（跑步 / 登山 / 騎車 / 游泳 etc）:
     簡短鼓勵 + 預估熱量（用對應 cardio MET 估）+ 提醒補水。
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

    # Inject user profile into system prompt. latest_weight_kg is special-
    # cased so the LLM sees an explicit "not yet recorded" — the absence of
    # a key would be ambiguous.
    profile = await get_profile_summary(db, user_id)
    profile_parts: list[str] = []
    for key, value in profile.items():
        if key == "latest_weight_kg":
            profile_parts.append(
                f"- latest_weight_kg: {value}" if value else "- latest_weight_kg: not yet recorded"
            )
        elif value is not None:
            profile_parts.append(f"- {key}: {value}")
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
    except (litellm.RateLimitError, litellm.AuthenticationError):
        logger.exception("LLM quota / auth error — pausing service reply")
        return SERVICE_PAUSED_MESSAGE
    except Exception:
        logger.exception("LLM call failed")
        return "Something went wrong, please try again."

    # Same defensive guard as turn 2 — Gemini may return empty choices.
    if not response.choices:
        logger.warning("LLM turn 1 returned no choices at all for text=%r", text[:200])
        reply = EMPTY_RESPONSE_MESSAGE
        await save_message(db, user_id, "user", text)
        await save_message(db, user_id, "assistant", reply)
        return reply

    message = response.choices[0].message
    tool_calls = message.tool_calls
    finish_reason = getattr(response.choices[0], "finish_reason", "?")

    if not tool_calls:
        if not message.content:
            logger.warning(
                "LLM returned empty response (finish_reason=%s) for user text "
                "preview=%r",
                finish_reason,
                text[:200],
            )
            reply = EMPTY_RESPONSE_MESSAGE
        else:
            reply = message.content
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

    # Turn 2: LLM generates final response from tool results.
    # Gemini 2.5 Flash reliably returns empty when given just
    # `[tool_call, tool_result]` and expected to summarize implicitly —
    # an explicit "please summarize" nudge dramatically reduces empty
    # completions on this round-trip.
    messages.append({
        "role": "user",
        "content": (
            "請用繁體中文簡短摘要剛剛記錄的內容（1-3 行）。"
            "若有 PR、目標達成、或值得提醒的觀察就一起講。"
            "如果只是純資料記錄，回一句確認即可。"
        ),
    })
    try:
        response2 = await chat_completion(messages=messages)
    except (litellm.RateLimitError, litellm.AuthenticationError):
        logger.exception("LLM quota / auth error on turn 2 — pausing service reply")
        return SERVICE_PAUSED_MESSAGE
    except Exception:
        logger.exception("LLM turn 2 failed")
        return "Recorded, but failed to generate summary."

    # Gemini 2.5 Flash intermittently returns no choices (or empty content)
    # on the post-tool summary turn. Avoid IndexError and give the user a
    # generic confirmation so at least the DB write isn't silent.
    if not response2.choices:
        logger.warning("LLM turn 2 returned no choices at all")
        final_reply = "已記錄完成。"
    else:
        finish_reason_2 = getattr(response2.choices[0], "finish_reason", "?")
        content_2 = response2.choices[0].message.content
        if not content_2:
            logger.warning(
                "LLM turn 2 returned empty content (finish_reason=%s)",
                finish_reason_2,
            )
            final_reply = "已記錄完成。"
        else:
            final_reply = content_2

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

            reply = await _process_with_llm(db, user.id, synthetic)

    await _send_reply(line_user_id, reply_token, reply, start)


async def _push_messages(user_id: str, messages: list) -> None:
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.push_message(
            PushMessageRequest(to=user_id, messages=messages)
        )


async def push_text(user_id: str, text: str) -> None:
    await _push_messages(user_id, [TextMessage(text=_truncate(text))])
