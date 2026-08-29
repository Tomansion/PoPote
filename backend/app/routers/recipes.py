import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import db
from ..aisles import AISLES, detect_aisle
from ..models import Recipe, RecipeCreate, RecipeUpdate, WSEvent
from ..ws import manager

logger = logging.getLogger(__name__)

router = APIRouter()


# python-arango is synchronous, so every database call goes through a worker
# thread to keep the event loop (and therefore the WebSocket fan-out) free.


@router.get("/recipes", response_model=list[Recipe])
async def list_recipes() -> list[Recipe]:
    return await asyncio.to_thread(db.list_recipes)


@router.get("/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str) -> Recipe:
    recipe = await asyncio.to_thread(db.get_recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/recipes", response_model=Recipe, status_code=201)
async def create_recipe(payload: RecipeCreate) -> Recipe:
    recipe = await asyncio.to_thread(db.create_recipe, payload)
    await manager.broadcast(WSEvent(type="recipe.created", recipe=recipe))
    return recipe


@router.put("/recipes/{recipe_id}", response_model=Recipe)
async def update_recipe(recipe_id: str, payload: RecipeUpdate) -> Recipe:
    recipe = await asyncio.to_thread(db.update_recipe, recipe_id, payload)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await manager.broadcast(WSEvent(type="recipe.updated", recipe=recipe))
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: str) -> None:
    deleted = await asyncio.to_thread(db.delete_recipe, recipe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await manager.broadcast(WSEvent(type="recipe.deleted", recipe_id=recipe_id))


@router.get("/aisles")
async def list_aisles() -> dict[str, list[str]]:
    """The aisle vocabulary, so the frontend override dropdown stays in sync."""
    return {"aisles": AISLES}


@router.get("/aisles/detect")
async def detect(name: str) -> dict[str, str]:
    """Live 'rayon détecté' hint while typing an ingredient."""
    return {"name": name, "aisle": detect_aisle(name)}


@router.websocket("/ws")
async def recipes_ws(websocket: WebSocket) -> None:
    """Live recipe feed.

    On connect the client receives a `hello` event carrying the full current
    list, which doubles as the initial load and as a resync after a dropped
    connection. Afterwards it receives one event per change.
    """
    await manager.connect(websocket)
    try:
        recipes = await asyncio.to_thread(db.list_recipes)
        await websocket.send_json(
            WSEvent(type="hello", recipes=recipes).model_dump(
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
        await manager.disconnect(websocket)
