"""Tests for user goal tracking."""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.services.goals import get_active_goals, set_goal, update_goal


async def test_set_goal(db: AsyncSession, user: User):
    result = await set_goal(
        db, user.id, "body_comp", "body fat to 22%",
        target_value=22.0, target_unit="%",
    )
    await db.flush()

    assert result["category"] == "body_comp"
    assert result["description"] == "body fat to 22%"
    assert result["target_value"] == 22.0
    assert result["status"] == "active"


async def test_set_goal_without_target(db: AsyncSession, user: User):
    result = await set_goal(db, user.id, "general", "improve running posture")
    await db.flush()

    assert result["category"] == "general"
    assert "target_value" not in result


async def test_multiple_active_goals(db: AsyncSession, user: User):
    await set_goal(db, user.id, "body_comp", "body fat 22%", target_value=22.0)
    await set_goal(db, user.id, "strength", "squat 80kg", target_value=80.0)
    await db.flush()

    active = await get_active_goals(db, user.id)
    assert len(active) == 2


async def test_update_goal_achieved(db: AsyncSession, user: User):
    result = await set_goal(db, user.id, "body_comp", "body fat 22%")
    await db.flush()

    updated = await update_goal(db, user.id, result["id"], status="achieved")
    assert updated["status"] == "achieved"
    assert "achieved_at" in updated

    active = await get_active_goals(db, user.id)
    assert len(active) == 0


async def test_update_goal_abandoned(db: AsyncSession, user: User):
    result = await set_goal(db, user.id, "habit", "train 4x/week")
    await db.flush()

    updated = await update_goal(db, user.id, result["id"], status="abandoned")
    assert updated["status"] == "abandoned"

    active = await get_active_goals(db, user.id)
    assert len(active) == 0


async def test_update_goal_description(db: AsyncSession, user: User):
    result = await set_goal(db, user.id, "strength", "squat 60kg")
    await db.flush()

    updated = await update_goal(
        db, user.id, result["id"],
        description="squat 80kg", target_value=80.0,
    )
    assert updated["description"] == "squat 80kg"
    assert updated["target_value"] == 80.0


async def test_update_goal_not_found(db: AsyncSession, user: User):
    result = await update_goal(db, user.id, 9999, status="achieved")
    assert result["error"] == "Goal not found"
