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


async def test_body_comp_summary_empty(db: AsyncSession, user: User):
    summary = await get_body_composition_summary(db, user.id, days=90)
    assert summary["total_measurements"] == 0
