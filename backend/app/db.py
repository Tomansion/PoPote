"""ArangoDB access layer.

Recipes live in a single document collection. Arango's `_key` is exposed to the
API as `id`; everything else in the document maps 1:1 to the Pydantic model.
"""

import logging
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
from .models import Recipe, RecipeCreate, RecipeUpdate, utcnow_iso

logger = logging.getLogger(__name__)

COLLECTION = "recipes"

_db: Optional[StandardDatabase] = None


def _ensure_database(client: ArangoClient) -> StandardDatabase:
    """Open the target database, creating it only if we are allowed to.

    A scoped user (one granted rights on `everymeal` alone) cannot read
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

            if not db.has_collection(COLLECTION):
                db.create_collection(COLLECTION)

            collection = db.collection(COLLECTION)
            collection.add_persistent_index(fields=["name"], unique=False)
            collection.add_persistent_index(fields=["updated_at"], unique=False)

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


def list_recipes() -> list[Recipe]:
    cursor = get_db().aql.execute(
        f"FOR r IN {COLLECTION} SORT LOWER(r.name) ASC RETURN r"
    )
    return [_to_recipe(doc) for doc in cursor]


def get_recipe(recipe_id: str) -> Optional[Recipe]:
    doc = get_db().collection(COLLECTION).get(recipe_id)
    return _to_recipe(doc) if doc else None


def create_recipe(data: RecipeCreate) -> Recipe:
    now = utcnow_iso()
    payload = _fill_aisles(data.model_dump())
    payload["created_at"] = now
    payload["updated_at"] = now

    meta = get_db().collection(COLLECTION).insert(payload, return_new=True)
    return _to_recipe(meta["new"])


def update_recipe(recipe_id: str, data: RecipeUpdate) -> Optional[Recipe]:
    collection = get_db().collection(COLLECTION)
    existing = collection.get(recipe_id)
    if not existing:
        return None

    payload = _fill_aisles(data.model_dump())
    payload["_key"] = recipe_id
    payload["created_at"] = existing.get("created_at", utcnow_iso())
    payload["updated_at"] = utcnow_iso()

    meta = collection.replace(payload, return_new=True)
    return _to_recipe(meta["new"])


def delete_recipe(recipe_id: str) -> bool:
    return bool(get_db().collection(COLLECTION).delete(recipe_id, ignore_missing=True))


def count_recipes() -> int:
    return get_db().collection(COLLECTION).count()


def seed_if_empty(recipes: list[RecipeCreate]) -> int:
    """Insert demo recipes only when the collection is empty. Returns count."""
    if count_recipes() > 0:
        return 0

    inserted = 0
    for recipe in recipes:
        try:
            create_recipe(recipe)
            inserted += 1
        except DocumentInsertError as exc:
            logger.warning("Could not seed recipe %r: %s", recipe.name, exc)
    logger.info("Seeded %s demo recipes", inserted)
    return inserted
