from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from backend.app.config import settings
from backend.app.db import db
from backend.app.models import utc_now

LOGGER = logging.getLogger("camera.platform.retention")


async def cleanup_expired_detections() -> int:
    """Deletes detection events older than DETECTION_RETENTION_DAYS."""
    if not db.is_connected:
        return 0

    retention_days = settings.detection_retention_days
    cutoff = utc_now() - timedelta(days=retention_days)

    try:
        result = await db.detection_events.delete_many({
            "$or": [
                {"timestamp": {"$lt": cutoff}},
                {"expires_at": {"$lt": utc_now()}},
            ]
        })
        count = result.deleted_count
        if count > 0:
            LOGGER.info("Retention cleanup: deleted %d expired detection events (older than %s).", count, cutoff.isoformat())
        return count
    except Exception as exc:
        LOGGER.error("Error during retention cleanup: %s", exc)
        return 0


async def retention_cleanup_loop() -> None:
    """Periodic background task that runs retention cleanup at configured intervals."""
    interval_seconds = max(3600, settings.retention_cleanup_hours * 3600)
    LOGGER.info("Starting retention cleanup background task (interval: %d hours).", settings.retention_cleanup_hours)

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await cleanup_expired_detections()
        except asyncio.CancelledError:
            LOGGER.info("Retention cleanup task cancelled.")
            break
        except Exception as exc:
            LOGGER.error("Unexpected error in retention loop: %s", exc)
