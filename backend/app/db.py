"""ArangoDB access layer.

Four document collections: `recipes`, `users`, `events`, and `app_settings`
(a single row holding the generated token-signing key). Arango's `_key` is
exposed to the API as `id`; everything else maps 1:1 to the Pydantic model.

Every recipe belongs to exactly one user. The owner check lives here rather
than in the routers, so there is one place where "can this user touch this
document" is decided and no endpoint can forget to ask.
"""

import logging
import secrets
import time
from typing import Any, Optional

from arango import ArangoClient
from arango.database import StandardDatabase
from arango.exceptions import (
    ArangoServerError,
    DatabaseCreateError,
    DocumentInsertError,
    ServerConnectionError,
)

from .aisles import detect_aisle
from .config import settings
from .models import (
    Event,
    EventCreate,
    EventUpdate,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    UserPublic,
    utcnow_iso,
)

logger = logging.getLogger(__name__)

COLLECTION = "recipes"
USERS = "users"
EVENTS = "events"
APP_SETTINGS = "app_settings"

# No 0/O/1/I/L: invite codes get read aloud and retyped from a phone screen.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8

_db: Optional[StandardDatabase] = None


def _ensure_database(client: ArangoClient) -> StandardDatabase:
    """Open the target database, creating it only if we are allowed to.

    A scoped user (one granted rights on `popote` alone) cannot read
    `_system`, so the happy path is to open the database directly. Creating it
    is only attempted as a fallback, for a local/dev root user pointed at an
    empty server.
    """
    db = client.db(
        settings.arango_db,
        username=settings.arango_user,
        password=settings.arango_password,
    )

    try:
        db.properties()  # Cheap round-trip that proves credentials and access.
        return db
    except (DatabaseCreateError, ArangoServerError) as exc:
        logger.info(
            "Database %r not directly usable (%s); trying to create it via _system",
            settings.arango_db,
            exc,
        )

    sys_db = client.db(
        "_system",
        username=settings.arango_user,
        password=settings.arango_password,
    )
    if not sys_db.has_database(settings.arango_db):
        sys_db.create_database(settings.arango_db)

    return client.db(
        settings.arango_db,
        username=settings.arango_user,
        password=settings.arango_password,
    )


def connect(max_attempts: int = 30, delay_seconds: float = 2.0) -> StandardDatabase:
    """Connect to Arango and make sure the recipes collection exists.

    Retries on connection failure: under docker-compose the API container
    regularly wins the race against ArangoDB's first start.
    """
    global _db

    client = ArangoClient(hosts=settings.arango_url)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            db = _ensure_database(client)

            for name in (COLLECTION, USERS, EVENTS, APP_SETTINGS):
                if not db.has_collection(name):
                    db.create_collection(name)

            collection = db.collection(COLLECTION)
            collection.add_persistent_index(fields=["name"], unique=False)
            collection.add_persistent_index(fields=["updated_at"], unique=False)
            collection.add_persistent_index(fields=["owner_id"], unique=False)

            users = db.collection(USERS)
            # Unique on the normalised email: this is what stops two accounts
            # differing only in case or stray whitespace.
            users.add_persistent_index(fields=["email"], unique=True)

            events = db.collection(EVENTS)
            events.add_persistent_index(fields=["invite_code"], unique=True)
            events.add_persistent_index(fields=["member_ids[*]"], unique=False)

            _db = db
            logger.info(
                "Connected to ArangoDB at %s (database %r)",
                settings.arango_url,
                settings.arango_db,
            )
            return db
        except (ServerConnectionError, ConnectionError, OSError) as exc:
            last_error = exc
            logger.warning(
                "ArangoDB not reachable (attempt %s/%s): %s", attempt, max_attempts, exc
            )
            time.sleep(delay_seconds)

    raise RuntimeError(
        f"Could not connect to ArangoDB at {settings.arango_url}"
    ) from last_error


def get_db() -> StandardDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised; call connect() first")
    return _db


def _to_recipe(doc: dict[str, Any]) -> Recipe:
    payload = {k: v for k, v in doc.items() if not k.startswith("_")}
    payload["id"] = doc["_key"]
    return Recipe(**payload)


def _fill_aisles(payload: dict[str, Any]) -> dict[str, Any]:
    for ingredient in payload.get("ingredients", []):
        if not ingredient.get("aisle"):
            ingredient["aisle"] = detect_aisle(ingredient.get("name", ""))
    return payload


def list_recipes(owner_id: str) -> list[Recipe]:
    cursor = get_db().aql.execute(
        f"FOR r IN {COLLECTION} FILTER r.owner_id == @owner "
        "SORT LOWER(r.name) ASC RETURN r",
        bind_vars={"owner": owner_id},
    )
    return [_to_recipe(doc) for doc in cursor]


def get_recipe(recipe_id: str, owner_id: str) -> Optional[Recipe]:
    """Fetch a recipe, but only for the user who owns it.

    A recipe belonging to someone else is reported as missing rather than
    forbidden, so the API never confirms that an id someone guessed exists.
    """
    doc = get_db().collection(COLLECTION).get(recipe_id)
    if not doc or doc.get("owner_id") != owner_id:
        return None
    return _to_recipe(doc)


