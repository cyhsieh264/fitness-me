"""Daily SQLite database backup with rotation (includes images)."""

import logging
import shutil
import sqlite3
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("data/backups")
IMAGE_DIR = Path("data/images")
MAX_BACKUPS = 7


def _db_path() -> Path:
    """Extract file path from database URL."""
    # "sqlite+aiosqlite:///data/fitness.db" -> "data/fitness.db"
    url = settings.database_url
    return Path(url.split("///", 1)[1])


async def backup_database() -> None:
    """Create a timestamped SQLite backup and rotate old ones."""
    from src.utils.time import now

    src_path = _db_path()
    if not src_path.exists():
        logger.warning("Database file not found: %s", src_path)
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = now().strftime("%Y%m%d_%H%M%S")
    dest_path = BACKUP_DIR / f"fitness_{timestamp}.db"

    # Use sqlite3 backup API for consistency (safe even during writes)
    src_conn = sqlite3.connect(str(src_path))
    dst_conn = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    # Copy images directory alongside DB backup
    images_dest = BACKUP_DIR / f"images_{timestamp}"
    if IMAGE_DIR.exists() and any(IMAGE_DIR.iterdir()):
        shutil.copytree(IMAGE_DIR, images_dest)
        logger.info("Images backed up to %s", images_dest)

    logger.info("Database backed up to %s", dest_path)

    # Rotate: keep only the latest MAX_BACKUPS
    backups = sorted(BACKUP_DIR.glob("fitness_*.db"), reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()
        # Remove matching images backup
        ts = old.stem.replace("fitness_", "")
        old_images = BACKUP_DIR / f"images_{ts}"
        if old_images.exists():
            shutil.rmtree(old_images)
        logger.info("Removed old backup: %s", old.name)
