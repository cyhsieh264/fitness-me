"""Tests for body composition tracking and goal comparison."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.services.body_comp import (
    get_body_composition_history,
    get_body_composition_summary,
    log_body_composition,
)
from src.services.profile import update_profile


async def test_log_body_composition(db: AsyncSession, user: User):
    result = await log_body_composition(
        db, user.id, date(2026, 3, 12), body_fat_pct=22.5, weight_kg=58.0
    )
    await db.flush()

    assert result["body_fat_pct"] == 22.5
    assert result["weight_kg"] == 58.0


async def test_body_comp_history(db: AsyncSession, user: User):
    await log_body_composition(db, user.id, date(2026, 2, 1), body_fat_pct=25.0, weight_kg=60.0)
    await log_body_composition(db, user.id, date(2026, 3, 1), body_fat_pct=23.0, weight_kg=58.5)
    await db.flush()

    history = await get_body_composition_history(db, user.id, days=90)
    assert len(history) == 2
    assert history[0]["date"] == "2026-03-01"


async def test_body_comp_summary_with_change(db: AsyncSession, user: User):
    await log_body_composition(db, user.id, date(2026, 1, 15), body_fat_pct=25.0, weight_kg=60.0)
    await log_body_composition(db, user.id, date(2026, 3, 10), body_fat_pct=22.5, weight_kg=58.0)
    await db.flush()

    summary = await get_body_composition_summary(db, user.id, days=90)
    assert summary["total_measurements"] == 2
    assert summary["change"]["body_fat_pct"] == -2.5
    assert summary["change"]["weight_kg"] == -2.0


async def test_body_comp_summary_with_goal(db: AsyncSession, user: User):
    await update_profile(db, user.id, target_body_fat_pct=20.0)
    await log_body_composition(db, user.id, date(2026, 3, 10), body_fat_pct=22.5)
    await db.flush()

    summary = await get_body_composition_summary(db, user.id, days=90)
    assert summary["goals"]["target_body_fat_pct"] == 20.0
    assert summary["goals"]["gap"] == 2.5


async def test_log_inbody_full(db: AsyncSession, user: User):
    result = await log_body_composition(
        db,
        user.id,
        date(2026, 3, 12),
        body_fat_pct=22.5,
        weight_kg=58.0,
        muscle_mass_kg=24.5,
        visceral_fat_level=3,
        bmr=1280,
        score=78,
        segments=[
            {"segment": "left_arm", "muscle_mass_kg": 1.8, "muscle_grade": "standard",
             "fat_mass_kg": 0.9, "fat_grade": "standard"},
            {"segment": "right_arm", "muscle_mass_kg": 1.9, "muscle_grade": "standard",
             "fat_mass_kg": 0.8, "fat_grade": "standard"},
            {"segment": "trunk", "muscle_mass_kg": 18.0, "muscle_grade": "above",
             "fat_mass_kg": 5.2, "fat_grade": "standard"},
            {"segment": "left_leg", "muscle_mass_kg": 6.2, "muscle_grade": "standard",
             "fat_mass_kg": 3.1, "fat_grade": "above"},
            {"segment": "right_leg", "muscle_mass_kg": 6.3, "muscle_grade": "standard",
             "fat_mass_kg": 3.0, "fat_grade": "above"},
        ],
        inbody_data={"bmi": 22.1, "body_water_kg": 30.5},
    )
    await db.flush()

    assert result["visceral_fat_level"] == 3
    assert result["bmr"] == 1280
    assert result["score"] == 78
    assert len(result["segments"]) == 5

    history = await get_body_composition_history(db, user.id, days=90)
    assert len(history) == 1
    assert history[0]["visceral_fat_level"] == 3
    assert len(history[0]["segments"]) == 5
    assert history[0]["segments"][0]["segment"] == "left_arm"


async def test_body_comp_summary_empty(db: AsyncSession, user: User):
    summary = await get_body_composition_summary(db, user.id, days=90)
    assert summary["total_measurements"] == 0
