"""Supabase Storage implementation via REST API.

Uses the Service Role key for server-side access. Signed URLs are minted
by Supabase and have an explicit expiry, so we do not add our own HMAC.
"""

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def _raise_with_body(r: httpx.Response, op: str) -> None:
    """Like r.raise_for_status() but surfaces the response body in the log
    so 4xx from Supabase actually tells us what went wrong."""
    if r.is_success:
        return
    body = ""
    try:
        body = r.text[:500]
    except Exception:
        pass
    logger.error("Supabase storage %s failed: %s %s — body=%r", op, r.status_code, r.reason_phrase, body)
    r.raise_for_status()


class SupabaseStorage:
    def __init__(
        self,
        base_url: str | None = None,
        service_key: str | None = None,
        bucket: str | None = None,
    ) -> None:
        self.base = (base_url or settings.supabase_url).rstrip("/")
        self.key = service_key or settings.supabase_service_key
        self.bucket = bucket or settings.supabase_bucket
        if not (self.base and self.key and self.bucket):
            raise RuntimeError(
                "SupabaseStorage requires SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_BUCKET"
            )

    async def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        url = f"{self.base}/storage/v1/object/{self.bucket}/{key}"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": content_type,
            # Allow re-upload to the same key (e.g. re-processed image).
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, content=data, headers=headers)
            _raise_with_body(r, "save")

    async def signed_url(self, key: str, expires_in: int = 3600) -> str:
        url = f"{self.base}/storage/v1/object/sign/{self.bucket}/{key}"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"expiresIn": expires_in}, headers=headers)
            _raise_with_body(r, "signed_url")
            signed_path = r.json()["signedURL"]
        # Supabase returns a path like "/object/sign/bucket/key?token=..." — prefix with host.
        return f"{self.base}/storage/v1{signed_path}"

    async def delete(self, key: str) -> None:
        url = f"{self.base}/storage/v1/object/{self.bucket}/{key}"
        headers = {"Authorization": f"Bearer {self.key}"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url, headers=headers)
            # 404 is fine — already gone.
            if r.status_code not in (200, 404):
                r.raise_for_status()
