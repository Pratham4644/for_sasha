from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

LOGGER = logging.getLogger("camera.platform.websocket")


class WebSocketManager:
    """Manages real-time WebSocket client connections and event broadcasting."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accepts and stores an active WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        LOGGER.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Removes a disconnected WebSocket client."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        LOGGER.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcasts a JSON message to all active WebSocket clients."""
        if not self.active_connections:
            return

        payload = json.dumps(message, default=str)
        stale: list[WebSocket] = []

        async with self._lock:
            clients = list(self.active_connections)

        for connection in clients:
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)

        if stale:
            async with self._lock:
                for dead in stale:
                    if dead in self.active_connections:
                        self.active_connections.remove(dead)


websocket_manager = WebSocketManager()
