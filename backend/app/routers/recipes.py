import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from .. import db
from ..aisles import AISLES, detect_aisle
from ..auth import CurrentUser, user_from_ws_token
from ..models import Recipe, RecipeCreate, RecipeUpdate, WSEvent
from ..ws import manager

logger = logging.getLogger(__name__)

router = APIRouter()


# python-arango is synchronous, so every database call goes through a worker
# thread to keep the event loop (and therefore the WebSocket fan-out) free.
#
# Every recipe endpoint is scoped to the caller: the user id comes from the
# token, never from the request, so there is no way to ask for someone else's
# recipes. A recipe owned by another account reads as 404 rather than 403,
# which keeps the API from confirming that a guessed id exists.


@router.get("/recipes", response_model=list[Recipe])
async def list_recipes(user: CurrentUser) -> list[Recipe]:
    return await asyncio.to_thread(db.list_recipes, user.id)


@router.get("/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str, user: CurrentUser) -> Recipe:
    recipe = await asyncio.to_thread(db.get_recipe, recipe_id, user.id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/recipes", response_model=Recipe, status_code=201)
async def create_recipe(payload: RecipeCreate, user: CurrentUser) -> Recipe:
    recipe = await asyncio.to_thread(db.create_recipe, payload, user.id)
    await manager.send_to_user(user.id, WSEvent(type="recipe.created", recipe=recipe))
    return recipe


@router.put("/recipes/{recipe_id}", response_model=Recipe)
async def update_recipe(
    recipe_id: str, payload: RecipeUpdate, user: CurrentUser
) -> Recipe:
    recipe = await asyncio.to_thread(db.update_recipe, recipe_id, payload, user.id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await manager.send_to_user(user.id, WSEvent(type="recipe.updated", recipe=recipe))
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: str, user: CurrentUser) -> None:
    deleted = await asyncio.to_thread(db.delete_recipe, recipe_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")
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
