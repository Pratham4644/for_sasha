from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Response, status

from backend.app.config import settings
from backend.app.db import db
from backend.app.models import utc_now
from backend.app.services.ai_pipeline import ai_pipeline_manager
from backend.app.services.mediamtx import mediamtx_service
from backend.app.services.sagemaker_client import SageMakerInferenceClient
from backend.app.services.stream_manager import stream_manager

LOGGER = logging.getLogger("camera.platform.routes.health")
router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/healthz")
@router.get("/health/public")
async def health():
    """Overall platform health probe reporting real component states."""
    db_ok = db.is_connected
    mediamtx_paths = await mediamtx_service.get_paths()
    mediamtx_ok = mediamtx_paths is not None

    total_cameras = 0
    online_cameras = 0
    if db_ok:
        try:
            total_cameras = await db.cameras.count_documents({})
            online_cameras = await db.cameras.count_documents({"status": "ONLINE"})
        except Exception:
            pass

    ai_count = len(ai_pipeline_manager.pipelines)
    ai_ok = settings.ai_enabled and ai_count > 0

    status_str = "healthy" if (db_ok and mediamtx_ok) else "degraded"
    now_ts = utc_now().isoformat()

    return {
        "status": status_str,
        "service": settings.app_name,
        "environment": settings.app_env,
        "database": db_ok,  # Boolean for frontend DetailedHealth interface
        "database_status": "connected" if db_ok else "disconnected",
        "mediamtx": "connected" if mediamtx_ok else "unreachable",
        "mediamtx_ok": mediamtx_ok,
        "timestamp": now_ts,
        "backend": {
            "status": "healthy",
            "ok": True,
            "version": "1.0.0",
        },
        "cameras": {
            "status": "healthy" if online_cameras > 0 else "idle",
            "ok": online_cameras > 0,
            "total": total_cameras,
            "online": online_cameras,
        },
        "ai": {
            "status": "healthy" if ai_ok else "idle",
            "ok": ai_ok,
            "enabled": settings.ai_enabled,
            "active_pipelines": ai_count,
            "model": settings.ai_model_name,
            "total_inferences": SageMakerInferenceClient.total_inferences,
            "successful_inferences": SageMakerInferenceClient.successful_inferences,
            "last_latency_ms": round(SageMakerInferenceClient.last_latency_ms, 2),
        },
    }


@router.get("/health/database")
async def health_database(response: Response):
    """Database connectivity health probe."""
    if not db.is_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": "MongoDB is not connected", "connected": False}

    try:
        count = await db.cameras.count_documents({})
        return {
            "status": "ok",
            "database": settings.mongodb_database,
            "connected": True,
            "total_cameras": count,
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": str(exc), "connected": False}


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
    """AI pipeline and inference engine status."""
    active_cams = list(ai_pipeline_manager.pipelines.keys())
    active_count = len(active_cams)
    is_healthy = settings.ai_enabled and active_count > 0

    return {
        "status": "healthy" if is_healthy else ("disabled" if not settings.ai_enabled else "idle"),
        "active_cameras": active_count,
        "active_camera_ids": active_cams,
        "enabled": settings.ai_enabled,
        "mode": SageMakerInferenceClient.active_mode,
        "model": "YOLO26s (80 classes)",
        "endpoint": settings.sagemaker_endpoint_name,
        "total_inferences": SageMakerInferenceClient.total_inferences,
        "successful_inferences": SageMakerInferenceClient.successful_inferences,
        "last_inference_at": SageMakerInferenceClient.last_inference_at,
        "last_latency_ms": round(SageMakerInferenceClient.last_latency_ms, 2),
    }


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
