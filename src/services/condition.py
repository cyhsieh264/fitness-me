from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Exercise, UserCondition
from src.utils.time import timestamp, to_datetime


async def add_condition(
    db: AsyncSession,
    user_id: int,
    category: str,
    description: str,
    action_item: str | None = None,
    exercise_id: int | None = None,
    source_session_id: int | None = None,
    observed_at: int | None = None,
) -> UserCondition:
    condition = UserCondition(
        user_id=user_id,
        category=category,
        description=description,
        action_item=action_item,
        exercise_id=exercise_id,
        source_session_id=source_session_id,
        created_at=observed_at if observed_at is not None else timestamp(),
    )
    db.add(condition)
    await db.flush()
    return condition


async def resolve_condition(
    db: AsyncSession,
    user_id: int,
    condition_id: int,
) -> bool:
    result = await db.execute(
        select(UserCondition).where(
            UserCondition.id == condition_id,
            UserCondition.user_id == user_id,
            UserCondition.is_active.is_(True),
        )
    )
    condition = result.scalar_one_or_none()
    if not condition:
        return False

    condition.is_active = False
    condition.resolved_at = timestamp()
    return True


async def get_active_conditions(
    db: AsyncSession,
    user_id: int,
) -> list[dict]:
    result = await db.execute(
        select(UserCondition)
        .where(
            UserCondition.user_id == user_id,
            UserCondition.is_active.is_(True),
        )
        .order_by(UserCondition.created_at.desc())
    )
    conditions = result.scalars().all()

    items = []
    for c in conditions:
        item: dict = {
            "id": c.id,
            "category": c.category,
            "description": c.description,
            "action_item": c.action_item,
            "created_at": dt.isoformat() if (dt := to_datetime(c.created_at)) else None,
        }
        if c.exercise_id:
            exercise = await db.get(Exercise, c.exercise_id)
            if exercise:
                item["exercise"] = exercise.name_zh
        items.append(item)

    return items


async def get_exercise_notes(
    db: AsyncSession,
    user_id: int,
    exercise_id: int,
) -> list[dict]:
    """Get active conditions/notes linked to a specific exercise."""
    result = await db.execute(
        select(UserCondition)
        .where(
            UserCondition.user_id == user_id,
            UserCondition.exercise_id == exercise_id,
            UserCondition.is_active.is_(True),
        )
        .order_by(UserCondition.created_at.desc())
    )
    conditions = result.scalars().all()

    return [
        {
            "id": c.id,
            "category": c.category,
            "description": c.description,
            "action_item": c.action_item,
        }
        for c in conditions
    ]
