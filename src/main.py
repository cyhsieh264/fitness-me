import asyncio
import hmac
import logging

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from scripts.seed import run_seed
from src.config import settings
from src.line.handler import handle_image_message, handle_text_message, push_text
from src.services.import_records import run_import
from src.services.scheduler import check_and_send_missed_push, start_scheduler, stop_scheduler
from src.storage import get_storage
from src.storage.local import LocalStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness-Me LINE Bot")
parser = WebhookParser(settings.line_channel_secret)


@app.on_event("startup")
async def startup() -> None:
    # run_seed() creates tables and idempotently inserts the exercise/muscle
    # dictionary. Safe to run on every boot — no-ops once the data is there.
    await run_seed()
    start_scheduler()
    await check_and_send_missed_push()


@app.on_event("shutdown")
async def shutdown() -> None:
    stop_scheduler()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/images/{key_b64}/{token}")
async def serve_image(key_b64: str, token: str) -> FileResponse:
    """Serve a locally-stored image after verifying the HMAC token.

    Only meaningful when STORAGE_PROVIDER=local; remote backends mint their
    own signed URLs and bypass this route entirely.
    """
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="Not found")
    path = storage.verify_and_path(key_b64, token)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


def _verify_admin_api_key(request: Request) -> None:
    given = request.headers.get("X-API-Key", "")
    expected = settings.admin_api_key
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


async def _run_import_and_notify(raw_text: str, cutoff_years: int) -> None:
    """Background worker: import records, then push the result via LINE.

    Both the data-owner user_id and the notification target are taken from
    ADMIN_LINE_USER_ID — the import is always for the admin themselves.
    """
    user_id = settings.admin_line_user_id
    try:
        success, total = await run_import(user_id, raw_text, cutoff_years)
        skipped = total - success
        lines = [
            "歷史紀錄匯入完成",
            f"寫入：{success}/{total} 筆",
        ]
        if skipped:
            lines.append(f"（{skipped} 筆 LLM 無法解析跳過）")
        await push_text(user_id, "\n".join(lines))
    except Exception:
        logger.exception("Background import failed for %s", user_id)
        try:
            await push_text(user_id, "歷史紀錄匯入失敗，請查看 server log。")
        except Exception:
            logger.exception("Could not push failure notification to %s", user_id)


@app.post("/admin/import-history", status_code=202)
async def import_history(
    request: Request,
    file: UploadFile = File(None),
    cutoff_years: int = Form(2),
) -> dict:
    """Kick off historical-record import; returns immediately with 202.

    The import (LLM parsing + DB writes) runs in the background and writes
    records under ADMIN_LINE_USER_ID. When it finishes the same user gets a
    LINE push message with the result.

    Accepts either:
    - multipart form: `file` (text upload) [+ optional `cutoff_years`]
    - JSON body: `{"raw_text": "...", "cutoff_years": 2}`
    """
    _verify_admin_api_key(request)

    if not settings.admin_line_user_id:
        raise HTTPException(
            status_code=500, detail="ADMIN_LINE_USER_ID is not configured"
        )

    if file:
        raw_text = (await file.read()).decode("utf-8")
    else:
        body = await request.json()
        raw_text = body.get("raw_text")
        cutoff_years = body.get("cutoff_years", 2)

    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text or file required")

    asyncio.create_task(_run_import_and_notify(raw_text, cutoff_years))
    return {
        "status": "accepted",
        "line_user_id": settings.admin_line_user_id,
        "message": "Import running in background; result will arrive via LINE.",
    }


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, str]:
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent):
            if isinstance(event.message, TextMessageContent):
                asyncio.create_task(_safe_handle(event))
            elif isinstance(event.message, ImageMessageContent):
                asyncio.create_task(_safe_handle_image(event))

    return {"status": "ok"}


async def _safe_handle(event: MessageEvent) -> None:
    try:
        await handle_text_message(event)
    except Exception:
        logger.exception("Unhandled error processing message from %s", event.source.user_id)


async def _safe_handle_image(event: MessageEvent) -> None:
    try:
        await handle_image_message(event)
    except Exception:
        logger.exception("Unhandled error processing image from %s", event.source.user_id)
