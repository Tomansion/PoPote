"""The shopping list for an event: generating it, sharing it, ticking it off.

Two audiences, and that is what shapes the file. Members reach the list
through their event and are authenticated like everywhere else. Everyone else
reaches it through a share link — a code in the URL and nothing more — because
the person holding the trolley is often not the person who planned the meals,
and asking them to make an account first would defeat the whole point.

The public half is therefore deliberately unauthenticated: it can read one
list and tick its boxes, and it can do nothing else. It cannot see the event
itself, the recipes behind the list, or anyone's email — it does see the
members' names and avatars, because a line assigned to an id nobody can read
tells the shopper nothing. Saying *who* fetches what stays with the members.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import ai, db, groceries
from ..auth import CurrentUser
from ..models import (
    GroceryAssign,
    GroceryCheck,
    GroceryCheckMany,
    GroceryList,
    GroceryListSummary,
    WSEvent,
)
from ..ws import manager, rooms

logger = logging.getLogger(__name__)

router = APIRouter()

NO_LIST = HTTPException(status_code=404, detail="Liste de courses introuvable")


async def _hydrate(grocery: GroceryList) -> GroceryList:
    """Attach the event's members, so the ids on each line have faces.

    Read from the event every time rather than stored on the list: someone who
    joins after the list was generated should still show up as a possible pair
    of hands, and someone who left should stop being offered.
    """
    event = await asyncio.to_thread(db.get_event_raw, grocery.event_id)
    grocery.members = event.members if event is not None else []
    return grocery


async def _publish(grocery: GroceryList) -> None:
    """Push a changed list to both audiences at once.

    The room reaches whoever has the shared page open, signed in or not; the
    per-user feed reaches members wherever they are in the app, which is what
    keeps the "Liste de courses" index fresh without polling.
    """
    event = await asyncio.to_thread(db.get_event_raw, grocery.event_id)
    grocery.members = event.members if event is not None else []

    payload = grocery.model_dump(mode="json")
    await rooms.broadcast(
        grocery.share_code, {"type": "grocery.updated", "grocery": payload}
    )

    if event is not None:
        await manager.send_to_users(
            event.member_ids,
            WSEvent(type="grocery.updated", event_id=event.id, grocery=grocery),
        )


# ------------------------------------------------------------- members only


@router.get("/grocery-lists", response_model=list[GroceryListSummary])
async def list_grocery_lists(user: CurrentUser) -> list[GroceryListSummary]:
    """Every list from every event you belong to, most recently touched first.

    This is the "Liste de courses" section of the app: a way in to the lists
    that already exist, rather than a place to make new ones.
    """
    return await asyncio.to_thread(db.list_grocery_summaries, user.id)


@router.get("/events/{event_id}/grocery-list", response_model=GroceryList)
async def get_grocery_list(event_id: str, user: CurrentUser) -> GroceryList:
    event = await asyncio.to_thread(db.get_event, event_id, user.id)
    if event is None:
        raise NO_LIST

    grocery = await asyncio.to_thread(db.get_grocery_list, event_id)
    if grocery is None:
        raise NO_LIST
    grocery.members = event.members
    return grocery


@router.post("/events/{event_id}/grocery-list", response_model=GroceryList)
async def generate_grocery_list(event_id: str, user: CurrentUser) -> GroceryList:
    """(Re)build the list from what the plan currently says.

    Safe to run again after the plan changes: boxes already ticked survive, so
    someone halfway round the shop does not lose their place because a meal
    was added at home.
    """
    event = await asyncio.to_thread(db.get_event, event_id, user.id)
    if event is None:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    plan = await asyncio.to_thread(db.get_plan, event_id)
    recipes = await asyncio.to_thread(db.list_recipes_of_users, event.member_ids)
    by_id = {recipe.id: recipe for recipe in recipes}

    items = await asyncio.to_thread(groceries.build_items, event, plan, by_id)
    items = await _fuse(items, event_id)
    grocery = await asyncio.to_thread(db.save_grocery_list, event_id, event.name, items)

    await _publish(grocery)
    return grocery


async def _fuse(items: list, event_id: str) -> list:
    """Let the model merge what the unit table could not.

    Wrapped in the widest possible except: the list before this call is
    already correct, so nothing here is worth failing a generation over. No
    API key, a refused request, a mangled answer — all of them fall back to
    the same perfectly usable list.
    """
    if len(items) < 2 or not ai.is_enabled():
        return items

    payload = [
        {
            "key": item.key,
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        for item in items
    ]
    try:
        groups = await asyncio.to_thread(ai.fuse_ingredients, payload)
    except Exception as exc:  # noqa: BLE001 — any SDK/parsing failure, same fallback
        logger.warning("Ingredient fusion failed for %s: %s", event_id, exc)
        return items

    return groceries.apply_fusion(items, groups)


@router.post("/events/{event_id}/grocery-list/prices", response_model=GroceryList)
async def price_grocery_list(event_id: str, user: CurrentUser) -> GroceryList:
    """Ask the model what this shop is likely to cost.

    On demand rather than on generation: it is the one part of the app that
    costs money per use, and a list is perfectly usable without it. The
    estimate is stored, so reopening the page does not pay for it again.
    """
    event = await asyncio.to_thread(db.get_event, event_id, user.id)
    if event is None:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    grocery = await asyncio.to_thread(db.get_grocery_list, event_id)
    if grocery is None:
        raise NO_LIST
    if not grocery.items:
        return grocery

    payload = [
        {
            "key": item.key,
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        for item in grocery.items
    ]

    try:
        prices = await asyncio.to_thread(ai.estimate_prices, payload)
    except ai.AIDisabled as exc:
        raise HTTPException(
            status_code=503, detail="Estimation des prix non configurée sur ce serveur"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — any SDK/parsing failure, same fallback
        logger.warning("Price estimation failed for %s: %s", event_id, exc)
        raise HTTPException(
            status_code=502, detail="L'estimation a échoué, réessayez"
        ) from exc

    updated = await asyncio.to_thread(db.set_grocery_prices, event_id, prices)
    if updated is None:
        raise NO_LIST

    await _publish(updated)
    return updated


@router.post("/events/{event_id}/grocery-list/assign", response_model=GroceryList)
async def assign_grocery_items(
    event_id: str, payload: GroceryAssign, user: CurrentUser
) -> GroceryList:
    """Put people on some lines: one article, one rayon, or one recipe's worth.

    Which of the three it is has already been decided on screen — the list is
    grouped both ways there — so this only ever receives keys. Members only,
    unlike ticking: whoever holds the share link can say what is in the
    trolley, but not who has to go and get it.
    """
    event = await asyncio.to_thread(db.get_event, event_id, user.id)
    if event is None:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    known = set(event.member_ids)
    assignees = [uid for uid in dict.fromkeys(payload.assignees) if uid in known]

    grocery = await asyncio.to_thread(
        db.set_grocery_assignees, event_id, payload.keys, assignees
    )
    if grocery is None:
        raise NO_LIST

    await _publish(grocery)
    return grocery


# --------------------------------------------------------- the shared link


@router.get("/public/grocery-lists/{share_code}", response_model=GroceryList)
async def public_grocery_list(share_code: str) -> GroceryList:
    """Read one list by its code. No account needed — the link is the key.

    Carries the event's members, since without them the assignment on each
    line is a set of opaque ids. That is a real (small) widening of what a
    leaked link shows: display names and avatars, never emails.
    """
    grocery = await asyncio.to_thread(db.get_grocery_list_by_code, share_code)
    if grocery is None:
        raise NO_LIST
    return await _hydrate(grocery)


@router.patch(
    "/public/grocery-lists/{share_code}/items/{item_key}", response_model=GroceryList
)
async def check_grocery_item(
    share_code: str, item_key: str, payload: GroceryCheck
) -> GroceryList:
    """Tick or untick one line, for everyone looking at the list.

    Unauthenticated on purpose: whoever is at the shop ticks the boxes, and
    nothing else on this endpoint can be reached with the code. The worst a
    leaked link allows is someone unticking the yoghurts.
    """
    grocery = await asyncio.to_thread(
        db.set_grocery_item_checked, share_code, item_key, payload.checked
    )
    if grocery is None:
        raise NO_LIST

    await _publish(grocery)
    return grocery


@router.patch("/public/grocery-lists/{share_code}/items", response_model=GroceryList)
async def check_grocery_items(share_code: str, payload: GroceryCheckMany) -> GroceryList:
    """Tick or untick a whole heading's worth in one shot.

    A different route from the one above (no `{item_key}` segment), not an
    overload of it: the "check this whole rayon" box has to flip several
    lines atomically, and a loop calling the single-item endpoint once per
    line would race — see `db.set_grocery_items_checked`. Same no-account
    rule as everywhere else on this page.
    """
    grocery = await asyncio.to_thread(
        db.set_grocery_items_checked, share_code, payload.keys, payload.checked
    )
    if grocery is None:
        raise NO_LIST

    await _publish(grocery)
    return grocery


@router.websocket("/public/grocery-lists/{share_code}/ws")
async def public_grocery_ws(websocket: WebSocket, share_code: str) -> None:
    """Live feed for one shared list, keyed by the code rather than a token.

    The first message is the list itself, so this doubles as the initial load
    and as the resync after a dropped connection — the same shape as the
    signed-in feed's `hello`.
    """
    grocery = await asyncio.to_thread(db.get_grocery_list_by_code, share_code)
    if grocery is None:
        await websocket.close(code=1008, reason="Unknown list")
        return

    await _hydrate(grocery)
    room = grocery.share_code
    await rooms.join(websocket, room)
    try:
        await websocket.send_json(
            {"type": "grocery.updated", "grocery": grocery.model_dump(mode="json")}
        )
        while True:
            # No client-to-server protocol; this keeps the socket open and
            # detects disconnects. Any text received is treated as a ping.
            await websocket.receive_text()
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Grocery WS error: %s", exc)
    finally:
        await rooms.leave(websocket, room)
