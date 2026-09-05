"""Object storage for AI-generated recipe images, backed by MinIO.

Optional, like the AI features that populate it: a backend started without
MINIO_ENDPOINT set simply never gets a bucket, and image generation then
reports itself unavailable rather than crashing the request.
"""

import uuid
from io import BytesIO
from typing import Optional

from minio import Minio

from .config import settings

_client: Optional[Minio] = None
_bucket_ready = False


def _get_client() -> Optional[Minio]:
    global _client
    if not settings.minio_endpoint:
        return None
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def _ensure_bucket(client: Minio) -> None:
    global _bucket_ready
    if _bucket_ready:
        return

    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)

    # Public read: generated images are shown straight in <img> tags, with no
    # per-request auth available to the browser.
    policy = (
        '{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", '
        '"Principal": {"AWS": ["*"]}, "Action": ["s3:GetObject"], '
        f'"Resource": ["arn:aws:s3:::{settings.minio_bucket}/*"]}}]}}'
    )
    client.set_bucket_policy(settings.minio_bucket, policy)
    _bucket_ready = True


def upload_image(data: bytes, content_type: str = "image/png") -> Optional[str]:
    """Store `data` and return its public URL, or None if storage isn't configured."""
    client = _get_client()
    if client is None:
        return None

    _ensure_bucket(client)
    object_name = f"{uuid.uuid4()}.png"
    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.minio_public_url}/{settings.minio_bucket}/{object_name}"
