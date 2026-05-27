"""Daily push scheduling with APScheduler."""

import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, select, update

from src.config import settings
from src.db.database import async_session
from src.db.models import DailyInteraction, RawRecord, UserCondition
from src.utils.time import days_ago_ts, now, today

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.timezone)

CHAT_RETENTION_DAYS = 7
DAILY_INTERACTION_RETENTION_DAYS = 90
RAW_RECORD_RETENTION_DAYS = 90
RESOLVED_CONDITION_RETENTION_DAYS = 90


async def _daily_push_job() -> None:
    """Send daily push to all active users."""
    from src.line.push import send_daily_push
    from src.services.user import get_active_line_user_ids

    async with async_session() as db:
        line_user_ids = await get_active_line_user_ids(db)

    for line_uid in line_user_ids:
        try:
            await send_daily_push(line_uid)
        except Exception:
            logger.exception("Failed to send daily push to %s", line_uid)


async def _cleanup_job() -> None:
    """End-of-day cleanup: mark unanswered pushes as rest + purge expired data."""
    from src.services.chat_history import cleanup_old_messages

    async with async_session() as db:
        async with db.begin():
            # Mark unanswered daily interactions as rest
            await db.execute(
                update(DailyInteraction)
                .where(
                    DailyInteraction.date == today(),
                    DailyInteraction.push_sent_at.isnot(None),
                    DailyInteraction.responded_at.is_(None),
                )
                .values(user_plan="rest")
            )

            # Purge chat messages older than 7 days
            chat_deleted = await cleanup_old_messages(db, CHAT_RETENTION_DAYS)

            # Purge daily interactions older than 90 days
            di_cutoff = today() - timedelta(days=DAILY_INTERACTION_RETENTION_DAYS)
            di_result = await db.execute(
                delete(DailyInteraction).where(DailyInteraction.date < di_cutoff)
            )

            # Purge raw records older than 90 days
            rr_cutoff = days_ago_ts(RAW_RECORD_RETENTION_DAYS)
            rr_result = await db.execute(delete(RawRecord).where(RawRecord.created_at < rr_cutoff))

            # Purge resolved conditions older than 90 days
            cond_cutoff = days_ago_ts(RESOLVED_CONDITION_RETENTION_DAYS)
            cond_result = await db.execute(
                delete(UserCondition).where(
                    UserCondition.is_active.is_(False),
                    UserCondition.resolved_at.isnot(None),
                    UserCondition.resolved_at < cond_cutoff,
                )
            )

    logger.info(
        "Cleanup done: chat=%d, daily_interactions=%d, raw_records=%d, conditions=%d",
        chat_deleted,
        di_result.rowcount,  # type: ignore[attr-defined]
        rr_result.rowcount,  # type: ignore[attr-defined]
        cond_result.rowcount,  # type: ignore[attr-defined]
    )


async def check_and_send_missed_push() -> None:
    """On startup, send daily push if it was missed (e.g. after restart)."""
    if now().hour < 8:
        return

    async with async_session() as db:
        result = await db.execute(select(DailyInteraction).where(DailyInteraction.date == today()))
        if result.first():
            return

    logger.info("Missed daily push detected, sending now")
    await _daily_push_job()


def start_scheduler() -> None:
    """Start the scheduler with daily push and cleanup jobs."""
    # misfire_grace_time defaults to 1s: if the event loop is busy when the
    # trigger fires, APScheduler silently drops the run. The push already
    # tolerates up to an hour of jitter, so accept the same lateness window
    # rather than lose a whole morning. coalesce collapses any backlog into a
    # single run.
    scheduler.add_job(
        _daily_push_job,
        CronTrigger(hour=8, minute=0, jitter=3600, timezone=settings.timezone),
        id="daily_push",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    # Cleanup keys off today(); keep the grace tight so a misfire still runs
    # within the same calendar day.
    scheduler.add_job(
        _cleanup_job,
        CronTrigger(hour=23, minute=59, timezone=settings.timezone),
        id="daily_cleanup",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started: daily_push (08:00+jitter), daily_cleanup (23:59)")


def stop_scheduler() -> None:
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
