"""Storage backend selection.

Pick implementation via `STORAGE_PROVIDER` env var. The instance is cached
so callers can `from src.storage import storage` and share state.
"""

from functools import lru_cache

from src.config import settings
from src.storage.base import Storage
from src.storage.local import LocalStorage
from src.storage.supabase import SupabaseStorage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    provider = settings.storage_provider.lower()
    if provider == "supabase":
        return SupabaseStorage()
    if provider == "local":
        return LocalStorage()
    raise RuntimeError(f"unknown STORAGE_PROVIDER: {settings.storage_provider!r}")


__all__ = ["Storage", "LocalStorage", "SupabaseStorage", "get_storage"]
