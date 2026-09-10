"""ArangoDB access layer.

Six document collections: `recipes`, `users`, `events`, `plans`,
`grocery_lists`, and `app_settings` (a single row holding the generated
token-signing key). Arango's `_key` is exposed to the API as `id`; everything
else maps 1:1 to the Pydantic model. A plan and a grocery list are both keyed
by their event id, so each event has at most one of each and neither needs a
lookup index.

Every recipe belongs to exactly one user. Writing is the owner's alone;
*reading* extends to whoever shares an event with them, which is what makes
member pages and the planner's recipe picker possible. Both checks live here
rather than in the routers, so there is one place where "can this user touch
this document" is decided and no endpoint can forget to ask.
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
    SLOTS,
    Event,
    EventCreate,
    EventPlan,
    EventUpdate,
    GroceryItem,
    GroceryList,
    GroceryListSummary,
    MealSlot,
    PlanMove,
    ProfilePrefs,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    UserProfile,
    UserPublic,
    utcnow_iso,
)

logger = logging.getLogger(__name__)

COLLECTION = "recipes"
USERS = "users"
EVENTS = "events"
PLANS = "plans"
GROCERY = "grocery_lists"
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

            for name in (COLLECTION, USERS, EVENTS, PLANS, GROCERY, APP_SETTINGS):
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

            # The share code is how the public grocery page finds its list,
            # with no session to scope the lookup — so it has to be unique.
            db.collection(GROCERY).add_persistent_index(
                fields=["share_code"], unique=True
            )

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


def shares_event_with(user_id: str, other_id: str) -> bool:
    """True when both users belong to at least one event together.

    This is the whole of the read-sharing rule. Events are the only place two
    accounts ever meet — there is no directory and no friend list — so "we are
    planning something together" is exactly the moment recipes need to become
    readable across accounts.
    """
    if user_id == other_id:
        return True
    cursor = get_db().aql.execute(
        f"FOR e IN {EVENTS} FILTER @a IN e.member_ids AND @b IN e.member_ids "
        "LIMIT 1 RETURN 1",
        bind_vars={"a": user_id, "b": other_id},
    )
    return bool(list(cursor))


def get_recipe_for_viewer(recipe_id: str, viewer_id: str) -> Optional[Recipe]:
    """Fetch a recipe the viewer is allowed to *read* — theirs, or a
    co-member's. Still 404 for anything else, so a guessed id stays unconfirmed."""
    doc = get_db().collection(COLLECTION).get(recipe_id)
    if not doc:
        return None
    owner_id = doc.get("owner_id", "")
    if not owner_id or not shares_event_with(viewer_id, owner_id):
        return None
    return _to_recipe(doc)


def list_recipes_for_viewer(owner_id: str, viewer_id: str) -> Optional[list[Recipe]]:
    """Someone else's recipe list, for their member page. None if not allowed."""
    if not shares_event_with(viewer_id, owner_id):
        return None
    return list_recipes(owner_id)


def list_recipes_of_users(owner_ids: list[str]) -> list[Recipe]:
    """Every recipe owned by any of these users, in one query.

    Backs the planner's picker, which shows the whole event's cooking in one
    screen. Callers pass a member list they have already checked, so there is
    no per-recipe permission test to repeat here.
    """
    if not owner_ids:
        return []
    cursor = get_db().aql.execute(
        f"FOR r IN {COLLECTION} FILTER r.owner_id IN @owners "
        "SORT LOWER(r.name) ASC RETURN r",
        bind_vars={"owners": owner_ids},
    )
    return [_to_recipe(doc) for doc in cursor]


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
    # `replace()` overwrites the whole document, so the photo — which the
    # edit form never sends, because it is uploaded through its own endpoint
    # — has to be carried over by hand or every save would drop it.
    payload["image_url"] = existing.get("image_url", "")
    payload["image_thumb_url"] = existing.get("image_thumb_url", "")

    meta = collection.replace(payload, return_new=True)
    return _to_recipe(meta["new"])


