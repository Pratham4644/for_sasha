from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.db import db
from backend.app.middleware.error_handler import register_error_handlers
from backend.app.middleware.request_id import RequestIdMiddleware
from backend.app.routes import api_router, api_v1_router, health_router, websocket_router
from backend.app.services.ai_pipeline import ai_pipeline_manager
from backend.app.services.edge_status import remote_edge_status_loop
from backend.app.services.ingestion import start_camera_ingestion, uses_local_stream_manager
from backend.app.services.retention import retention_cleanup_loop
from backend.app.services.stream_manager import StreamState, stream_manager

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
# PyMongo topology/heartbeat spam is unhelpful at DEBUG — keep app logs readable.
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("pymongo.topology").setLevel(logging.WARNING)
LOGGER = logging.getLogger("camera.platform.main")


def _make_status_callback(loop: asyncio.AbstractEventLoop):
    """
    Creates a stream_manager status callback that updates MongoDB camera status.
    This is the ONLY place that transitions a camera to ONLINE — after the
    lifecycle thread has verified the MediaMTX publisher is active.
    """
    from backend.app.models import CameraStatus

    STATE_TO_DB: dict[StreamState, str] = {
        StreamState.STOPPED: CameraStatus.OFFLINE.value,
        StreamState.CONNECTING: CameraStatus.CONNECTING.value,
        StreamState.ONLINE: CameraStatus.ONLINE.value,
        StreamState.RECONNECTING: CameraStatus.CONNECTING.value,
        StreamState.ERROR: CameraStatus.ERROR.value,
    }

    def _callback(camera_id: str, state: StreamState, error: str | None) -> None:
        new_status = STATE_TO_DB.get(state)
        if not new_status or not db.is_connected:
            return
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _update_db(camera_id, new_status, error),
                loop,
            )

    async def _update_db(camera_id: str, status_value: str, error: str | None) -> None:
        try:
            update: dict = {"status": status_value}
            if error:
                update["last_error"] = error
            await db.cameras.update_one({"id": camera_id}, {"$set": update})
            LOGGER.debug("Camera %s status updated to %s in MongoDB", camera_id, status_value)
        except Exception as exc:
            LOGGER.debug("Failed to update camera %s status: %s", camera_id, exc)

    return _callback


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup
    LOGGER.info("Starting %s (Environment: %s)", settings.app_name, settings.app_env)

    # Register stream status → MongoDB callback before cameras are started
    main_loop = asyncio.get_running_loop()
    stream_manager.register_status_callback(_make_status_callback(main_loop))
    ai_pipeline_manager.set_event_loop(main_loop)

    db_ok = await db.connect()
    if db_ok:
        try:
            await db.ensure_indexes()
        except Exception as exc:
            LOGGER.error("Failed to ensure database indexes on startup: %s", exc)

        # Auto-start active cameras on backend startup
        try:
            from backend.app.models import Camera, CameraStatus
            cursor = db.cameras.find({"enabled": True, "stream_paused": {"$ne": True}})
            async for doc in cursor:
                try:
                    cam = Camera(**doc)
                    started, message = await start_camera_ingestion(cam)
                    await db.cameras.update_one(
                        {"id": cam.id},
                        {"$set": {"status": CameraStatus.CONNECTING.value}},
                    )
                    mode_label = "remote-edge" if not uses_local_stream_manager(cam) else "local"
                    LOGGER.info(
                        "Auto-started %s ingestion for camera '%s' (%s): %s",
                        mode_label,
                        cam.name,
                        cam.id,
                        message if not started else "started",
                    )
                except Exception as cam_err:
                    LOGGER.error("Error auto-starting camera %s: %s", doc.get("name"), cam_err)
        except Exception as exc:
            LOGGER.error("Error checking active cameras on startup: %s", exc)
    else:
        LOGGER.warning("MongoDB not connected on startup. Database queries will fail closed.")

    # Launch retention and remote-edge status background workers
    retention_task = asyncio.create_task(retention_cleanup_loop())
    edge_status_task = asyncio.create_task(remote_edge_status_loop())

    yield

    # 2. Shutdown
    LOGGER.info("Shutting down %s...", settings.app_name)
    retention_task.cancel()
    edge_status_task.cancel()

    try:
        stream_manager.stop_all()
        ai_pipeline_manager.stop_all()
    except Exception as exc:
        LOGGER.error("Error stopping streaming processes: %s", exc)

    await db.close()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

# 1. Request ID Middleware
app.add_middleware(RequestIdMiddleware)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 3. Exception Handlers
register_error_handlers(app)

# 4. Route Mounting
app.include_router(health_router)
app.include_router(websocket_router)
app.include_router(api_router)
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root():
    """Root platform status endpoint."""
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "system_status": "/api/system/status",
    }
