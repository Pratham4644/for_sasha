from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from backend.app.auth import hash_edge_token
from backend.app.config import settings
from backend.app.db import db
from backend.app.models import Camera, EdgeGateway, IngestionMode, utc_now
from backend.app.services.camera import get_camera_credentials
from backend.app.services.ingestion import (
    build_source_url_with_credentials,
    effective_ingestion_mode,
)

LOGGER = logging.getLogger("camera.platform.routes.edge")
router = APIRouter(prefix="/edge", tags=["Edge Gateway"])

_DEBUG_LOG_PATH = "debug-abbe6f.log"


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "abbe6f",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass
    # endregion


@dataclass
class EdgeGatewayContext:
    gateway_id: str
    organization_id: str


async def authenticate_edge_gateway(
    authorization: str | None = Header(default=None),
) -> EdgeGatewayContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid edge gateway authorization token.",
        )

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing edge gateway authorization token.",
        )

    if settings.edge_gateway_token and secrets.compare_digest(token, settings.edge_gateway_token):
        org_id = settings.edge_gateway_org_id
        if not org_id:
            org_doc = await db.organizations.find_one({})
            org_id = org_doc["id"] if org_doc else None
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Edge gateway organization is not configured.",
            )
        return EdgeGatewayContext(gateway_id="env-default", organization_id=org_id)

    token_hash = hash_edge_token(token)
    gateway_doc = await db.edge_gateways.find_one({"token_hash": token_hash, "is_active": True})
    if not gateway_doc:
        _debug_log(
            "H4",
            "edge.py:authenticate_edge_gateway",
            "edge token rejected",
            {"token_configured": bool(settings.edge_gateway_token)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid edge gateway authorization token.",
        )

    gateway = EdgeGateway(**gateway_doc)
    return EdgeGatewayContext(gateway_id=gateway.id, organization_id=gateway.organization_id)


def _camera_matches_gateway(camera: Camera, gateway: EdgeGatewayContext) -> bool:
    if camera.organization_id != gateway.organization_id:
        return False
    if camera.edge_gateway_id and camera.edge_gateway_id != gateway.gateway_id:
        return False
    return effective_ingestion_mode(camera) == IngestionMode.REMOTE_EDGE


async def _assigned_cameras(gateway: EdgeGatewayContext) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "organization_id": gateway.organization_id,
        "enabled": True,
        "stream_paused": {"$ne": True},
    }

    assigned: list[dict[str, Any]] = []
    cursor = db.cameras.find(query).sort("name", 1)
    async for doc in cursor:
        camera = Camera(**doc)
        if effective_ingestion_mode(camera) != IngestionMode.REMOTE_EDGE:
            continue
        if gateway.gateway_id != "env-default" and camera.edge_gateway_id not in (None, gateway.gateway_id):
            continue

        username, password = get_camera_credentials(camera)
        source_url = build_source_url_with_credentials(
            camera.source_url_template,
            username,
            password,
        )
        assigned.append(
            {
                "camera_id": camera.id,
                "name": camera.name,
                "media_path": camera.media_path,
                "source_url": source_url,
                "ai_enabled": camera.ai_enabled,
            }
        )

    return assigned


@router.get("/config")
async def get_edge_config(
    request: Request,
    gateway: EdgeGatewayContext = Depends(authenticate_edge_gateway),
):
    """Return cameras assigned to this authenticated edge gateway."""
    cameras = await _assigned_cameras(gateway)

    _debug_log(
        "H5",
        "edge.py:get_edge_config",
        "edge config served",
        {
            "gateway_id": gateway.gateway_id,
            "organization_id": gateway.organization_id,
            "camera_count": len(cameras),
            "media_paths": [item["media_path"] for item in cameras],
            "publish_host": settings.edge_publish_host,
            "publish_port": settings.mediamtx_rtsp_port,
        },
    )

    client_ip = request.client.host if request.client else None
    now = utc_now()
    if gateway.gateway_id != "env-default":
        await db.edge_gateways.update_one(
            {"id": gateway.gateway_id},
            {"$set": {"last_heartbeat": now, "last_seen_ip": client_ip, "updated_at": now}},
        )

    return {
        "gateway_id": gateway.gateway_id,
        "organization_id": gateway.organization_id,
        "mediamtx_publish_host": settings.edge_publish_host,
        "mediamtx_rtsp_port": settings.mediamtx_rtsp_port,
        "mediamtx_publish_username": settings.mediamtx_publish_username,
        "cameras": cameras,
    }


@router.post("/heartbeat")
async def post_edge_heartbeat(
    request: Request,
    payload: dict[str, Any] | None = None,
    gateway: EdgeGatewayContext = Depends(authenticate_edge_gateway),
):
    """Optional heartbeat from edge agent for gateway health tracking."""
    payload = payload or {}
    client_ip = request.client.host if request.client else None
    now = utc_now()

    if gateway.gateway_id != "env-default":
        await db.edge_gateways.update_one(
            {"id": gateway.gateway_id},
            {
                "$set": {
                    "last_heartbeat": now,
                    "last_seen_ip": client_ip,
                    "updated_at": now,
                }
            },
        )

    _debug_log(
        "H5",
        "edge.py:post_edge_heartbeat",
        "edge heartbeat received",
        {
            "gateway_id": gateway.gateway_id,
            "client_ip": client_ip,
            "active_workers": payload.get("active_workers"),
        },
    )

    return {
        "success": True,
        "gateway_id": gateway.gateway_id,
        "timestamp": now.isoformat(),
    }
