"""Meal log CRUD and aggregation.

Stores per-meal nutrition entries. Linked to a `user_images` row when a photo
was attached, but works equally well from text-only logging ("早餐三明治 + 美式").
"""

import json
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MealLog
from src.utils.time import timestamp, window_dates


async def log_meal(
    db: AsyncSession,
    user_id: int,
    meal_date: date,
    meal_type: str,
    food_items: list[str],
    calories: int | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    image_id: int | None = None,
    notes: str | None = None,
) -> dict:
    record = MealLog(
        user_id=user_id,
        date=meal_date,
        meal_type=meal_type,
        food_items=json.dumps(food_items, ensure_ascii=False),
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        image_id=image_id,
        notes=notes,
        created_at=timestamp(),
    )
    db.add(record)
    await db.flush()
    return _serialize(record)


async def get_meal_history(
    db: AsyncSession,
    user_id: int,
    days: int = 7,
    meal_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    start, end = window_dates(days, date_from, date_to)
    query = select(MealLog).where(MealLog.user_id == user_id, MealLog.date >= start)
    if end:
        query = query.where(MealLog.date <= end)
    if meal_type:
        query = query.where(MealLog.meal_type == meal_type)
    query = query.order_by(MealLog.date.desc(), MealLog.created_at.desc())

    result = await db.execute(query)
    return [_serialize(m) for m in result.scalars().all()]


async def get_daily_totals(
    db: AsyncSession,
    user_id: int,
    days: int = 7,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, dict[str, float]]:
    """Aggregate calories + macros per date over the window."""
    start, end = window_dates(days, date_from, date_to)
    query = select(MealLog).where(MealLog.user_id == user_id, MealLog.date >= start)
    if end:
        query = query.where(MealLog.date <= end)
    result = await db.execute(query)

    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    for m in result.scalars().all():
        bucket = totals[m.date.isoformat()]
        if m.calories is not None:
            bucket["calories"] += m.calories
        if m.protein_g is not None:
            bucket["protein_g"] += m.protein_g
        if m.carbs_g is not None:
            bucket["carbs_g"] += m.carbs_g
        if m.fat_g is not None:
            bucket["fat_g"] += m.fat_g

    return dict(totals)


def _serialize(m: MealLog) -> dict:
    return {
        "id": m.id,
        "date": m.date.isoformat(),
        "meal_type": m.meal_type,
        "food_items": json.loads(m.food_items) if m.food_items else [],
        "calories": m.calories,
        "protein_g": m.protein_g,
        "carbs_g": m.carbs_g,
        "fat_g": m.fat_g,
        "image_id": m.image_id,
        "notes": m.notes,
    }
