from __future__ import annotations

import logging
from typing import Any
import httpx
from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.mediamtx")


class MediaMTXService:
    """Manages integration with the MediaMTX streaming server and Control API."""

    def __init__(self) -> None:
        self.api_url = settings.mediamtx_api_url.rstrip("/")

    def _get_auth(self) -> tuple[str, str] | None:
        if settings.mediamtx_publish_username and settings.mediamtx_publish_password:
            return (settings.mediamtx_publish_username, settings.mediamtx_publish_password)
        return None

    async def get_paths(self) -> list[dict[str, Any]] | None:
        """Fetches active path items from MediaMTX API."""
        url = f"{self.api_url}/v3/paths/list"
        auth = self._get_auth()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url, auth=auth)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("items", [])
                LOGGER.warning("MediaMTX returned status %d on /v3/paths/list", res.status_code)
                return None
        except Exception as exc:
            LOGGER.debug("Failed to reach MediaMTX API (%s): %s", url, exc)
            return None

    async def get_path_detail(self, path_name: str) -> dict[str, Any] | None:
        """Queries a single path by name directly from MediaMTX API."""
        url = f"{self.api_url}/v3/paths/get/{path_name}"
        auth = self._get_auth()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url, auth=auth)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception as exc:
            LOGGER.debug("Failed to get path detail for %s: %s", path_name, exc)
            return None

    async def get_path_status(self, path_name: str) -> dict[str, Any]:
        """
        Queries status of an individual media path.

        MediaMTX v3 API uses:
            - sourceReady: bool    → true when a publisher is actively sending frames
            - source.type          → "rtspSession" / "rtmpSession" etc. when publisher connected
            - readers              → list of active consumers
            - tracks               → list of track descriptors (video/audio)

        Returns:
            {
                "online": bool,
                "source_ready": bool,
                "publisher_connected": bool,
                "video_available": bool,
                "status": "online" | "publisher_waiting" | "offline" | "unknown",
                "readers": int,
                "tracks": list,
                "raw": dict | None,
            }
        """
        # Try direct path query first (faster than listing all paths)
        detail = await self.get_path_detail(path_name)

        if detail is None:
            # Fall back to listing all paths
            paths = await self.get_paths()
            if paths is None:
                return {
                    "online": False,
                    "source_ready": False,
                    "publisher_connected": False,
                    "video_available": False,
                    "status": "unknown",
                    "message": "MediaMTX Control API unavailable",
                    "readers": 0,
                    "tracks": [],
                    "raw": None,
                }
            detail = next((p for p in paths if p.get("name") == path_name), None)

        if detail is None:
            return {
                "online": False,
                "source_ready": False,
                "publisher_connected": False,
                "video_available": False,
                "status": "offline",
                "readers": 0,
                "tracks": [],
                "raw": None,
            }

        # MediaMTX v3: sourceReady = publisher is actively streaming frames
        source_ready = bool(detail.get("sourceReady", detail.get("ready", False)))
        source = detail.get("source") or {}
        publisher_connected = bool(source.get("type"))  # type is set when publisher is connected
        readers = len(detail.get("readers", []))
        tracks = detail.get("tracks", [])

        # Video is available when sourceReady=true and there is a video track
        has_video_track = any(
            (
                t.get("type") in ("H264", "H265", "VP8", "VP9", "AV1", "video")
                or t.get("codec") in ("H264", "H265", "VP8", "VP9", "AV1")
            )
            if isinstance(t, dict)
            else str(t).upper() in ("H264", "H265", "VP8", "VP9", "AV1", "VIDEO")
            for t in tracks
        ) if tracks else source_ready  # If tracks not reported, rely on sourceReady

        if source_ready:
            status_str = "online"
        elif publisher_connected:
            status_str = "publisher_waiting"
        else:
            status_str = "offline"

        return {
            "online": source_ready,
            "source_ready": source_ready,
            "publisher_connected": publisher_connected,
            "video_available": source_ready and has_video_track,
            "status": status_str,
            "readers": readers,
            "tracks": tracks,
            "raw": detail,
        }

    async def provision_path(self, path_name: str, source: str = "publisher") -> bool:
        """Dynamically provisions a path in MediaMTX via POST /v3/config/paths/add."""
        url = f"{self.api_url}/v3/config/paths/add/{path_name}"
        auth = self._get_auth()
        payload = {"source": source}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(url, json=payload, auth=auth)
                if res.status_code in (200, 201):
                    return True
                # Path might already exist
                if res.status_code == 400 and "already exists" in res.text:
                    return True
                LOGGER.debug("MediaMTX provision path '%s' returned %d: %s", path_name, res.status_code, res.text)
                return False
        except Exception as exc:
            LOGGER.debug("Could not provision path '%s' in MediaMTX: %s", path_name, exc)
            return False

    async def delete_path(self, path_name: str) -> bool:
        """Removes a path configuration from MediaMTX."""
        url = f"{self.api_url}/v3/config/paths/delete/{path_name}"
        auth = self._get_auth()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.delete(url, auth=auth)
                return res.status_code in (200, 204)
        except Exception:
            return False

    def get_stream_urls(self, path_name: str) -> dict[str, str]:
        """Generates publicly accessible playback URLs for both standard and AI paths."""
        base_webrtc = settings.public_webrtc_url.rstrip("/")
        base_hls = settings.public_hls_url.rstrip("/")
        rtsp_host = settings.mediamtx_host
        rtsp_port = settings.mediamtx_rtsp_port

        return {
            "webrtc": f"{base_webrtc}/{path_name}/",
            "whep": f"{base_webrtc}/{path_name}/whep",
            "hls": f"{base_hls}/{path_name}/index.m3u8",
            "rtsp": f"rtsp://{rtsp_host}:{rtsp_port}/{path_name}",
            # AI stream paths
            "webrtc_ai": f"{base_webrtc}/{path_name}-ai/",
            "whep_ai": f"{base_webrtc}/{path_name}-ai/whep",
            "hls_ai": f"{base_hls}/{path_name}-ai/index.m3u8",
            "rtsp_ai": f"rtsp://{rtsp_host}:{rtsp_port}/{path_name}-ai",
        }


mediamtx_service = MediaMTXService()
