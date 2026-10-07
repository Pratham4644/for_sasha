from __future__ import annotations

import asyncio
import logging

from backend.app.config import settings
from backend.app.db import db
from backend.app.models import Camera, IngestionMode
from backend.app.services.ingestion import effective_ingestion_mode, sync_remote_edge_status

LOGGER = logging.getLogger("camera.platform.edge_status")


async def sync_all_remote_edge_cameras() -> None:
    """Refresh MongoDB status for remote-edge cameras from MediaMTX publisher state."""
    if not db.is_connected:
        return

    cursor = db.cameras.find({"enabled": True, "stream_paused": {"$ne": True}})
    async for doc in cursor:
        camera = Camera(**doc)
        if effective_ingestion_mode(camera) != IngestionMode.REMOTE_EDGE:
            continue

        try:
            new_status = await sync_remote_edge_status(camera)
            if new_status.value != (
                camera.status.value if hasattr(camera.status, "value") else str(camera.status)
            ):
                await db.cameras.update_one(
                    {"id": camera.id},
                    {"$set": {"status": new_status.value}},
                )
        except Exception as exc:
            LOGGER.debug("Failed remote-edge status sync for %s: %s", camera.id, exc)


async def remote_edge_status_loop() -> None:
    interval = max(5, settings.remote_edge_status_interval_seconds)
    while True:
        try:
            await sync_all_remote_edge_cameras()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.error("Remote-edge status loop error: %s", exc)
        await asyncio.sleep(interval)
