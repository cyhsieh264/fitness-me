"""Local filesystem Storage implementation.

Used for development and as a Fly.io volume-backed fallback. Signed URLs
point back to this app's `/images/{b64}/{token}` route, which calls
`verify_and_path()` to authenticate the request.
"""

import base64
import hashlib
import hmac
from pathlib import Path

from src.config import settings

# Root directory for stored blobs. Sits inside the project so it can be mounted
# as a Fly volume in production.
ROOT = Path("data/images")


class LocalStorage:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root

    async def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def signed_url(self, key: str, expires_in: int = 3600) -> str:
        # `expires_in` is accepted for interface compatibility; LocalStorage
        # currently uses HMAC without expiry to match the original design.
        b64 = base64.urlsafe_b64encode(key.encode()).rstrip(b"=").decode()
        token = self._sign(key)
        return f"{settings.base_url}/images/{b64}/{token}"

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def verify_and_path(self, b64_key: str, token: str) -> Path | None:
        """Used by the FastAPI route serving signed URLs."""
        try:
            padding = "=" * (-len(b64_key) % 4)
            key = base64.urlsafe_b64decode(b64_key + padding).decode()
        except (ValueError, UnicodeDecodeError):
            return None
        if not hmac.compare_digest(token, self._sign(key)):
            return None
        path = self._resolve(key)
        return path if path.exists() else None

    def _resolve(self, key: str) -> Path:
        # Reject absolute keys and traversal attempts.
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError(f"invalid storage key: {key!r}")
        return self.root / key

    @staticmethod
    def _sign(key: str) -> str:
        secret = settings.line_channel_secret.encode()
        return hmac.new(secret, key.encode(), hashlib.sha256).hexdigest()[:16]
