"""Storage abstraction shared by local filesystem and cloud backends."""

from typing import Protocol


class Storage(Protocol):
    """Opaque blob store keyed by string paths.

    `key` is storage-relative (e.g. "U123/inbody/abc.jpg"). The interface
    is content-addressable from the caller's view: callers do not need to
    know whether the bytes live on a local disk or in object storage.
    """

    async def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        """Persist `data` under `key`. Overwrites if the key exists."""

    async def signed_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a URL the client can fetch to read the blob."""

    async def delete(self, key: str) -> None:
        """Remove the blob at `key`. No-op if it does not exist."""
