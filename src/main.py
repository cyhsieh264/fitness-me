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
from src.db.database import async_session
from src.line.handler import handle_image_message, handle_text_message, push_text
from src.services.admin_ops import delete_records_in_range
from src.services.import_records import run_import
from src.services.scheduler import check_and_send_missed_push, start_scheduler, stop_scheduler
from src.storage import get_storage
from src.storage.local import LocalStorage
from src.utils.logging import align_uvicorn_loggers, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness-Me LINE Bot")
parser = WebhookParser(settings.line_channel_secret)


@app.on_event("startup")
async def startup() -> None:
    # uvicorn configures its own logging before the app starts; re-route its
    # loggers through our root handler now so every line shares one format.
    align_uvicorn_loggers()
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


async def _run_import_and_notify(
    line_user_id: str, raw_text: str, cutoff_years: int
) -> None:
    """Background worker: import records under line_user_id, notify admin.

    Records are persisted under the request-supplied data owner; the LINE
    push notification always goes to ADMIN_LINE_USER_ID (the operator).
    """
    notify_to = settings.admin_line_user_id
    try:
        counts = await run_import(line_user_id, raw_text, cutoff_years)
        lines = [
            "歷史紀錄匯入完成",
            f"使用者：{line_user_id}",
            f"新增：{counts['new']}/{counts['total']} 筆",
        ]
        if counts["already_existed"]:
            lines.append(f"已存在跳過：{counts['already_existed']} 筆")
        if counts["llm_failed"]:
            lines.append(f"無法解析：{counts['llm_failed']} 筆")
        await push_text(notify_to, "\n".join(lines))
    except Exception:
        logger.exception("Background import failed for %s", line_user_id)
        try:
            await push_text(
                notify_to,
                f"歷史紀錄匯入失敗\n使用者：{line_user_id}\n請查看 server log。",
            )
        except Exception:
            logger.exception("Could not push failure notification to %s", notify_to)


@app.post("/admin/import-history", status_code=202)
async def import_history(
    request: Request,
    line_user_id: str = Form(None),
    file: UploadFile = File(None),
    cutoff_years: int = Form(2),
) -> dict:
    """Kick off historical-record import; returns immediately with 202.

    Admin (the API caller) imports records on behalf of a target user
    identified by `line_user_id`. The import runs in the background; when
    it finishes ADMIN_LINE_USER_ID receives the LINE push notification.

    Accepts either:
    - multipart form: `line_user_id` + `file` (text upload) [+ optional `cutoff_years`]
    - JSON body: `{"line_user_id": "...", "raw_text": "...", "cutoff_years": 2}`
    """
    _verify_admin_api_key(request)

    if not settings.admin_line_user_id:
        raise HTTPException(
            status_code=500, detail="ADMIN_LINE_USER_ID is not configured"
        )

    if file and line_user_id:
        raw_text = (await file.read()).decode("utf-8")
    else:
        body = await request.json()
        line_user_id = body.get("line_user_id")
        raw_text = body.get("raw_text")
        cutoff_years = body.get("cutoff_years", 2)

    if not line_user_id or not raw_text:
        raise HTTPException(status_code=400, detail="line_user_id and raw_text/file required")

    asyncio.create_task(_run_import_and_notify(line_user_id, raw_text, cutoff_years))
    return {
        "status": "accepted",
        "line_user_id": line_user_id,
        "notify_to": settings.admin_line_user_id,
        "message": "Import running in background; admin will receive a LINE notification.",
    }


@app.post("/admin/delete-records")
async def delete_records(
    request: Request,
    line_user_id: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
) -> dict:
    """Delete a user's records (training / cardio / body / meal / PR) within
    a date range.

    Accepts either form-data or JSON. `end_date` must be >= `start_date`;
    same date is allowed (deletes only that day). Missing user / empty
    range returns 200 with zero counts — only validation/server errors
    raise.
    """
    _verify_admin_api_key(request)

    if not (line_user_id and start_date and end_date):
        body = await request.json()
        line_user_id = line_user_id or body.get("line_user_id")
        start_date = start_date or body.get("start_date")
        end_date = end_date or body.get("end_date")

    if not (line_user_id and start_date and end_date):
        raise HTTPException(
            status_code=400,
            detail="line_user_id, start_date, end_date are all required",
        )

    try:
        from datetime import date as _date
        sd = _date.fromisoformat(start_date)
        ed = _date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="dates must be YYYY-MM-DD")

    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    async with async_session() as db:
        async with db.begin():
            counts = await delete_records_in_range(db, line_user_id, sd, ed)

    return {"status": "ok", "deleted": counts}


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
