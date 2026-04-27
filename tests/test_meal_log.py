"""Tests for meal logging service: round-trip + daily aggregation."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.services.meal_log import get_daily_totals, get_meal_history, log_meal


async def test_log_and_history_round_trip(db: AsyncSession, user: User, today: date):
    saved = await log_meal(
        db,
        user_id=user.id,
        meal_date=today,
        meal_type="lunch",
        food_items=["義大利麵", "沙拉"],
        calories=650,
        protein_g=24,
        carbs_g=80,
        fat_g=22,
    )
    await db.flush()

    assert saved["meal_type"] == "lunch"
    assert saved["food_items"] == ["義大利麵", "沙拉"]
    assert saved["calories"] == 650

    history = await get_meal_history(db, user.id, days=1)
    assert len(history) == 1
    assert history[0]["food_items"] == ["義大利麵", "沙拉"]


async def test_meal_type_filter(db: AsyncSession, user: User, today: date):
    await log_meal(db, user.id, today, "breakfast", ["燕麥"], calories=300)
    await log_meal(db, user.id, today, "lunch", ["便當"], calories=700)
    await db.flush()

    only_lunch = await get_meal_history(db, user.id, days=1, meal_type="lunch")
    assert len(only_lunch) == 1
    assert only_lunch[0]["meal_type"] == "lunch"


async def test_daily_totals_aggregate_same_day(db: AsyncSession, user: User, today: date):
    await log_meal(db, user.id, today, "breakfast", ["燕麥"], calories=300, protein_g=10)
    await log_meal(db, user.id, today, "lunch", ["便當"], calories=700, protein_g=30)
    await db.flush()

    totals = await get_daily_totals(db, user.id, days=1)
    key = today.isoformat()
    assert totals[key]["calories"] == 1000
    assert totals[key]["protein_g"] == 40


async def test_history_window_excludes_old(db: AsyncSession, user: User, today: date):
    await log_meal(db, user.id, today - timedelta(days=10), "lunch", ["過期紀錄"])
    await log_meal(db, user.id, today, "lunch", ["最近紀錄"])
    await db.flush()

    history = await get_meal_history(db, user.id, days=7)
    assert len(history) == 1
    assert history[0]["food_items"] == ["最近紀錄"]