def create_recipe(data: RecipeCreate, owner_id: str) -> Recipe:
    now = utcnow_iso()
    payload = _fill_aisles(data.model_dump())
    payload["owner_id"] = owner_id
    payload["created_at"] = now
    payload["updated_at"] = now

    meta = get_db().collection(COLLECTION).insert(payload, return_new=True)
    return _to_recipe(meta["new"])


def update_recipe(recipe_id: str, data: RecipeUpdate, owner_id: str) -> Optional[Recipe]:
    collection = get_db().collection(COLLECTION)
    existing = collection.get(recipe_id)
    if not existing or existing.get("owner_id") != owner_id:
        return None

    payload = _fill_aisles(data.model_dump())
    payload["_key"] = recipe_id
    # Ownership is never taken from the request body.
    payload["owner_id"] = owner_id
    payload["created_at"] = existing.get("created_at", utcnow_iso())
    payload["updated_at"] = utcnow_iso()

    meta = collection.replace(payload, return_new=True)
    return _to_recipe(meta["new"])


def delete_recipe(recipe_id: str, owner_id: str) -> bool:
    collection = get_db().collection(COLLECTION)
    existing = collection.get(recipe_id)
    if not existing or existing.get("owner_id") != owner_id:
        return False
    return bool(collection.delete(recipe_id, ignore_missing=True))


def count_recipes() -> int:
    return get_db().collection(COLLECTION).count()


def seed_recipes_for_user(recipes: list[RecipeCreate], owner_id: str) -> int:
    """Give a freshly registered account its own copy of the demo recipes.

    Recipes are per-user, so there is no longer an ownerless set to seed once
    at boot: an empty account with nothing in it is the thing worth avoiding.
    """
    inserted = 0
    for recipe in recipes:
        try:
            create_recipe(recipe, owner_id)
            inserted += 1
        except DocumentInsertError as exc:
            logger.warning("Could not seed recipe %r: %s", recipe.name, exc)
    return inserted


# ------------------------------------------------------------ signing key


def get_or_create_jwt_secret() -> str:
    """Read the stored token-signing key, generating it on first call.

    Kept in the database rather than in memory so that restarting the backend
    does not invalidate every issued token.
    """
    collection = get_db().collection(APP_SETTINGS)

    doc = collection.get("jwt_secret")
    if doc and doc.get("value"):
        return doc["value"]

    secret = secrets.token_urlsafe(48)
    try:
        collection.insert({"_key": "jwt_secret", "value": secret})
    except DocumentInsertError:
        # Another worker inserted it between the read and the write; theirs wins,
        # otherwise the two processes would sign with different keys.
        doc = collection.get("jwt_secret")
        if doc and doc.get("value"):
            return doc["value"]
        raise
    return secret


# ------------------------------------------------------------------ users


def _to_user(doc: dict[str, Any]) -> UserPublic:
    return UserPublic(
        id=doc["_key"],
        display_name=doc.get("display_name", ""),
        avatar_seed=doc.get("avatar_seed", 0),
        created_at=doc.get("created_at", ""),
    )


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_user(user_id: str) -> Optional[UserPublic]:
    doc = get_db().collection(USERS).get(user_id)
    return _to_user(doc) if doc else None


def get_users(user_ids: list[str]) -> list[UserPublic]:
    if not user_ids:
        return []
    cursor = get_db().aql.execute(
        f"FOR u IN {USERS} FILTER u._key IN @ids RETURN u",
        bind_vars={"ids": user_ids},
    )
    by_id = {doc["_key"]: _to_user(doc) for doc in cursor}
    # Preserve the caller's order, and skip ids whose account has been deleted.
    return [by_id[uid] for uid in user_ids if uid in by_id]


def get_user_auth(email: str) -> Optional[dict[str, Any]]:
    """The raw document, including the password hash. Login only."""
    cursor = get_db().aql.execute(
        f"FOR u IN {USERS} FILTER u.email == @email LIMIT 1 RETURN u",
        bind_vars={"email": normalise_email(email)},
    )
    docs = list(cursor)
    return docs[0] if docs else None


def email_taken(email: str) -> bool:
    return get_user_auth(email) is not None


def create_user(
    email: str, password_hash: str, display_name: str, avatar_seed: int
) -> UserPublic:
    payload = {
        "email": normalise_email(email),
        "password_hash": password_hash,
        "display_name": display_name,
        "avatar_seed": avatar_seed,
        "created_at": utcnow_iso(),
    }
    meta = get_db().collection(USERS).insert(payload, return_new=True)
    return _to_user(meta["new"])


def update_user_profile(
    user_id: str, display_name: Optional[str], avatar_seed: Optional[int]
) -> Optional[UserPublic]:
    patch: dict[str, Any] = {"_key": user_id}
    if display_name is not None:
        patch["display_name"] = display_name
    if avatar_seed is not None:
        patch["avatar_seed"] = avatar_seed

    if len(patch) == 1:
        return get_user(user_id)

    collection = get_db().collection(USERS)
    if not collection.has(user_id):
        return None
    meta = collection.update(patch, return_new=True, keep_none=False)
    return _to_user(meta["new"])


