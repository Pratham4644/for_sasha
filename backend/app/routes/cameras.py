from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.auth import encrypt_camera_credentials, get_current_user
from backend.app.config import settings
from backend.app.db import db
from backend.app.models import Camera, CameraStatus, User, UserRole, utc_now
from backend.app.permissions import get_tenant_filter, require_permission
from backend.app.schemas import (
    ApiResponse,
    CameraCreate,
    CameraPlaybackResponse,
    CameraResponse,
    CameraStreamResponse,
    CameraUpdate,
)
from backend.app.services.ai_pipeline import ai_pipeline_manager
from backend.app.services.camera import (
    format_camera_playback,
    format_camera_response,
    get_camera_credentials,
    sanitize_source_url,
)
from backend.app.services.mediamtx import mediamtx_service
from backend.app.services.stream_manager import stream_manager, test_camera_connectivity

LOGGER = logging.getLogger("camera.platform.routes.cameras")
router = APIRouter(prefix="/cameras", tags=["Cameras"])


async def _resolve_camera(camera_id: str, current_user: User) -> Camera:
    """Finds camera by either 'id' or 'media_path', enforcing tenant isolation."""
    query = get_tenant_filter(current_user, {
        "$or": [{"id": camera_id}, {"media_path": camera_id}]
    })
    doc = await db.cameras.find_one(query)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' not found.",
        )
    return Camera(**doc)


