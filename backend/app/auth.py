"""Password hashing, session tokens, and the request dependencies that use them.

The scheme is deliberately the plainest thing that works on both targets: a
bearer token in the `Authorization` header, no cookies. The APK runs from
`https://localhost`, an origin that makes cross-site cookies painful, and a
bearer header lets CORS stay at `allow_credentials=False`.

Tokens are long-lived (see `settings.jwt_ttl_days`) and carry no server-side
session, so a restart never logs anyone out — provided the signing key is
stable, which `resolve_secret` guarantees by persisting one in ArangoDB.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import settings
from .models import UserPublic

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

# Resolved once at startup by `init_secret()`.
_secret: Optional[str] = None

# auto_error=False so a missing header produces our own 401 with a JSON body,
# rather than FastAPI's bare 403.
_bearer = HTTPBearer(auto_error=False)


def init_secret() -> None:
    """Pin down the signing key, generating and storing one on first start.

    An explicit `JWT_SECRET` always wins. Otherwise the key is read from (or
    written to) ArangoDB, so tokens survive a container restart, a rebuild, or
    a redeploy with no configuration at all. A key held only in process memory
    would invalidate every session on each restart, which is exactly what the
    long TTL is meant to avoid.
    """
    global _secret

    if settings.jwt_secret.strip():
        _secret = settings.jwt_secret.strip()
        logger.info("Signing sessions with JWT_SECRET from the environment")
        return

    _secret = db.get_or_create_jwt_secret()
    logger.info("Signing sessions with the key stored in ArangoDB")


def _get_secret() -> str:
    if _secret is None:
        raise RuntimeError("Auth not initialised; call init_secret() first")
    return _secret


# ------------------------------------------------------------------ passwords


def hash_password(password: str) -> str:
    # bcrypt silently truncates at 72 bytes; rejecting is better than a
    # password that quietly ignores everything the user typed past it.
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("password must be at most 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------- tokens


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_ttl_days)).timestamp()),
        # Lets a token be invalidated later without any server-side session
        # store, by bumping a per-user value. Unused for now.
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def user_id_from_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    return user_id if isinstance(user_id, str) else None


# --------------------------------------------------------------- dependencies


UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Session expirée, reconnectez-vous",
    headers={"WWW-Authenticate": "Bearer"},
)


async def current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> UserPublic:
    if credentials is None or not credentials.credentials:
        raise UNAUTHORIZED

    user_id = user_id_from_token(credentials.credentials)
    if user_id is None:
        raise UNAUTHORIZED

    user = db.get_user(user_id)
    if user is None:
        # Valid signature, but the account is gone.
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[UserPublic, Depends(current_user)]


def user_from_ws_token(token: Optional[str]) -> Optional[UserPublic]:
    """Authenticate a WebSocket handshake.

    Browsers cannot set headers on a WebSocket handshake, so the token arrives
    as a `?token=` query parameter instead. It is the same token and the same
    verification; only the transport differs.
    """
    if not token:
        return None
    user_id = user_id_from_token(token)
    if user_id is None:
        return None
    return db.get_user(user_id)
