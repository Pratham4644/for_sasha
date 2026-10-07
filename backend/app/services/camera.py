from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backend.app.auth import decrypt_camera_credentials
from backend.app.config import settings
from backend.app.models import Camera
from backend.app.schemas import CameraPlaybackResponse, CameraResponse
from backend.app.services.mediamtx import mediamtx_service


def sanitize_source_url(raw_url: str) -> tuple[str, str | None, str | None]:
    """
    Strips inline credentials from a source URL and returns:
    (clean_url, extracted_username, extracted_password)
    """
    if "://" not in raw_url:
        return raw_url.strip(), None, None

    parsed = urlsplit(raw_url.strip())
    username = parsed.username
    password = parsed.password

    # Reconstruct netloc without credentials
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    port_part = f":{parsed.port}" if parsed.port else ""
    clean_netloc = f"{hostname}{port_part}"

    clean_url = urlunsplit((
        parsed.scheme,
        clean_netloc,
        parsed.path,
        parsed.query,
        parsed.fragment,
    ))
    return clean_url, username, password


def get_camera_credentials(camera: Camera) -> tuple[str | None, str | None]:
    """Retrieves decrypted username and password for a camera for backend streaming."""
    if not camera.credentials_ref:
        return None, None
    creds = decrypt_camera_credentials(camera.credentials_ref)
    return creds.get("username"), creds.get("password")


def format_camera_response(camera: Camera) -> CameraResponse:
    """Serializes a Camera document into an API response without leaking secrets."""
    return CameraResponse(
        id=camera.id,
        camera_id=camera.id,
        organization_id=camera.organization_id,
        site_id=camera.site_id,
        name=camera.name,
        description=camera.description,
        source_protocol=camera.source_protocol,
        stream_url=camera.source_url_template,
        source_url=camera.source_url_template,
        media_path=camera.media_path,
        configured_resolution=camera.configured_resolution,
        configured_fps=camera.configured_fps,
        enabled=camera.enabled,
        ai_enabled=camera.ai_enabled,
        ai_model=camera.ai_model,
        ingestion_mode=(
            camera.ingestion_mode.value
            if hasattr(camera.ingestion_mode, "value")
            else str(camera.ingestion_mode)
        ),
        edge_gateway_id=camera.edge_gateway_id,
        stream_paused=camera.stream_paused,
        status=camera.status.value if hasattr(camera.status, "value") else str(camera.status),
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def format_camera_playback(camera: Camera) -> CameraPlaybackResponse:
    """Builds playback configuration with reader credentials and WHEP/HLS URLs."""
    urls = mediamtx_service.get_stream_urls(camera.media_path)
    reader_creds = None
    if settings.mediamtx_read_username:
        reader_creds = {
            "username": settings.mediamtx_read_username,
            "password": settings.mediamtx_read_password,
        }

    return CameraPlaybackResponse(
        camera_id=camera.id,
        name=camera.name,
        media_path=camera.media_path,
        whep_url=urls["whep"],
        whep_ai_url=urls["whep_ai"] if camera.ai_enabled else None,
        hls_url=urls["hls"],
        hls_ai_url=urls["hls_ai"] if camera.ai_enabled else None,
        rtsp_url=urls["rtsp"],
        rtsp_ai_url=urls["rtsp_ai"] if camera.ai_enabled else None,
        reader_credentials=reader_creds,
    )
