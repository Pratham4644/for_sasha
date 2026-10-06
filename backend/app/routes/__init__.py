from __future__ import annotations

from fastapi import APIRouter

from backend.app.routes.analytics import router as analytics_router
from backend.app.routes.auth import router as auth_router
from backend.app.routes.cameras import router as cameras_router
from backend.app.routes.detections import router as detections_router
from backend.app.routes.health import router as health_router
from backend.app.routes.logs import router as logs_router
from backend.app.routes.organizations import router as organizations_router
from backend.app.routes.sites import router as sites_router
from backend.app.routes.users import router as users_router
from backend.app.routes.websocket import router as websocket_router

# Unified API router mounted under /api and /api/v1 for complete compatibility
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(cameras_router)
api_router.include_router(detections_router)
api_router.include_router(logs_router)
api_router.include_router(websocket_router)
api_router.include_router(users_router)
api_router.include_router(sites_router)
api_router.include_router(organizations_router)
api_router.include_router(health_router)
api_router.include_router(analytics_router)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(cameras_router)
api_v1_router.include_router(detections_router)
api_v1_router.include_router(logs_router)
api_v1_router.include_router(websocket_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(sites_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(analytics_router)

__all__ = ["api_router", "api_v1_router", "health_router", "websocket_router"]
