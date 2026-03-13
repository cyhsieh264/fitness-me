"""User image storage, retrieval, and secure URL generation."""

import hashlib
import hmac
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import UserImage
from src.utils.time import timestamp, today

IMAGE_DIR = Path("data/images")

# In-memory cache of image_id -> image_path for token verification.
# Populated on demand; avoids DB lookup in the sync endpoint.
_path_cache: dict[int, str] = {}


def _sign(image_id: int) -> str:
    """Generate HMAC token for an image ID."""
    key = settings.line_channel_secret.encode()
    msg = f"image:{image_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:16]


def generate_image_url(image_id: int, image_path: str) -> str:
    """Generate a signed URL for an image."""
    _path_cache[image_id] = image_path
    token = _sign(image_id)
    return f"{settings.base_url}/images/{image_id}/{token}"


def verify_image_token(image_id: int, token: str) -> str | None:
    """Verify HMAC token and return image path if valid."""
    expected = _sign(image_id)
    if not hmac.compare_digest(token, expected):
        return None
    return _path_cache.get(image_id)


def save_image_file(
    line_user_id: str,
    category: str,
    message_id: str,
    image_bytes: bytes,
) -> str:
    """Save image to filesystem and return the path."""
    user_dir = IMAGE_DIR / line_user_id / category
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{message_id}.jpg"
    file_path = user_dir / filename
    file_path.write_bytes(image_bytes)
    return str(file_path)


async def save_image_record(
    db: AsyncSession,
    user_id: int,
    category: str,
    image_path: str,
    description: str | None = None,
    image_date: date | None = None,
) -> dict:
    record = UserImage(
        user_id=user_id,
        category=category,
        image_path=image_path,
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
        "image_path": record.image_path,
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
    """Get a signed URL for a specific image."""
    result = await db.execute(
        select(UserImage).where(UserImage.id == image_id, UserImage.user_id == user_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        return {"error": "Image not found"}

    url = generate_image_url(image.id, image.image_path)
    return {
        "id": image.id,
        "url": url,
        "category": image.category,
        "date": image.date.isoformat(),
        "description": image.description,
    }
