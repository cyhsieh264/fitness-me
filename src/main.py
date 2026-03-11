import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.config import settings
from src.db.database import engine
from src.db.models import Base
from src.line.handler import handle_text_message
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


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, str]:
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            asyncio.create_task(_safe_handle(event))

    return {"status": "ok"}


async def _safe_handle(event: MessageEvent) -> None:
    try:
        await handle_text_message(event)
    except Exception:
        logger.exception("Unhandled error processing message from %s", event.source.user_id)
