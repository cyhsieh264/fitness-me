from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import UserProfile
from src.utils.time import timestamp


async def get_or_create_profile(
    db: AsyncSession,
    user_id: int,
) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    existing: UserProfile | None = result.scalar_one_or_none()
    if existing:
        return existing

    profile = UserProfile(user_id=user_id, updated_at=timestamp())
    db.add(profile)
    await db.flush()
    return profile


async def update_profile(
    db: AsyncSession,
    user_id: int,
    **fields: object,
) -> dict[str, object]:
    profile = await get_or_create_profile(db, user_id)

    allowed = {
        "fitness_goals",
        "training_habit",
        "cardio_status",
        "target_body_fat_pct",
        "target_max_hr",
        "notes",
    }
    updated = []
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(profile, key, value)
            updated.append(key)

    if updated:
        profile.updated_at = timestamp()

    return {
        "updated_fields": updated,
        "fitness_goals": profile.fitness_goals,
        "training_habit": profile.training_habit,
    }


async def get_profile_summary(
    db: AsyncSession,
    user_id: int,
) -> dict:
    profile = await get_or_create_profile(db, user_id)
    return {
        "fitness_goals": profile.fitness_goals,
        "training_habit": profile.training_habit,
        "cardio_status": profile.cardio_status,
        "target_body_fat_pct": profile.target_body_fat_pct,
        "target_max_hr": profile.target_max_hr,
    }
