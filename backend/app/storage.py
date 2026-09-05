"""Object storage for AI-generated recipe images, backed by RustFS.

RustFS is S3-compatible, so the generic `minio` package (an S3 client, not
tied to the MinIO server specifically) talks to it the same way it would to
MinIO, AWS S3, or anything else that speaks the S3 API.

Optional, like the AI features that populate it: a backend started without
RUSTFS_ENDPOINT set simply never gets a bucket, and image generation then
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
    if not settings.rustfs_endpoint:
        return None
    if _client is None:
        _client = Minio(
            settings.rustfs_endpoint,
            access_key=settings.rustfs_access_key,
            secret_key=settings.rustfs_secret_key,
            secure=settings.rustfs_secure,
        )
    return _client


def _ensure_bucket(client: Minio) -> None:
    global _bucket_ready
    if _bucket_ready:
        return

    if not client.bucket_exists(settings.rustfs_bucket):
        client.make_bucket(settings.rustfs_bucket)

    # Public read: generated images are shown straight in <img> tags, with no
    # per-request auth available to the browser.
    policy = (
        '{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", '
        '"Principal": {"AWS": ["*"]}, "Action": ["s3:GetObject"], '
        f'"Resource": ["arn:aws:s3:::{settings.rustfs_bucket}/*"]}}]}}'
    )
    client.set_bucket_policy(settings.rustfs_bucket, policy)
    _bucket_ready = True


def upload_image(data: bytes, content_type: str = "image/png") -> Optional[str]:
    """Store `data` and return its public URL, or None if storage isn't configured."""
    client = _get_client()
    if client is None:
        return None

    _ensure_bucket(client)
    object_name = f"{uuid.uuid4()}.png"
    client.put_object(
        settings.rustfs_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.rustfs_public_url}/{settings.rustfs_bucket}/{object_name}"