def set_recipe_image(
    recipe_id: str, owner_id: str, image_url: str, thumb_url: str
) -> Optional[tuple[Recipe, list[str]]]:
    """Attach (or clear) a photo, and report which objects it replaced.

    The old URLs come back so the caller can delete them from the bucket:
    re-cropping the same dish five times should not leave five photos behind.
    Passing two empty strings clears the picture.
    """
    collection = get_db().collection(COLLECTION)
    existing = collection.get(recipe_id)
    if not existing or existing.get("owner_id") != owner_id:
        return None

    replaced = [
        url
        for url in (existing.get("image_url", ""), existing.get("image_thumb_url", ""))
        if url and url not in (image_url, thumb_url)
    ]

    collection.update(
        {
            "_key": recipe_id,
            "image_url": image_url,
            "image_thumb_url": thumb_url,
            "updated_at": utcnow_iso(),
        }
    )
    return _to_recipe(collection.get(recipe_id)), replaced


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
    """The lean shape, for event member lists."""
    return UserPublic(
        id=doc["_key"],
        display_name=doc.get("display_name", ""),
        avatar_seed=doc.get("avatar_seed", 0),
        created_at=doc.get("created_at", ""),
    )


def _to_profile(doc: dict[str, Any]) -> UserProfile:
    """The same user, plus the ten answers. For yourself and for member pages.

    `prefs` is defaulted rather than required: accounts created before the
    questions existed have no such field, and an account that never answered
    any of them is indistinguishable from one that has — both are ten empty
    strings, and empty answers are simply not displayed.
    """
    return UserProfile(
        **_to_user(doc).model_dump(),
        prefs=ProfilePrefs(**(doc.get("prefs") or {})),
    )


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_user(user_id: str) -> Optional[UserProfile]:
    doc = get_db().collection(USERS).get(user_id)
    return _to_profile(doc) if doc else None


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
) -> UserProfile:
    payload = {
        "email": normalise_email(email),
        "password_hash": password_hash,
        "display_name": display_name,
        "avatar_seed": avatar_seed,
        "created_at": utcnow_iso(),
    }
    meta = get_db().collection(USERS).insert(payload, return_new=True)
    return _to_profile(meta["new"])


def update_user_profile(
    user_id: str,
    display_name: Optional[str],
    avatar_seed: Optional[int],
    prefs: Optional[ProfilePrefs] = None,
) -> Optional[UserProfile]:
    patch: dict[str, Any] = {"_key": user_id}
    if display_name is not None:
        patch["display_name"] = display_name
    if avatar_seed is not None:
        patch["avatar_seed"] = avatar_seed
    if prefs is not None:
        # The form always submits all ten answers, so this replaces the set
        # rather than merging — which is what lets an answer be cleared.
        patch["prefs"] = prefs.model_dump()

    if len(patch) == 1:
        return get_user(user_id)

    collection = get_db().collection(USERS)
    if not collection.has(user_id):
        return None
    meta = collection.update(
        patch, return_new=True, keep_none=False, merge=False
    )
    return _to_profile(meta["new"])


# ----------------------------------------------------------------- events


