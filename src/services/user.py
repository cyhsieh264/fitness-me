from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.utils.time import timestamp


async def get_or_create_user(
    db: AsyncSession,
    line_user_id: str,
    display_name: str | None = None,
) -> User:
    result = await db.execute(select(User).where(User.line_user_id == line_user_id))
    existing: User | None = result.scalar_one_or_none()
    if existing:
        return existing

    user = User(line_user_id=line_user_id, display_name=display_name, created_at=timestamp())
    db.add(user)
    await db.flush()
    return user


async def get_user_by_line_id(db: AsyncSession, line_user_id: str) -> User | None:
    """Get user by LINE user ID."""
    result = await db.execute(select(User).where(User.line_user_id == line_user_id))
    user: User | None = result.scalar_one_or_none()
    return user


async def get_active_line_user_ids(db: AsyncSession) -> list[str]:
    """Get LINE user IDs of all active users."""
    result = await db.execute(select(User.line_user_id).where(User.is_active.is_(True)))
    return list(result.scalars().all())