@router.post("", response_model=ApiResponse[CameraResponse], status_code=status.HTTP_201_CREATED)
async def create_camera(
    req: CameraCreate,
    current_user: User = Depends(require_permission("camera:create")),
):
    """
    Registers a new camera dynamically into MongoDB.
    No hardcoded camera paths. Media path is generated or verified.
    """
    target_org_id = current_user.organization_id

    # 1. Resolve site_id
    site_id = req.site_id
    if not site_id:
        # Check for first site or create default site
        first_site = await db.sites.find_one({"organization_id": target_org_id})
        if first_site:
            site_id = first_site["id"]
        else:
            default_site_id = str(uuid.uuid4())
            await db.sites.insert_one({
                "id": default_site_id,
                "organization_id": target_org_id,
                "name": "Default Site",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            })
            site_id = default_site_id

    # 2. Determine unique media_path
    if req.media_path and req.media_path.strip():
        media_path = req.media_path.strip().replace(" ", "_")
    elif req.camera_id and req.camera_id.strip():
        media_path = req.camera_id.strip().replace(" ", "_")
    else:
        media_path = f"cam_{uuid.uuid4().hex[:8]}"

    # Verify media_path uniqueness
    existing = await db.cameras.find_one({
        "organization_id": target_org_id,
        "media_path": media_path,
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Media path '{media_path}' already exists in your organization.",
        )

    # 3. Sanitize source URL and encrypt credentials
    clean_url, ext_user, ext_pass = sanitize_source_url(req.source_url)
    username = req.username or ext_user
    password = req.password or ext_pass

    credentials_ref = None
    if username or password:
        credentials_ref = encrypt_camera_credentials({
            "username": username or "",
            "password": password or "",
        })

    # 4. Provision path in MediaMTX if enabled
    if req.enabled:
        await mediamtx_service.provision_path(media_path, source="publisher")
        if req.ai_enabled:
            await mediamtx_service.provision_path(f"{media_path}-ai", source="publisher")

    # 5. Persist to MongoDB
    camera = Camera(
        id=req.camera_id if req.camera_id else str(uuid.uuid4()),
        organization_id=target_org_id,
        site_id=site_id,
        name=req.name.strip(),
        source_protocol=req.source_protocol.upper(),
        source_url_template=clean_url,
        media_path=media_path,
        credentials_ref=credentials_ref,
        enabled=req.enabled,
        ai_enabled=req.ai_enabled,
        ai_model=req.ai_model,
        ai_endpoint=req.ai_endpoint,
        configured_resolution=req.configured_resolution,
        configured_fps=req.configured_fps,
        status=CameraStatus.OFFLINE,
    )

    if req.enabled:
        try:
            started = stream_manager.start_camera(
                camera_id=camera.id,
                camera_url=camera.source_url_template,
                username=username,
                password=password,
                media_path=camera.media_path,
                resolution=camera.configured_resolution,
                fps=camera.configured_fps,
            )
            if started:
                # Set CONNECTING — stream_manager lifecycle will transition to ONLINE
                # only after MediaMTX publisher is verified
                camera.status = CameraStatus.CONNECTING
                if camera.ai_enabled:
                    ai_pipeline_manager.start_pipeline(camera)
        except Exception as exc:
            LOGGER.error("Auto-start stream failed for new camera %s: %s", camera.name, exc)

    await db.cameras.insert_one(camera.model_dump(mode="json"))
    LOGGER.info("Registered dynamic camera: %s (media_path: %s)", camera.name, camera.media_path)

    return ApiResponse(success=True, data=format_camera_response(camera))


@router.get("", response_model=ApiResponse[list[CameraResponse]])
async def list_cameras(
    site_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    current_user: User = Depends(require_permission("camera:read")),
):
    """Lists cameras for current tenant with optional status/site filters."""
    query: dict = {}
    if site_id:
        query["site_id"] = site_id
    if status_filter:
        query["status"] = status_filter.upper()

    tenant_query = get_tenant_filter(current_user, query)
    cursor = db.cameras.find(tenant_query).sort("created_at", -1)

    cameras = [format_camera_response(Camera(**doc)) async for doc in cursor]
    return ApiResponse(success=True, data=cameras)


@router.get("/{camera_id}", response_model=ApiResponse[CameraResponse])
async def get_camera(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:read")),
):
    """Retrieves a single camera by ID."""
    camera = await _resolve_camera(camera_id, current_user)
    return ApiResponse(success=True, data=format_camera_response(camera))


@router.put("/{camera_id}", response_model=ApiResponse[CameraResponse])
@router.patch("/{camera_id}", response_model=ApiResponse[CameraResponse])
async def update_camera(
    camera_id: str,
    req: CameraUpdate,
    current_user: User = Depends(require_permission("camera:update")),
):
    """Updates camera configuration or credentials."""
    camera = await _resolve_camera(camera_id, current_user)
    updates: dict = {"updated_at": utc_now()}

    if req.name is not None:
        updates["name"] = req.name.strip()
    if req.description is not None:
        updates["description"] = req.description
    if req.configured_resolution is not None:
        updates["configured_resolution"] = req.configured_resolution
    if req.configured_fps is not None:
        updates["configured_fps"] = req.configured_fps
    if req.ai_enabled is not None:
        updates["ai_enabled"] = req.ai_enabled
    if req.ai_model is not None:
        updates["ai_model"] = req.ai_model
    if req.ai_endpoint is not None:
        updates["ai_endpoint"] = req.ai_endpoint

    if req.source_url is not None:
        clean_url, ext_user, ext_pass = sanitize_source_url(req.source_url)
        updates["source_url_template"] = clean_url
        user_to_save = req.username or ext_user
        pass_to_save = req.password or ext_pass
        if user_to_save or pass_to_save:
            updates["credentials_ref"] = encrypt_camera_credentials({
                "username": user_to_save or "",
                "password": pass_to_save or "",
            })
    elif req.username is not None or req.password is not None:
        updates["credentials_ref"] = encrypt_camera_credentials({
            "username": req.username or "",
            "password": req.password or "",
        })

    if req.enabled is not None:
        updates["enabled"] = req.enabled
        if not req.enabled:
            # Stop streaming if camera was disabled
            stream_manager.stop_camera(camera.id)
            ai_pipeline_manager.stop_pipeline(camera.id)
            updates["status"] = CameraStatus.OFFLINE.value

    await db.cameras.update_one({"id": camera.id}, {"$set": updates})
    updated_doc = await db.cameras.find_one({"id": camera.id})
    return ApiResponse(success=True, data=format_camera_response(Camera(**updated_doc)))


@router.delete("/{camera_id}", response_model=ApiResponse[dict[str, str]])
async def delete_camera(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:delete")),
):
    """Stops and deletes camera, removing MediaMTX paths."""
    camera = await _resolve_camera(camera_id, current_user)

    # 1. Stop active streaming and AI processes
    stream_manager.stop_camera(camera.id)
    ai_pipeline_manager.stop_pipeline(camera.id)

    # 2. Delete MediaMTX paths
    await mediamtx_service.delete_path(camera.media_path)
    await mediamtx_service.delete_path(f"{camera.media_path}-ai")

    # 3. Delete from MongoDB
    await db.cameras.delete_one({"id": camera.id})
    LOGGER.info("Deleted camera %s (%s)", camera.name, camera.id)

    return ApiResponse(success=True, data={"message": "Camera deleted successfully."})


@router.post("/{camera_id}/start", response_model=ApiResponse[dict[str, Any]])
async def start_camera_stream(
    camera_id: str,
    current_user: User = Depends(require_permission("stream:control")),
):
    """
    Starts independent FFmpeg ingestion process for the camera.
    Also starts AI pipeline if ai_enabled is True.
    """
    camera = await _resolve_camera(camera_id, current_user)

    if not camera.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start disabled camera. Enable it first.",
        )

    username, password = get_camera_credentials(camera)

    started = stream_manager.start_camera(
        camera_id=camera.id,
        camera_url=camera.source_url_template,
        username=username,
        password=password,
        media_path=camera.media_path,
        resolution=camera.configured_resolution,
        fps=camera.configured_fps,
    )

    if not started:
        err = stream_manager.get_last_error(camera.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start camera stream: {err or 'FFmpeg process failed to launch'}",
        )

    # Start AI pipeline if enabled
    if camera.ai_enabled:
        ai_pipeline_manager.start_pipeline(camera)

    # Set CONNECTING — lifecycle thread will update to ONLINE after publisher verified
    await db.cameras.update_one({"id": camera.id}, {"$set": {"status": CameraStatus.CONNECTING.value}})

    urls = mediamtx_service.get_stream_urls(camera.media_path)
    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "status": "connecting",
            "message": "Camera stream starting — will become ONLINE once publisher is confirmed.",
            "streams": urls,
        },
    )


