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


async def test_calories_auto_estimated_when_missing(
    db: AsyncSession, user: User, today: date
):
    # 30 min cycling at 18 km/h, weight defaulted to 65kg -> MET 7.5
    # ≈ 7.5 * 65 * 3.5 * 30 / 200 ≈ 256 kcal
    result = await log_cardio(
        db, user.id, today, "cycling",
        duration_min=30, speed_kmh=18.0,
    )
    await db.flush()

    assert result["calories_estimated"] is True
    assert 230 <= result["calories"] <= 280


async def test_explicit_calories_not_overwritten(
    db: AsyncSession, user: User, today: date
):
    result = await log_cardio(
        db, user.id, today, "running",
        duration_min=20, calories=400,
    )
    await db.flush()

    assert result["calories"] == 400
    assert result["calories_estimated"] is False


async def test_calories_uses_latest_weight(db: AsyncSession, user: User, today: date):
    from src.services.body_comp import log_body_composition

    # Heaviest user → bigger calorie estimate
    await log_body_composition(
        db, user.id, today - timedelta(days=1), weight_kg=90.0
    )
    await db.flush()

    result = await log_cardio(
        db, user.id, today, "cycling",
        duration_min=30, speed_kmh=18.0,
    )
    await db.flush()

    # 7.5 * 90 * 3.5 * 30 / 200 ≈ 354 kcal — clearly above the 65kg baseline
    assert result["calories"] is not None
    assert result["calories"] > 320
