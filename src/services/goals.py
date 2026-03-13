"""User goal tracking: set, update, and query goals."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import UserGoal
from src.utils.time import timestamp


async def set_goal(
    db: AsyncSession,
    user_id: int,
    category: str,
    description: str,
    target_value: float | None = None,
    target_unit: str | None = None,
    deadline: int | None = None,
) -> dict:
    goal = UserGoal(
        user_id=user_id,
        category=category,
        description=description,
        target_value=target_value,
        target_unit=target_unit,
        deadline=deadline,
        status="active",
        created_at=timestamp(),
    )
    db.add(goal)
    await db.flush()

    return _goal_to_dict(goal)


async def update_goal(
    db: AsyncSession,
    user_id: int,
    goal_id: int,
    status: str | None = None,
    description: str | None = None,
    target_value: float | None = None,
    deadline: int | None = None,
) -> dict:
    result = await db.execute(
        select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found"}

    if description is not None:
        goal.description = description
    if target_value is not None:
        goal.target_value = target_value
    if deadline is not None:
        goal.deadline = deadline
    if status is not None:
        goal.status = status
        if status == "achieved":
            goal.achieved_at = timestamp()

    return _goal_to_dict(goal)


async def get_active_goals(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(UserGoal)
        .where(UserGoal.user_id == user_id, UserGoal.status == "active")
        .order_by(UserGoal.created_at.desc())
    )
    return [_goal_to_dict(g) for g in result.scalars().all()]


def _goal_to_dict(goal: UserGoal) -> dict:
    d: dict = {
        "id": goal.id,
        "category": goal.category,
        "description": goal.description,
        "status": goal.status,
    }
    if goal.target_value is not None:
        d["target_value"] = goal.target_value
        d["target_unit"] = goal.target_unit
    if goal.deadline is not None:
        d["deadline"] = goal.deadline
    if goal.achieved_at is not None:
        d["achieved_at"] = goal.achieved_at
    return d