@router.post("/{camera_id}/stop", response_model=ApiResponse[dict[str, Any]])
async def stop_camera_stream(
    camera_id: str,
    current_user: User = Depends(require_permission("stream:control")),
):
    """Stops the camera's FFmpeg stream and AI pipeline cleanly."""
    camera = await _resolve_camera(camera_id, current_user)

    stream_manager.stop_camera(camera.id)
    ai_pipeline_manager.stop_pipeline(camera.id)

    await db.cameras.update_one({"id": camera.id}, {"$set": {"status": CameraStatus.OFFLINE.value}})

    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "status": "stopped",
            "message": "Camera stream and AI worker stopped.",
        },
    )


@router.post("/{camera_id}/restart", response_model=ApiResponse[dict[str, Any]])
async def restart_camera_stream(
    camera_id: str,
    current_user: User = Depends(require_permission("stream:control")),
):
    """Restarts stream ingestion and AI pipeline."""
    camera = await _resolve_camera(camera_id, current_user)

    stream_manager.stop_camera(camera.id)
    ai_pipeline_manager.stop_pipeline(camera.id)

    username, password = get_camera_credentials(camera)
    stream_manager.start_camera(
        camera_id=camera.id,
        camera_url=camera.source_url_template,
        username=username,
        password=password,
        media_path=camera.media_path,
        resolution=camera.configured_resolution,
        fps=camera.configured_fps,
    )

    if camera.ai_enabled:
        ai_pipeline_manager.start_pipeline(camera)

    # Set CONNECTING — will transition to ONLINE once publisher confirmed
    await db.cameras.update_one({"id": camera.id}, {"$set": {"status": CameraStatus.CONNECTING.value}})

    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "status": "connecting",
            "message": "Camera stream restarting — will become ONLINE once publisher is confirmed.",
        },
    )


@router.post("/{camera_id}/enable", response_model=ApiResponse[dict[str, Any]])
async def enable_camera(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:update")),
):
    """Enables the camera and starts ingestion stream & AI pipeline."""
    camera = await _resolve_camera(camera_id, current_user)
    username, password = get_camera_credentials(camera)

    started = stream_manager.start_camera(
        camera_id=camera.id,
        camera_url=camera.source_url_template,
        username=username,
        password=password,
        media_path=camera.media_path,
        resolution=camera.configured_resolution,
        fps=camera.configured_fps,
    )
    if camera.ai_enabled:
        ai_pipeline_manager.start_pipeline(camera)

    await db.cameras.update_one(
        {"id": camera.id},
        {"$set": {"enabled": True, "status": CameraStatus.ONLINE.value if started else CameraStatus.OFFLINE.value}}
    )

    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "enabled": True,
            "status": "online" if started else "offline",
            "message": f"Camera {camera.name} enabled and stream started.",
        },
    )


@router.post("/{camera_id}/disable", response_model=ApiResponse[dict[str, Any]])
async def disable_camera(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:update")),
):
    """Disables the camera and cleanly stops ingestion stream & AI pipeline."""
    camera = await _resolve_camera(camera_id, current_user)

    stream_manager.stop_camera(camera.id)
    ai_pipeline_manager.stop_pipeline(camera.id)

    await db.cameras.update_one(
        {"id": camera.id},
        {"$set": {"enabled": False, "status": CameraStatus.OFFLINE.value}}
    )

    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "enabled": False,
            "status": "offline",
            "message": f"Camera {camera.name} disabled and stream stopped.",
        },
    )


