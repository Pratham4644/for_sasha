from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Response, status

from backend.app.config import settings
from backend.app.db import db
from backend.app.services.ai_pipeline import ai_pipeline_manager
from backend.app.services.mediamtx import mediamtx_service
from backend.app.services.stream_manager import stream_manager

LOGGER = logging.getLogger("camera.platform.routes.health")
router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/healthz")
async def health():
    """Overall platform health probe."""
    db_ok = db.is_connected
    mediamtx_paths = await mediamtx_service.get_paths()
    mediamtx_ok = mediamtx_paths is not None

    status_str = "ok" if (db_ok and mediamtx_ok) else "degraded"
    return {
        "status": status_str,
        "service": settings.app_name,
        "environment": settings.app_env,
        "database": "connected" if db_ok else "disconnected",
        "mediamtx": "connected" if mediamtx_ok else "unreachable",
    }


@router.get("/health/database")
async def health_database(response: Response):
    """Database connectivity health probe."""
    if not db.is_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": "MongoDB is not connected"}

    try:
        # Fast query
        await db.cameras.count_documents({})
        return {
            "status": "ok",
            "database": settings.mongodb_database,
            "connected": True,
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": str(exc)}


@router.get("/health/mediamtx")
async def health_mediamtx(response: Response):
    """MediaMTX streaming engine health probe."""
    paths = await mediamtx_service.get_paths()
    if paths is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "error",
            "message": "MediaMTX Control API unreachable",
            "api_url": settings.mediamtx_api_url,
        }

    return {
        "status": "ok",
        "active_paths_count": len(paths),
        "paths": [p.get("name") for p in paths],
    }


@router.get("/health/ai")
async def health_ai():
    """AI pipeline and SageMaker status."""
    return {
        "status": "ok" if settings.ai_enabled else "disabled",
        "enabled": settings.ai_enabled,
        "model": settings.ai_model_name,
        "region": settings.sagemaker_region,
        "endpoint": settings.sagemaker_endpoint_name,
        "active_pipelines": len(ai_pipeline_manager.pipelines),
        "active_camera_ids": list(ai_pipeline_manager.pipelines.keys()),
        "mock_fallback": settings.ai_mock_fallback,
    }


@router.get("/api/system/status")
@router.get("/system/status")
async def system_status():
    """Comprehensive system telemetry for operator dashboard."""
    running_cameras = stream_manager.get_running_cameras()
    total_cameras = 0
    total_detections = 0

    if db.is_connected:
        try:
            total_cameras = await db.cameras.count_documents({})
            total_detections = await db.detection_events.count_documents({})
        except Exception:
            pass

    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "database": {
            "connected": db.is_connected,
            "database_name": settings.mongodb_database,
            "total_cameras": total_cameras,
            "total_detections": total_detections,
        },
        "streaming": {
            "active_streams_count": len(running_cameras),
            "streaming_camera_ids": running_cameras,
            "encoder": settings.ffmpeg_encoder,
            "resolution": settings.stream_resolution,
            "fps": settings.stream_fps,
        },
        "ai": {
            "enabled": settings.ai_enabled,
            "active_pipelines_count": len(ai_pipeline_manager.pipelines),
            "model": settings.ai_model_name,
            "inference_interval_seconds": settings.ai_inference_interval,
            "confidence_threshold": settings.ai_min_confidence,
        },
        "mediamtx": {
            "host": settings.mediamtx_host,
            "rtsp_port": settings.mediamtx_rtsp_port,
            "webrtc_port": settings.mediamtx_webrtc_port,
            "hls_port": settings.mediamtx_hls_port,
        },
    }
