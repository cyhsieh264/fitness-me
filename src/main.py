import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from src.config import settings
from src.db.database import engine
from src.db.models import Base
from src.line.handler import handle_image_message, handle_text_message
from src.services.images import verify_image_token
from src.services.import_records import run_import
from src.services.scheduler import check_and_send_missed_push, start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness-Me LINE Bot")
parser = WebhookParser(settings.line_channel_secret)


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")
    start_scheduler()
    await check_and_send_missed_push()


@app.on_event("shutdown")
async def shutdown() -> None:
    stop_scheduler()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/images/{image_id}/{token}")
async def serve_image(image_id: int, token: str) -> FileResponse:
    """Serve user image with HMAC token verification."""
    path = verify_image_token(image_id, token)
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


def _verify_admin(request: Request) -> None:
    token = request.headers.get("X-Admin-Token", "")
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/admin/download-db")
async def download_db(request: Request) -> FileResponse:
    """Download a safe copy of the SQLite database."""
    _verify_admin(request)

    import sqlite3
    import tempfile

    db_path = settings.database_url.split("///", 1)[1]
    if not Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Database not found")

    # Use sqlite3 backup API for a consistent snapshot
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    src_conn = sqlite3.connect(db_path)
    dst_conn = sqlite3.connect(tmp.name)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    return FileResponse(tmp.name, filename="fitness.db", media_type="application/octet-stream")


@app.post("/admin/import-history")
async def import_history(
    request: Request,
    line_user_id: str = Form(None),
    file: UploadFile = File(None),
    cutoff_years: int = Form(2),
) -> dict:
    """Import historical records via LLM parsing.

    Accepts either:
    - multipart form: line_user_id + file (text file upload)
    - JSON body: {"line_user_id": "...", "raw_text": "...", "cutoff_years": 2}
    """
    _verify_admin(request)

    if file and line_user_id:
        raw_text = (await file.read()).decode("utf-8")
    else:
        body = await request.json()
        line_user_id = body.get("line_user_id")
        raw_text = body.get("raw_text")
        cutoff_years = body.get("cutoff_years", 2)

    if not line_user_id or not raw_text:
        raise HTTPException(status_code=400, detail="line_user_id and raw_text/file required")

    success, total = await run_import(line_user_id, raw_text, cutoff_years)
    return {"success": success, "total": total}


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
