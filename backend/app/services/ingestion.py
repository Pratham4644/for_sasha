from __future__ import annotations

import ipaddress
import json
import logging
import time
from urllib.parse import quote, urlsplit, urlunsplit

from backend.app.models import Camera, CameraStatus, IngestionMode
from backend.app.services.ai_pipeline import ai_pipeline_manager
from backend.app.services.camera import get_camera_credentials
from backend.app.services.mediamtx import mediamtx_service
from backend.app.services.stream_manager import stream_manager

LOGGER = logging.getLogger("camera.platform.ingestion")

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


def is_private_host(hostname: str) -> bool:
    """Return True when the camera host is on a private/local network."""
    if not hostname:
        return False

    host = hostname.strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True

    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False


def is_private_source(source_url: str) -> bool:
    """Detect RFC1918/local camera URLs that require remote-edge ingestion."""
    if not source_url:
        return False

    raw = source_url.strip()
    if "://" not in raw:
        raw = f"rtsp://{raw}"

    hostname = urlsplit(raw).hostname or ""
    return is_private_host(hostname)


def effective_ingestion_mode(camera: Camera) -> IngestionMode:
    """
    Resolve the effective ingestion mode.

    Existing cameras without an explicit mode but with private source URLs
    are treated as remote-edge to avoid AWS StreamManager pulling LAN IPs.
    """
    mode = camera.ingestion_mode
    if isinstance(mode, str):
        mode = IngestionMode(mode)

    if mode == IngestionMode.LOCAL and is_private_source(camera.source_url_template):
        return IngestionMode.REMOTE_EDGE

    return mode


def uses_local_stream_manager(camera: Camera) -> bool:
    return effective_ingestion_mode(camera) == IngestionMode.LOCAL


def build_source_url_with_credentials(
    source_url: str,
    username: str | None,
    password: str | None,
) -> str:
    """Build an authenticated RTSP URL for edge workers without logging secrets."""
    raw = source_url.strip()
    if "://" not in raw:
        raw = f"rtsp://{raw}"

    parsed = urlsplit(raw)
    if parsed.username or not (username or password):
        return raw

    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"

    user_part = quote(username or "", safe="")
    pass_part = quote(password or "", safe="")
    netloc = f"{user_part}:{pass_part}@{hostname}" if password else f"{user_part}@{hostname}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def start_local_ingestion(
    camera: Camera,
    username: str | None,
    password: str | None,
) -> bool:
    """Start embedded backend FFmpeg ingestion for locally reachable cameras."""
    _debug_log(
        "H1",
        "ingestion.py:start_local_ingestion",
        "starting local stream manager",
        {"camera_id": camera.id, "media_path": camera.media_path},
    )
    return stream_manager.start_camera(
        camera_id=camera.id,
        camera_url=camera.source_url_template,
        username=username,
        password=password,
        media_path=camera.media_path,
        resolution=camera.configured_resolution,
        fps=camera.configured_fps,
    )


def stop_local_ingestion(camera_id: str) -> None:
    stream_manager.stop_camera(camera_id)


async def start_camera_ingestion(camera: Camera) -> tuple[bool, str]:
    """
    Start ingestion appropriate to the camera mode.

    Returns (started, message). Remote-edge cameras do not spawn backend FFmpeg;
    they wait for the edge gateway to publish into MediaMTX.
    """
    username, password = get_camera_credentials(camera)
    mode = effective_ingestion_mode(camera)

    _debug_log(
        "H2",
        "ingestion.py:start_camera_ingestion",
        "resolved ingestion mode",
        {
            "camera_id": camera.id,
            "mode": mode.value,
            "media_path": camera.media_path,
            "private_source": is_private_source(camera.source_url_template),
        },
    )

    if mode == IngestionMode.REMOTE_EDGE:
        await mediamtx_service.provision_path(camera.media_path, source="publisher")
        if camera.ai_enabled:
            await mediamtx_service.provision_path(f"{camera.media_path}-ai", source="publisher")
            ai_pipeline_manager.start_pipeline(camera)
        return False, "Remote-edge camera awaiting edge gateway publisher."

    started = start_local_ingestion(camera, username, password)
    if camera.ai_enabled:
        ai_pipeline_manager.start_pipeline(camera)

    if started:
        return True, "Local FFmpeg ingestion started."
    return False, stream_manager.get_last_error(camera.id) or "Failed to start local FFmpeg ingestion."


async def stop_camera_ingestion(camera: Camera) -> None:
    """Stop ingestion workers for the camera."""
    if uses_local_stream_manager(camera):
        stop_local_ingestion(camera.id)
    ai_pipeline_manager.stop_pipeline(camera.id)


async def sync_remote_edge_status(camera: Camera) -> CameraStatus:
    """Update camera status from MediaMTX publisher state for remote-edge cameras."""
    media_status = await mediamtx_service.get_path_status(camera.media_path)
    video_available = bool(media_status.get("video_available") or media_status.get("source_ready"))
    publisher_connected = bool(media_status.get("publisher_connected"))

    _debug_log(
        "H3",
        "ingestion.py:sync_remote_edge_status",
        "mediamtx path status",
        {
            "camera_id": camera.id,
            "media_path": camera.media_path,
            "video_available": video_available,
            "publisher_connected": publisher_connected,
            "raw_status": media_status.get("status"),
        },
    )

    if video_available:
        return CameraStatus.ONLINE
    if publisher_connected:
        return CameraStatus.CONNECTING
    if camera.enabled and not camera.stream_paused:
        return CameraStatus.CONNECTING
    return CameraStatus.OFFLINE
