"""Registration, login, profile, and other people's pages.

No email delivery, no password reset, no refresh-token rotation. A token is
issued once and lasts for years, which is what makes "open the app on the
phone and it is already my account" work without any of that machinery.

A profile carries ten optional answers about what its owner eats and likes.
They are visible to whoever shares an event with them and to nobody else —
the same rule that governs recipes, and for the same reason: an event is the
only place two accounts ever meet.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..auth import CurrentUser, create_token, hash_password, verify_password
from ..config import settings
from ..models import (
    AuthResponse,
    ProfileUpdate,
    PublicProfile,
    UserProfile,
    UserRegister,
    UserLogin,
)
from ..seed import DEMO_RECIPES

logger = logging.getLogger(__name__)

router = APIRouter()

# Deliberately identical for "unknown email" and "wrong password", so the API
# cannot be used to find out which addresses have an account.
BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Email ou mot de passe incorrect",
)


def _register(payload: UserRegister) -> UserProfile:
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

    # Re-read through the same mapping every other endpoint uses, rather than
    # assembling a user from the auth document by hand — one place decides
    # what a profile looks like.
    user = await asyncio.to_thread(db.get_user, doc["_key"])
    if user is None:
        raise BAD_CREDENTIALS
    return AuthResponse(token=create_token(user.id), user=user)


@router.get("/auth/me", response_model=UserProfile)
async def me(user: CurrentUser) -> UserProfile:
    """Validates a stored token on startup and refreshes the cached profile."""
    return user


@router.put("/auth/me", response_model=UserProfile)
async def update_me(payload: ProfileUpdate, user: CurrentUser) -> UserProfile:
    """Rename yourself, reroll the avatar, or answer the questions."""
    updated = await asyncio.to_thread(
        db.update_user_profile,
        user.id,
        payload.display_name,
        payload.avatar_seed,
        payload.prefs,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return updated


@router.get("/users/{user_id}", response_model=PublicProfile)
async def public_profile(user_id: str, user: CurrentUser) -> PublicProfile:
    """Someone else's page: their answers, and the recipes you may read.

    Gated on sharing an event with them. Someone you have never planned
    anything with reads as 404, exactly like a recipe of theirs would — the
    API does not confirm that an account id exists.
    """
    profile = await asyncio.to_thread(db.get_user, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    recipes = await asyncio.to_thread(db.list_recipes_for_viewer, user_id, user.id)
    if recipes is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    return PublicProfile(user=profile, recipes=recipes)
