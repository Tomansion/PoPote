"""Object storage for recipe photos, backed by RustFS.

RustFS is S3-compatible, so the generic `minio` package (an S3 client, not
tied to the MinIO server specifically) talks to it the same way it would to
MinIO, AWS S3, or anything else that speaks the S3 API.

Optional: a backend started without RUSTFS_ENDPOINT set simply never gets a
bucket, and photo upload reports itself unavailable rather than crashing the
request. Everything else in the app works without it.
"""

import logging
import uuid
from io import BytesIO
from typing import Optional
from urllib.parse import unquote, urlparse

from minio import Minio
from minio.error import S3Error

from .config import settings

logger = logging.getLogger(__name__)

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


def is_configured() -> bool:
    return bool(settings.rustfs_endpoint)


def _ensure_bucket(client: Minio) -> None:
    global _bucket_ready
    if _bucket_ready:
        return

    if not client.bucket_exists(settings.rustfs_bucket):
        client.make_bucket(settings.rustfs_bucket)

    # Public read: photos are shown straight in <img> tags, with no per-request
    # auth available to the browser.
    policy = (
        '{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", '
        '"Principal": {"AWS": ["*"]}, "Action": ["s3:GetObject"], '
        f'"Resource": ["arn:aws:s3:::{settings.rustfs_bucket}/*"]}}]}}'
    )
    client.set_bucket_policy(settings.rustfs_bucket, policy)
    _bucket_ready = True


def upload_image(
    data: bytes, content_type: str = "image/jpeg", suffix: str = "jpg"
) -> Optional[str]:
    """Store `data` and return its public URL, or None if storage isn't configured."""
    client = _get_client()
    if client is None:
        return None

    _ensure_bucket(client)
    object_name = f"{uuid.uuid4()}.{suffix}"
    client.put_object(
        settings.rustfs_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.rustfs_public_url}/{settings.rustfs_bucket}/{object_name}"


def delete_by_url(url: str) -> None:
    """Remove an object this module previously stored. Never raises.

    Called when a photo is replaced or deleted, so the bucket does not grow a
    copy of every picture anyone has ever cropped and re-uploaded. A URL from
    somewhere else — or one whose object is already gone — is ignored: losing
    an orphan is not worth failing the request the user actually made.
    """
    client = _get_client()
    if client is None or not url:
        return

    prefix = f"/{settings.rustfs_bucket}/"
    path = unquote(urlparse(url).path)
    if prefix not in path:
        return
    object_name = path.split(prefix, 1)[1]
    if not object_name:
        return

    try:
        client.remove_object(settings.rustfs_bucket, object_name)
    except S3Error as exc:
        logger.info("Could not delete %s: %s", object_name, exc)
