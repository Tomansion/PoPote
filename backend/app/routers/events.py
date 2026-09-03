"""Group events, and the invite link that lets someone join one.

Invites are share codes rather than email invitations: an event carries an
opaque `invite_code`, the app turns it into a link, and anyone who opens the
link and is signed in can join. That keeps the whole feature free of an SMTP
provider and of any way to look another user up by address.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..auth import CurrentUser
from ..models import Event, EventCreate, EventPreview, EventUpdate, WSEvent
from ..ws import manager

logger = logging.getLogger(__name__)

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="Événement introuvable")


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