# ----------------------------------------------------------------- events


def _to_event(doc: dict[str, Any], hydrate: bool = True) -> Event:
    member_ids = doc.get("member_ids", [])
    return Event(
        id=doc["_key"],
        name=doc.get("name", ""),
        starts_on=doc["starts_on"],
        ends_on=doc["ends_on"],
        owner_id=doc.get("owner_id", ""),
        invite_code=doc.get("invite_code", ""),
        member_ids=member_ids,
        members=get_users(member_ids) if hydrate else [],
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def _unique_invite_code() -> str:
    collection = get_db().collection(EVENTS)
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        cursor = get_db().aql.execute(
            f"FOR e IN {EVENTS} FILTER e.invite_code == @code LIMIT 1 RETURN 1",
            bind_vars={"code": code},
        )
        if not list(cursor):
            return code
    raise RuntimeError("Could not allocate a free invite code")


def list_events(user_id: str) -> list[Event]:
    """Every event the user belongs to, soonest first."""
    cursor = get_db().aql.execute(
        f"FOR e IN {EVENTS} FILTER @uid IN e.member_ids "
        "SORT e.starts_on ASC, LOWER(e.name) ASC RETURN e",
        bind_vars={"uid": user_id},
    )
    return [_to_event(doc) for doc in cursor]


def get_event(event_id: str, user_id: str) -> Optional[Event]:
    doc = get_db().collection(EVENTS).get(event_id)
    if not doc or user_id not in doc.get("member_ids", []):
        return None
    return _to_event(doc)


def get_event_raw(event_id: str) -> Optional[Event]:
    """Fetch an event with no membership check.

    For internal use only — notifying the remaining members after someone has
    just removed themselves, when `get_event` would (correctly) refuse.
    """
    doc = get_db().collection(EVENTS).get(event_id)
    return _to_event(doc) if doc else None


def get_event_by_code(invite_code: str) -> Optional[Event]:
    """Look an event up by invite code, with no membership requirement.

    This is what backs the invite link, so it must work for someone who is not
    a member yet. Callers are responsible for only exposing the preview fields.
    """
    cursor = get_db().aql.execute(
        f"FOR e IN {EVENTS} FILTER e.invite_code == @code LIMIT 1 RETURN e",
        bind_vars={"code": invite_code.strip().upper()},
    )
    docs = list(cursor)
    return _to_event(docs[0]) if docs else None


def create_event(data: EventCreate, owner_id: str) -> Event:
    now = utcnow_iso()
    payload = data.model_dump(mode="json")
    payload["owner_id"] = owner_id
    payload["invite_code"] = _unique_invite_code()
    # The creator is a member from the start, so one query lists every event
    # you belong to without special-casing the one you own.
    payload["member_ids"] = [owner_id]
    payload["created_at"] = now
    payload["updated_at"] = now

    meta = get_db().collection(EVENTS).insert(payload, return_new=True)
    return _to_event(meta["new"])


def update_event(event_id: str, data: EventUpdate, user_id: str) -> Optional[Event]:
    """Rename or reschedule. Owner only — members can join and leave, not edit."""
    collection = get_db().collection(EVENTS)
    existing = collection.get(event_id)
    if not existing or existing.get("owner_id") != user_id:
        return None

    patch = data.model_dump(mode="json")
    patch["_key"] = event_id
    patch["updated_at"] = utcnow_iso()

    meta = collection.update(patch, return_new=True)
    return _to_event(meta["new"])


def delete_event(event_id: str, user_id: str) -> Optional[list[str]]:
    """Delete an event. Returns the members to notify, or None if not allowed."""
    collection = get_db().collection(EVENTS)
    existing = collection.get(event_id)
    if not existing or existing.get("owner_id") != user_id:
        return None

    members = list(existing.get("member_ids", []))
    collection.delete(event_id, ignore_missing=True)
    return members


def join_event(invite_code: str, user_id: str) -> Optional[Event]:
    """Add the user to the event the code names. Idempotent."""
    event = get_event_by_code(invite_code)
    if event is None:
        return None

    if user_id in event.member_ids:
        return event

    collection = get_db().collection(EVENTS)
    meta = collection.update(
        {"_key": event.id, "member_ids": event.member_ids + [user_id],
         "updated_at": utcnow_iso()},
        return_new=True,
    )
    return _to_event(meta["new"])


def leave_event(event_id: str, user_id: str) -> Optional[list[str]]:
    """Remove the user from an event. Returns the remaining members, or None.

    The owner cannot leave their own event — they delete it instead, which
    avoids an event with an owner who is not a member.
    """
    collection = get_db().collection(EVENTS)
    existing = collection.get(event_id)
    if not existing:
        return None

    members = list(existing.get("member_ids", []))
    if user_id not in members or existing.get("owner_id") == user_id:
        return None

    members.remove(user_id)
    collection.update({"_key": event_id, "member_ids": members,
                       "updated_at": utcnow_iso()})
    return members
