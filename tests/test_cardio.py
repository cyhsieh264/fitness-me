"""Tests for cardio recording and progress summary."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.services.cardio import get_cardio_history, get_cardio_summary, log_cardio


async def test_log_cardio(db: AsyncSession, user: User):
    result = await log_cardio(
        db,
        user.id,
        date(2026, 3, 10),
        "treadmill",
        duration_min=30,
        speed_kmh=6.0,
        incline=3.0,
        max_heart_rate=155,
    )
    await db.flush()

    assert result["cardio_type"] == "treadmill"
    assert result["duration_min"] == 30
    assert result["max_heart_rate"] == 155


async def test_get_cardio_history(db: AsyncSession, user: User, today: date):
    await log_cardio(db, user.id, today, "treadmill", duration_min=30, max_heart_rate=150)
    await log_cardio(db, user.id, today, "spinning", duration_min=45, max_heart_rate=165)
    await db.flush()

    history = await get_cardio_history(db, user.id, days=7)
    assert len(history) == 2


async def test_cardio_filter_by_type(db: AsyncSession, user: User, today: date):
    await log_cardio(db, user.id, today, "treadmill", duration_min=30)
    await log_cardio(db, user.id, today, "spinning", duration_min=45)
    await db.flush()

    history = await get_cardio_history(db, user.id, days=7, cardio_type="treadmill")
    assert len(history) == 1
    assert history[0]["type"] == "treadmill"


async def test_cardio_summary(db: AsyncSession, user: User, today: date):
    await log_cardio(
        db, user.id, today - timedelta(days=2), "treadmill",
        duration_min=30, max_heart_rate=150,
    )
    await log_cardio(
        db, user.id, today, "treadmill",
        duration_min=35, max_heart_rate=160,
    )
    await log_cardio(
        db, user.id, today, "spinning",
        duration_min=45, max_heart_rate=170,
    )
    await db.flush()

    summary = await get_cardio_summary(db, user.id, days=30)
    assert summary["total_sessions"] == 3
    assert summary["by_type"] == {"treadmill": 2, "spinning": 1}
    assert summary["total_duration_min"] == 110
    assert summary["avg_max_hr"] == 160
    assert summary["highest_max_hr"] == 170


async def test_cardio_summary_empty(db: AsyncSession, user: User):
    summary = await get_cardio_summary(db, user.id, days=30)
    assert summary["total_sessions"] == 0