def _to_event(doc: dict[str, Any], hydrate: bool = True) -> Event:
    member_ids = doc.get("member_ids", [])
    return Event(
        id=doc["_key"],
        name=doc.get("name", ""),
        starts_on=doc["starts_on"],
        ends_on=doc["ends_on"],
        # Defaulted: events created before the planner existed carry no
        # headcount, and four is the same default a new event gets.
        default_people=doc.get("default_people", 4),
        owner_id=doc.get("owner_id", ""),
        invite_code=doc.get("invite_code", ""),
        member_ids=member_ids,
        members=get_users(member_ids) if hydrate else [],
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def _unique_code(collection_name: str, field: str) -> str:
    """A free share code for `collection_name`.`field`.

    Both kinds of link — the invite and the grocery list — are opaque codes
    people retype off a phone screen, so they share an alphabet and a length.
    They are drawn from separate namespaces on purpose: handing someone the
    shopping list must not also hand them a way into the event.
    """
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        cursor = get_db().aql.execute(
            f"FOR d IN {collection_name} FILTER d.@field == @code LIMIT 1 RETURN 1",
            bind_vars={"field": field, "code": code},
        )
        if not list(cursor):
            return code
    raise RuntimeError(f"Could not allocate a free code for {collection_name}")


def _unique_invite_code() -> str:
    return _unique_code(EVENTS, "invite_code")


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
    # Both hang off the event and are keyed by its id, so there is nothing
    # left to reach them with once it is gone.
    get_db().collection(PLANS).delete(event_id, ignore_missing=True)
    get_db().collection(GROCERY).delete(event_id, ignore_missing=True)
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


# ------------------------------------------------------------------ plans


def _to_plan(doc: dict[str, Any]) -> EventPlan:
    days = {
        day: {slot: MealSlot(**value) for slot, value in slots.items() if slot in SLOTS}
        for day, slots in (doc.get("days") or {}).items()
    }
    return EventPlan(
        event_id=doc["_key"],
        days=days,
        updated_at=doc.get("updated_at", ""),
    )


def get_plan(event_id: str) -> EventPlan:
    """The event's plan, or an empty one. Never None: an event with nothing
    planned yet and an event whose plan was emptied out look the same."""
    doc = get_db().collection(PLANS).get(event_id)
    return _to_plan(doc) if doc else EventPlan(event_id=event_id)


def set_slot(event_id: str, day: str, slot: str, meal: MealSlot) -> EventPlan:
    """Write one part of one day, leaving every other slot untouched.

    Done as a single AQL statement that recomputes `days` from `OLD`, rather
    than as a merge: a merge would keep an override the user has just cleared
    (`people` back to null), and replacing the whole document would drop
    whatever someone else changed in another slot while this dialog was open.
    """
    now = utcnow_iso()
    value = meal.model_dump(mode="json")
    empty = meal.is_empty

    # An untouched slot is removed rather than stored as a row of defaults, so
    # "nothing decided" and "decided to skip" stay distinguishable.
    day_expression = (
        "UNSET(OLD.days[@day] || {}, @slot)"
        if empty
        else "MERGE(OLD.days[@day] || {}, { [@slot]: @value })"
    )

    cursor = get_db().aql.execute(
        f"""
        UPSERT {{ _key: @key }}
        INSERT {{ _key: @key, event_id: @key,
                  days: @insert_days, updated_at: @now }}
        UPDATE {{ days: MERGE(OLD.days || {{}}, {{ [@day]: {day_expression} }}),
                  updated_at: @now }}
        IN {PLANS} OPTIONS {{ mergeObjects: false }}
        RETURN NEW
        """,
        bind_vars={
            "key": event_id,
            "day": day,
            "slot": slot,
            "value": value,
            "insert_days": {} if empty else {day: {slot: value}},
            "now": now,
        },
    )
    return _to_plan(list(cursor)[0])


def move_meals(event_id: str, move: PlanMove) -> EventPlan:
    """Drag & drop: pull the named meals out of wherever they are and append
    them to one target slot, in the order they were given.

    Read-modify-write of the whole plan, unlike `set_slot`: a move touches two
    slots at once and has to be all-or-nothing between them. Two people
    dragging different meals in the same second is a race the last one wins —
    acceptable for a shared shopping weekend, and cheaper than a transaction.
    """
    plan = get_plan(event_id)
    days = {day: dict(slots) for day, slots in plan.days.items()}

    moved = []
    for item in move.items:
        source = days.get(item.day, {}).get(item.slot)
        if source is None:
            continue
        found = next((r for r in source.recipes if r.uid == item.uid), None)
        if found is None:
            continue
        source.recipes = [r for r in source.recipes if r.uid != item.uid]
        moved.append(found)

    if not moved:
        return plan

    target = days.setdefault(move.to_day, {}).get(move.to_slot) or MealSlot()
    # Dropping something into a slot marked "rien à cuisiner" is a change of
    # mind, not a contradiction: the meal wins and the flag clears.
    target.skipped = False
    target.recipes = target.recipes + moved
    days.setdefault(move.to_day, {})[move.to_slot] = target

    payload_days = {
        day: {
            slot: meal.model_dump(mode="json")
            for slot, meal in slots.items()
            if not meal.is_empty
        }
        for day, slots in days.items()
    }
    now = utcnow_iso()
    cursor = get_db().aql.execute(
        f"""
        UPSERT {{ _key: @key }}
        INSERT {{ _key: @key, event_id: @key, days: @days, updated_at: @now }}
        UPDATE {{ days: @days, updated_at: @now }}
        IN {PLANS} OPTIONS {{ mergeObjects: false }}
        RETURN NEW
        """,
        bind_vars={"key": event_id, "days": payload_days, "now": now},
    )
    return _to_plan(list(cursor)[0])


# ---------------------------------------------------------- grocery lists


def _to_grocery(doc: dict[str, Any]) -> GroceryList:
    return GroceryList(
        event_id=doc["_key"],
        event_name=doc.get("event_name", ""),
        share_code=doc.get("share_code", ""),
        items=[GroceryItem(**item) for item in doc.get("items", [])],
        total_price=doc.get("total_price"),
        priced_at=doc.get("priced_at", ""),
        generated_at=doc.get("generated_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def get_grocery_list(event_id: str) -> Optional[GroceryList]:
    doc = get_db().collection(GROCERY).get(event_id)
    return _to_grocery(doc) if doc else None


def get_grocery_list_by_code(share_code: str) -> Optional[GroceryList]:
    """Look a list up by its share code, with no membership check.

    This is what backs the public page, so it must work with no session at
    all. The code is the only credential, which is the trade the share link
    makes on purpose.
    """
    cursor = get_db().aql.execute(
        f"FOR g IN {GROCERY} FILTER g.share_code == @code LIMIT 1 RETURN g",
        bind_vars={"code": share_code.strip().upper()},
    )
    docs = list(cursor)
    return _to_grocery(docs[0]) if docs else None


def save_grocery_list(
    event_id: str, event_name: str, items: list[GroceryItem]
) -> GroceryList:
    """Store a freshly computed list, keeping what the shoppers already did.

    Regenerating after a plan change must not untick the ten things already in
    the trolley, so `checked` is carried over by item key. A price is only
    carried over when the quantity has not moved — the same line for twice as
    many people does not cost the same.
    """
    collection = get_db().collection(GROCERY)
    existing = collection.get(event_id)
    now = utcnow_iso()

    previous = {}
    if existing:
        previous = {item["key"]: item for item in existing.get("items", [])}

    for item in items:
        before = previous.get(item.key)
        if not before:
            continue
        item.checked = bool(before.get("checked"))
        if before.get("quantity") == item.quantity and before.get("unit") == item.unit:
            item.price = before.get("price")

    priced = [item.price for item in items if item.price is not None]
    payload = {
        "_key": event_id,
        "event_id": event_id,
        "event_name": event_name,
        "share_code": (
            existing.get("share_code") if existing else _unique_code(GROCERY, "share_code")
        ),
        "items": [item.model_dump(mode="json") for item in items],
        "total_price": round(sum(priced), 2) if priced else None,
        "priced_at": existing.get("priced_at", "") if existing else "",
        "generated_at": now,
        "updated_at": now,
    }

    if existing:
        collection.replace(payload)
    else:
        collection.insert(payload)
    return _to_grocery(collection.get(event_id))


def set_grocery_item_checked(
    share_code: str, item_key: str, checked: bool
) -> Optional[GroceryList]:
    """Tick or untick one line, addressed by share code rather than event id.

    The public page has no session to scope a lookup by event, and everyone
    holding the link — signed in or not — ticks the same boxes.
    """
    existing = get_grocery_list_by_code(share_code)
    if existing is None:
        return None

    items = [item.model_dump(mode="json") for item in existing.items]
    if not any(item["key"] == item_key for item in items):
        return None
    for item in items:
        if item["key"] == item_key:
            item["checked"] = checked

    collection = get_db().collection(GROCERY)
    collection.update(
        {"_key": existing.event_id, "items": items, "updated_at": utcnow_iso()},
        merge=False,
    )
    return _to_grocery(collection.get(existing.event_id))


def set_grocery_prices(event_id: str, prices: dict[str, float]) -> Optional[GroceryList]:
    """Attach an estimate to every line the model priced, and total them up."""
    collection = get_db().collection(GROCERY)
    existing = collection.get(event_id)
    if not existing:
        return None

    items = list(existing.get("items", []))
    for item in items:
        if item["key"] in prices:
            item["price"] = prices[item["key"]]

    priced = [item["price"] for item in items if item.get("price") is not None]
    now = utcnow_iso()
    collection.update(
        {
            "_key": event_id,
            "items": items,
            "total_price": round(sum(priced), 2) if priced else None,
            "priced_at": now,
            "updated_at": now,
        },
        merge=False,
    )
    return _to_grocery(collection.get(event_id))


def list_grocery_summaries(user_id: str) -> list[GroceryListSummary]:
    """One row per event the user belongs to that has a list, freshest first."""
    cursor = get_db().aql.execute(
        f"""
        FOR e IN {EVENTS}
          FILTER @uid IN e.member_ids
          LET g = DOCUMENT({GROCERY}, e._key)
          FILTER g != null
          SORT g.updated_at DESC
          RETURN {{ event: e, list: g }}
        """,
        bind_vars={"uid": user_id},
    )

    summaries = []
    for row in cursor:
        event, grocery = row["event"], row["list"]
        items = grocery.get("items", [])
        summaries.append(
            GroceryListSummary(
                event_id=event["_key"],
                event_name=event.get("name", ""),
                share_code=grocery.get("share_code", ""),
                item_count=len(items),
                checked_count=sum(1 for item in items if item.get("checked")),
                total_price=grocery.get("total_price"),
                starts_on=event.get("starts_on"),
                ends_on=event.get("ends_on"),
                updated_at=grocery.get("updated_at", ""),
            )
        )
    return summaries
