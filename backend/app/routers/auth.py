"""Registration, login, and profile.

Three endpoints and nothing else: no email delivery, no password reset, no
refresh-token rotation. A token is issued once and lasts for years, which is
what makes "open the app on the phone and it is already my account" work
without any of that machinery.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..auth import CurrentUser, create_token, hash_password, verify_password
from ..config import settings
from ..models import AuthResponse, ProfileUpdate, UserPublic, UserRegister, UserLogin
from ..seed import DEMO_RECIPES

logger = logging.getLogger(__name__)

router = APIRouter()

# Deliberately identical for "unknown email" and "wrong password", so the API
# cannot be used to find out which addresses have an account.
BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Email ou mot de passe incorrect",
)


def _register(payload: UserRegister) -> UserPublic:
    if db.email_taken(payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte existe déjà avec cet email",
        )

    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = db.create_user(
        email=payload.email,
        password_hash=password_hash,
        display_name=payload.display_name,
        avatar_seed=payload.avatar_seed,
    )

    if settings.seed_demo_data:
        # A brand-new account with an empty recipe list has nothing to show;
        # seeding a copy of the demos gives it something to open onto.
        seeded = db.seed_recipes_for_user(DEMO_RECIPES, user.id)
        logger.info("Seeded %s demo recipes for %s", seeded, user.id)

    return user


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(payload: UserRegister) -> AuthResponse:
    user = await asyncio.to_thread(_register, payload)
    return AuthResponse(token=create_token(user.id), user=user)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: UserLogin) -> AuthResponse:
    doc = await asyncio.to_thread(db.get_user_auth, payload.email)
    if doc is None:
        raise BAD_CREDENTIALS

    ok = await asyncio.to_thread(
        verify_password, payload.password, doc.get("password_hash", "")
    )
    if not ok:
        raise BAD_CREDENTIALS

    user = UserPublic(
        id=doc["_key"],
        display_name=doc.get("display_name", ""),
        avatar_seed=doc.get("avatar_seed", 0),
        created_at=doc.get("created_at", ""),
    )
    return AuthResponse(token=create_token(user.id), user=user)


@router.get("/auth/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    """Validates a stored token on startup and refreshes the cached profile."""
    return user


@router.put("/auth/me", response_model=UserPublic)
async def update_me(payload: ProfileUpdate, user: CurrentUser) -> UserPublic:
    """Rename yourself, or save a rerolled avatar seed."""
    updated = await asyncio.to_thread(
        db.update_user_profile, user.id, payload.display_name, payload.avatar_seed
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return updated
