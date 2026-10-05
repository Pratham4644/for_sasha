from __future__ import annotations

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.app.websocket_manager import websocket_manager

LOGGER = logging.getLogger("camera.platform.routes.websocket")
router = APIRouter(tags=["Real-time Events"])


@router.websocket("/ws/detections")
@router.websocket("/api/ws/detections")
async def detection_websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket connection for live AI detection events.
    Frontend connects to receive detection events instantly without polling.
    """
    await websocket_manager.connect(websocket)
    try:
        # Keep connection open and handle incoming ping/messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
    except Exception as exc:
        LOGGER.debug("WebSocket client error: %s", exc)
        await websocket_manager.disconnect(websocket)


@router.get("/api/detections/stream")
@router.get("/detections/stream")
async def detection_sse_endpoint():
    """
    Server-Sent Events (SSE) fallback endpoint for environments
    where WebSockets may be blocked by proxies.
    """
    queue: asyncio.Queue = asyncio.Queue()

    # Create temporary subscriber
    async def sse_generator():
        try:
            # Yield initial connection confirmation
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                # Heartbeat every 15 seconds if no detections
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: detection\ndata: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
