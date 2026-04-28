"""Fitness-profile fields on the user row.

These are soft, narrative attributes the LLM injects into the system prompt
(training cadence, current focus, target body fat, etc.). Concrete, deadlined
goals live in user_goals — keep the two responsibilities separate.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BodyComposition, User
from src.utils.time import timestamp

PROFILE_FIELDS = (
    "training_habit",
    "cardio_status",
    "target_body_fat_pct",
    "target_max_hr",
    "notes",
)


async def update_profile(
    db: AsyncSession,
    user_id: int,
    **fields: object,
) -> dict[str, object]:
    user = await _get_user(db, user_id)

    updated: list[str] = []
    for key, value in fields.items():
        if key in PROFILE_FIELDS and value is not None:
            setattr(user, key, value)
            updated.append(key)

    if updated:
        user.profile_updated_at = timestamp()

    return {
        "updated_fields": updated,
        "training_habit": user.training_habit,
        "cardio_status": user.cardio_status,
    }


async def get_profile_summary(db: AsyncSession, user_id: int) -> dict:
    user = await _get_user(db, user_id)

    # Latest recorded weight powers cardio calorie estimation. Surfacing it
    # here lets the LLM know whether to ask for it before logging cardio.
    weight_result = await db.execute(
        select(BodyComposition.weight_kg)
        .where(
            BodyComposition.user_id == user_id,
            BodyComposition.weight_kg.isnot(None),
        )
        .order_by(BodyComposition.date.desc())
        .limit(1)
    )
    latest_weight = weight_result.scalar_one_or_none()

    return {
        "training_habit": user.training_habit,
        "cardio_status": user.cardio_status,
        "target_body_fat_pct": user.target_body_fat_pct,
        "target_max_hr": user.target_max_hr,
        "latest_weight_kg": float(latest_weight) if latest_weight else None,
    }


async def _get_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    return user
