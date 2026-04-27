"""User image flow: upload via Storage, persist record, mint signed URL."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import UserImage
from src.storage import get_storage
from src.utils.time import timestamp, today


def build_storage_key(line_user_id: str, category: str, message_id: str) -> str:
    return f"{line_user_id}/{category}/{message_id}.jpg"


async def save_image(
    db: AsyncSession,
    user_id: int,
    line_user_id: str,
    category: str,
    message_id: str,
    image_bytes: bytes,
    description: str | None = None,
    image_date: date | None = None,
) -> dict:
    """Upload bytes to storage and persist a UserImage row in one call."""
    key = build_storage_key(line_user_id, category, message_id)
    await get_storage().save(key, image_bytes)

    record = UserImage(
        user_id=user_id,
        category=category,
        storage_key=key,
        description=description,
        date=image_date or today(),
        created_at=timestamp(),
    )
    db.add(record)
    await db.flush()
    return {
        "id": record.id,
        "category": record.category,
        "date": record.date.isoformat(),
        "storage_key": record.storage_key,
        "description": record.description,
    }


async def get_image_history(
    db: AsyncSession,
    user_id: int,
    category: str | None = None,
    limit: int = 20,
) -> list[dict]:
    query = select(UserImage).where(UserImage.user_id == user_id)
    if category:
        query = query.where(UserImage.category == category)
    query = query.order_by(UserImage.date.desc()).limit(limit)

    result = await db.execute(query)
    return [
        {
            "id": r.id,
            "category": r.category,
            "date": r.date.isoformat(),
            "description": r.description,
        }
        for r in result.scalars().all()
    ]


async def get_image_url(
    db: AsyncSession,
    user_id: int,
    image_id: int,
) -> dict:
    result = await db.execute(
        select(UserImage).where(UserImage.id == image_id, UserImage.user_id == user_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        return {"error": "Image not found"}

    url = await get_storage().signed_url(image.storage_key)
    return {
        "id": image.id,
        "url": url,
        "category": image.category,
        "date": image.date.isoformat(),
        "description": image.description,
    }