@router.get("/{camera_id}/status", response_model=ApiResponse[dict[str, Any]])
async def get_camera_status(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:read")),
):
    """Checks online status via MediaMTX and active FFmpeg processes."""
    camera = await _resolve_camera(camera_id, current_user)
    media_status = await mediamtx_service.get_path_status(camera.media_path)
    is_ffmpeg_running = stream_manager.is_running(camera.id)
    is_ai_running = ai_pipeline_manager.is_running(camera.id)
    stream_info = stream_manager.get_stream_info(camera.id)

    # True ONLINE requires MediaMTX sourceReady=true (frames actually flowing)
    video_available = bool(media_status.get("video_available") or media_status.get("source_ready"))
    publisher_connected = bool(media_status.get("publisher_connected"))

    if video_available:
        effective_status = "online"
        new_db_status = CameraStatus.ONLINE
    elif is_ffmpeg_running or publisher_connected:
        effective_status = "connecting"
        new_db_status = CameraStatus.CONNECTING
    else:
        effective_status = "offline"
        new_db_status = CameraStatus.OFFLINE

    # Update database if status changed
    if new_db_status.value != camera.status.value:
        await db.cameras.update_one({"id": camera.id}, {"$set": {"status": new_db_status.value}})

    return ApiResponse(
        success=True,
        data={
            "camera_id": camera.id,
            "name": camera.name,
            "status": effective_status.upper(),
            "online": effective_status == "online",
            "ffmpeg_running": is_ffmpeg_running,
            "mediamtx_publisher": bool(media_status.get("publisher_connected") or media_status.get("source_ready")),
            "mediamtx_source_ready": media_status.get("source_ready", False),
            "video_available": video_available,
            "ai_enabled": camera.ai_enabled,
            "ai_status": "RUNNING" if is_ai_running else ("STOPPED" if camera.ai_enabled else "DISABLED"),
            "ai_running": is_ai_running,
            "readers": media_status.get("readers", 0),
            "tracks": media_status.get("tracks", []),
            "media_path": camera.media_path,
            "stream_state": stream_info.get("state"),
            "last_error": stream_info.get("last_error"),
            "reconnect_attempt": stream_info.get("reconnect_attempt", 0),
        },
    )


@router.get("/{camera_id}/stream", response_model=ApiResponse[CameraStreamResponse])
async def get_camera_stream(
    camera_id: str,
    current_user: User = Depends(require_permission("stream:read")),
):
    """Returns accessible stream URLs for the camera."""
    camera = await _resolve_camera(camera_id, current_user)
    media_status = await mediamtx_service.get_path_status(camera.media_path)
    is_online = bool(media_status.get("online") or stream_manager.is_running(camera.id))

    urls = mediamtx_service.get_stream_urls(camera.media_path)

    return ApiResponse(
        success=True,
        data=CameraStreamResponse(
            camera_id=camera.id,
            status="online" if is_online else "offline",
            online=is_online,
            streams=urls,
        ),
    )


@router.get("/{camera_id}/playback", response_model=ApiResponse[CameraPlaybackResponse])
async def get_camera_playback(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:read")),
):
    """Returns WebRTC / WHEP playback configuration for the frontend."""
    camera = await _resolve_camera(camera_id, current_user)
    playback = format_camera_playback(camera)
    return ApiResponse(success=True, data=playback)


@router.post("/{camera_id}/test", response_model=ApiResponse[dict[str, Any]])
async def test_camera_connection(
    camera_id: str,
    current_user: User = Depends(require_permission("camera:read")),
):
    """
    Performs full 5-stage RTSP source connectivity test:
    DNS resolution -> TCP port probe -> RTSP auth check -> Stream open -> FFmpeg frame decode.
    """
    camera = await _resolve_camera(camera_id, current_user)
    username, password = get_camera_credentials(camera)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: test_camera_connectivity(
            camera.source_url_template,
            username=username,
            password=password,
            timeout=5.0,
        ),
    )
    return ApiResponse(success=result.get("success", False), data=result)


@router.post("/test-source", response_model=ApiResponse[dict[str, Any]])
async def test_source_url(
    payload: dict[str, Any],
    current_user: User = Depends(require_permission("camera:create")),
):
    """
    Tests an unpersisted camera source URL and credentials before creating a camera.
    """
    url = payload.get("source_url", "")
    username = payload.get("username")
    password = payload.get("password")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: test_camera_connectivity(url, username=username, password=password, timeout=5.0),
    )
    return ApiResponse(success=result.get("success", False), data=result)
