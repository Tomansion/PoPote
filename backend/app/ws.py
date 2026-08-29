"""WebSocket fan-out.

One process, one in-memory set of connections. That is enough for the POC; if
the API is ever scaled to several workers this needs a shared broker (Redis
pub/sub, or Arango change streams) so every worker sees every write.
"""

import asyncio
import logging

from fastapi import WebSocket

from .models import WSEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("WS client connected (%s total)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("WS client disconnected (%s left)", len(self._connections))

    async def broadcast(self, event: WSEvent) -> None:
        message = event.model_dump(mode="json", exclude_none=True)

        async with self._lock:
            targets = list(self._connections)

        dead: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not break the loop
                dead.append(connection)

        if dead:
            async with self._lock:
                for connection in dead:
                    self._connections.discard(connection)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
