import asyncio
import logging

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from .. import db, images, storage
from ..aisles import AISLES, detect_aisle
from ..auth import CurrentUser, user_from_ws_token
from ..models import Recipe, RecipeCreate, RecipeUpdate, WSEvent
from ..ws import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# A photo straight out of a phone is a couple of megabytes; ten is generous
# for anything anyone would deliberately upload, and small enough that a
# rejected file has not already cost the server much to receive.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

NOT_FOUND = HTTPException(status_code=404, detail="Recipe not found")


# python-arango is synchronous, so every database call goes through a worker
# thread to keep the event loop (and therefore the WebSocket fan-out) free.
#
# Writing a recipe is the owner's alone: the user id comes from the token,
# never from the request. Reading one is wider — anyone sharing an event with
# the owner may open it, which is what makes the planner's picker and member
# pages work. Anything outside both rules reads as 404 rather than 403, so the
# API never confirms that a guessed id exists.


@router.get("/recipes", response_model=list[Recipe])
async def list_recipes(user: CurrentUser) -> list[Recipe]:
    """Your own recipe book. Other people's recipes are reached through the
    event they are shared in, or through their member page."""
    return await asyncio.to_thread(db.list_recipes, user.id)


@router.get("/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str, user: CurrentUser) -> Recipe:
    recipe = await asyncio.to_thread(db.get_recipe_for_viewer, recipe_id, user.id)
    if recipe is None:
        raise NOT_FOUND
    return recipe


@router.post("/recipes", response_model=Recipe, status_code=201)
async def create_recipe(payload: RecipeCreate, user: CurrentUser) -> Recipe:
    recipe = await asyncio.to_thread(db.create_recipe, payload, user.id)
    await manager.send_to_user(user.id, WSEvent(type="recipe.created", recipe=recipe))
    return recipe


@router.post("/recipes/{recipe_id}/image", response_model=Recipe)
async def upload_recipe_image(
    recipe_id: str, user: CurrentUser, file: UploadFile = File(...)
) -> Recipe:
    """Attach a photo the user picked, resized into a full size and a thumbnail.

    Separate from the recipe itself, and owner-only: an upload is a second
    request that can fail, retry, or be skipped entirely without the recipe
    ever being at risk.
    """
    recipe = await asyncio.to_thread(db.get_recipe, recipe_id, user.id)
    if recipe is None:
        raise NOT_FOUND

    if not storage.is_configured():
        raise HTTPException(
            status_code=503, detail="Stockage d'image non configuré sur ce serveur"
        )

    # Read one byte past the limit: enough to know the file is too big without
    # pulling all of it into memory first.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image trop lourde (maximum {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo)",
        )
    if not data:
        raise HTTPException(status_code=422, detail="Fichier vide")

    try:
        full, thumb = await asyncio.to_thread(images.render, data)
    except images.UnreadableImage as exc:
        logger.info("Rejected upload for %s: %s", recipe_id, exc)
        raise HTTPException(
            status_code=415, detail="Format d'image non reconnu"
        ) from exc

    full_url = await asyncio.to_thread(
        storage.upload_image, full, images.CONTENT_TYPE, images.SUFFIX
    )
    thumb_url = await asyncio.to_thread(
        storage.upload_image, thumb, images.CONTENT_TYPE, images.SUFFIX
    )
    if not full_url or not thumb_url:
        raise HTTPException(status_code=503, detail="Stockage d'image non configuré")

    result = await asyncio.to_thread(
        db.set_recipe_image, recipe_id, user.id, full_url, thumb_url
    )
    if result is None:
        raise NOT_FOUND
    updated, replaced = result

    # The previous photo has nothing pointing at it any more.
    for url in replaced:
        await asyncio.to_thread(storage.delete_by_url, url)

    await manager.send_to_user(user.id, WSEvent(type="recipe.updated", recipe=updated))
    return updated


@router.delete("/recipes/{recipe_id}/image", response_model=Recipe)
async def delete_recipe_image(recipe_id: str, user: CurrentUser) -> Recipe:
    """Remove the photo and fall back to the generated gradient."""
    result = await asyncio.to_thread(db.set_recipe_image, recipe_id, user.id, "", "")
    if result is None:
        raise NOT_FOUND
    updated, replaced = result

    for url in replaced:
        await asyncio.to_thread(storage.delete_by_url, url)

    await manager.send_to_user(user.id, WSEvent(type="recipe.updated", recipe=updated))
    return updated


@router.put("/recipes/{recipe_id}", response_model=Recipe)
async def update_recipe(
    recipe_id: str, payload: RecipeUpdate, user: CurrentUser
) -> Recipe:
    recipe = await asyncio.to_thread(db.update_recipe, recipe_id, payload, user.id)
    if recipe is None:
        raise NOT_FOUND
    await manager.send_to_user(user.id, WSEvent(type="recipe.updated", recipe=recipe))
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: str, user: CurrentUser) -> None:
    existing = await asyncio.to_thread(db.get_recipe, recipe_id, user.id)
    if existing is None:
        raise NOT_FOUND

    deleted = await asyncio.to_thread(db.delete_recipe, recipe_id, user.id)
    if not deleted:
        raise NOT_FOUND

    for url in (existing.image_url, existing.image_thumb_url):
        if url:
            await asyncio.to_thread(storage.delete_by_url, url)

    await manager.send_to_user(
        user.id, WSEvent(type="recipe.deleted", recipe_id=recipe_id)
    )


@router.get("/aisles")
async def list_aisles() -> dict[str, list[str]]:
    """The aisle vocabulary, so the frontend override dropdown stays in sync."""
    return {"aisles": AISLES}


@router.get("/aisles/detect")
async def detect(name: str) -> dict[str, str]:
    """Live 'rayon détecté' hint while typing an ingredient."""
    return {"name": name, "aisle": detect_aisle(name)}


@router.websocket("/ws")
async def recipes_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
    """Live feed for one signed-in user.

    The token arrives as a query parameter because browsers cannot set headers
    on a WebSocket handshake; it is the same token the REST calls carry.

    On connect the client receives a `hello` event with that user's full recipe
    list and events, which doubles as the initial load and as a resync after a
    dropped connection. Afterwards it receives one event per change.
    """
    user = await asyncio.to_thread(user_from_ws_token, token)
    if user is None:
        # 1008 (policy violation) before accepting: the client reads this as
        # "log in again" rather than retrying forever behind a backoff.
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await manager.connect(websocket, user.id)
    try:
        recipes = await asyncio.to_thread(db.list_recipes, user.id)
        events = await asyncio.to_thread(db.list_events, user.id)
        await websocket.send_json(
            WSEvent(type="hello", recipes=recipes, events=events).model_dump(
                mode="json", exclude_none=True
            )
        )

        while True:
            # No client-to-server protocol yet; this keeps the socket open and
            # detects disconnects. Any text received is treated as a ping.
            await websocket.receive_text()
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("WS error: %s", exc)
    finally:
        await manager.disconnect(websocket, user.id)
