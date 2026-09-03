"""WebSocket fan-out, addressed per user.

One process, one in-memory map of user id -> that user's open sockets. That is
enough for the POC; if the API is ever scaled to several workers this needs a
shared broker (Redis pub/sub, or Arango change streams) so every worker sees
every write.

Nothing is broadcast to everyone any more. Recipes are private, so a recipe
event goes only to its owner; an event goes to each of its members. A user
with the app open on a phone and a laptop has two sockets under the same id,
and both receive the same messages — that is what keeps the two devices in
sync.
"""

import asyncio
import logging

from fastapi import WebSocket

from .models import WSEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("WS client connected for %s (%s total)", user_id, self.count)

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if sockets:
                sockets.discard(websocket)
                # Drop the empty set, otherwise the map grows once per user
                # who has ever connected and never shrinks.
                if not sockets:
                    del self._connections[user_id]
        logger.info("WS client disconnected for %s (%s left)", user_id, self.count)

    async def send_to_users(self, user_ids: list[str], event: WSEvent) -> None:
        """Deliver one event to every socket belonging to any of these users."""
        message = event.model_dump(mode="json", exclude_none=True)

        async with self._lock:
            targets: list[tuple[str, WebSocket]] = [
                (user_id, socket)
                for user_id in set(user_ids)
                for socket in self._connections.get(user_id, ())
            ]

        dead: list[tuple[str, WebSocket]] = []
        for user_id, connection in targets:
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not break the loop
                dead.append((user_id, connection))

        if dead:
            async with self._lock:
                for user_id, connection in dead:
                    sockets = self._connections.get(user_id)
                    if not sockets:
                        continue
                    sockets.discard(connection)
                    if not sockets:
                        del self._connections[user_id]

    async def send_to_user(self, user_id: str, event: WSEvent) -> None:
        await self.send_to_users([user_id], event)

    @property
    def count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())

    @property
    def user_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
