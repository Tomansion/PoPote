"""Group events, the invite link that lets someone join one, and the plan.

Invites are share codes rather than email invitations: an event carries an
opaque `invite_code`, the app turns it into a link, and anyone who opens the
link and is signed in can join. That keeps the whole feature free of an SMTP
provider and of any way to look another user up by address.

The plan hangs off the event and is edited by every member, not just the
owner — the point of planning a weekend together is that everyone can say
what they are cooking on Saturday night. Every write is broadcast to all
members, so four phones round a kitchen table stay in step.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Path, status

from .. import db
from ..auth import CurrentUser
from ..models import (
    SLOTS,
    Event,
    EventCreate,
    EventPlan,
    EventPreview,
    EventUpdate,
    MealSlot,
    PlanMove,
    Recipe,
    SlotName,
    WSEvent,
)
from ..ws import manager

logger = logging.getLogger(__name__)

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="Événement introuvable")

# Days are addressed in the URL, so the shape is checked before anything
# reaches the database — a plan keyed by "../etc" is not a thing worth having.
DayParam = Path(pattern=r"^\d{4}-\d{2}-\d{2}$")


async def _member_event(event_id: str, user_id: str) -> Event:
    """The event, or 404 — the membership check every plan endpoint starts with."""
    event = await asyncio.to_thread(db.get_event, event_id, user_id)
    if event is None:
        raise NOT_FOUND
    return event


async def _broadcast_plan(event: Event, plan: EventPlan) -> None:
    await manager.send_to_users(
        event.member_ids, WSEvent(type="plan.updated", event_id=event.id, plan=plan)
    )


@router.get("/events", response_model=list[Event])
async def list_events(user: CurrentUser) -> list[Event]:
    return await asyncio.to_thread(db.list_events, user.id)


@router.get("/events/{event_id}", response_model=Event)
async def get_event(event_id: str, user: CurrentUser) -> Event:
    event = await asyncio.to_thread(db.get_event, event_id, user.id)
    if event is None:
        raise NOT_FOUND
    return event


@router.post("/events", response_model=Event, status_code=201)
async def create_event(payload: EventCreate, user: CurrentUser) -> Event:
    event = await asyncio.to_thread(db.create_event, payload, user.id)
    await manager.send_to_users(event.member_ids, WSEvent(type="event.created", event=event))
    return event


@router.put("/events/{event_id}", response_model=Event)
async def update_event(event_id: str, payload: EventUpdate, user: CurrentUser) -> Event:
    event = await asyncio.to_thread(db.update_event, event_id, payload, user.id)
    if event is None:
        raise NOT_FOUND
    await manager.send_to_users(event.member_ids, WSEvent(type="event.updated", event=event))
    return event


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: str, user: CurrentUser) -> None:
    members = await asyncio.to_thread(db.delete_event, event_id, user.id)
    if members is None:
        raise NOT_FOUND
    # Sent after the delete, to everyone who had it — including the members who
    # are about to lose it from their list.
    await manager.send_to_users(members, WSEvent(type="event.deleted", event_id=event_id))


@router.get("/invites/{invite_code}", response_model=EventPreview)
async def preview_invite(invite_code: str, user: CurrentUser) -> EventPreview:
    """What the invite link shows before you accept it.

    Returns only the handful of fields worth showing on the join screen — never
    the member list — since anyone holding the code can call this.
    """
    event = await asyncio.to_thread(db.get_event_by_code, invite_code)
    if event is None:
        raise HTTPException(status_code=404, detail="Cette invitation n'existe plus")

    owner = next((m for m in event.members if m.id == event.owner_id), None)
    return EventPreview(
        id=event.id,
        name=event.name,
        starts_on=event.starts_on,
        ends_on=event.ends_on,
        owner_name=owner.display_name if owner else "quelqu'un",
        member_count=len(event.member_ids),
        already_member=user.id in event.member_ids,
    )


@router.post("/invites/{invite_code}/join", response_model=Event)
async def join_by_invite(invite_code: str, user: CurrentUser) -> Event:
    """Join an event from its code. Safe to call twice — joining is idempotent."""
    event = await asyncio.to_thread(db.join_event, invite_code, user.id)
    if event is None:
        raise HTTPException(status_code=404, detail="Cette invitation n'existe plus")
    # Existing members see the new arrival appear live; the joiner gets the
    # event itself in the same message.
    await manager.send_to_users(event.member_ids, WSEvent(type="event.updated", event=event))
    return event


@router.post("/events/{event_id}/leave", status_code=204)
async def leave_event(event_id: str, user: CurrentUser) -> None:
    remaining = await asyncio.to_thread(db.leave_event, event_id, user.id)
    if remaining is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de quitter cet événement (en êtes-vous l'organisateur ?)",
        )

    event = await asyncio.to_thread(db.get_event_raw, event_id)
    if event is not None:
        await manager.send_to_users(remaining, WSEvent(type="event.updated", event=event))
    # The leaver drops it from their own list.
    await manager.send_to_user(user.id, WSEvent(type="event.deleted", event_id=event_id))


# ------------------------------------------------------------------- plan


@router.get("/events/{event_id}/recipes", response_model=list[Recipe])
async def list_event_recipes(event_id: str, user: CurrentUser) -> list[Recipe]:
    """Every member's recipes, for the planner's picker.

    One call rather than one per member: the picker shows your own book in one
    tab and everyone else's in another, and its search runs across both. Each
    recipe carries its `owner_id`, which the client matches against the event's
    member list to label it.
    """
    event = await _member_event(event_id, user.id)
    return await asyncio.to_thread(db.list_recipes_of_users, event.member_ids)


@router.get("/events/{event_id}/plan", response_model=EventPlan)
async def get_plan(event_id: str, user: CurrentUser) -> EventPlan:
    await _member_event(event_id, user.id)
    return await asyncio.to_thread(db.get_plan, event_id)


@router.put("/events/{event_id}/plan/{day}/{slot}", response_model=EventPlan)
async def set_plan_slot(
    payload: MealSlot,
    user: CurrentUser,
    event_id: str,
    slot: SlotName,
    day: str = DayParam,
) -> EventPlan:
    """Replace one part of one day. Any member may write; the whole plan comes
    back, which is also what every other member receives over the socket."""
    event = await _member_event(event_id, user.id)

    day_value = str(day)
    if not (str(event.starts_on) <= day_value <= str(event.ends_on)):
        raise HTTPException(
            status_code=422, detail="Ce jour est en dehors de l'événement"
        )

    plan = await asyncio.to_thread(db.set_slot, event_id, day_value, slot, payload)
    await _broadcast_plan(event, plan)
    return plan


@router.post("/events/{event_id}/plan/move", response_model=EventPlan)
async def move_plan_meals(
    event_id: str, payload: PlanMove, user: CurrentUser
) -> EventPlan:
    """Drag & drop, including a multi-selection dragged in one gesture."""
    event = await _member_event(event_id, user.id)

    if not (str(event.starts_on) <= payload.to_day <= str(event.ends_on)):
        raise HTTPException(
            status_code=422, detail="Ce jour est en dehors de l'événement"
        )

    plan = await asyncio.to_thread(db.move_meals, event_id, payload)
    await _broadcast_plan(event, plan)
    return plan
