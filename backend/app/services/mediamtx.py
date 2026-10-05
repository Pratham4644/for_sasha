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

    async def get_path_status(self, path_name: str) -> dict[str, Any]:
        """
        Queries status of an individual media path.
        Returns:
            {"online": bool, "status": "online" | "offline" | "unknown", "readers": int}
        """
        paths = await self.get_paths()
        if paths is None:
            return {
                "online": False,
                "status": "unknown",
                "message": "MediaMTX Control API unavailable",
                "readers": 0,
            }

        target = next((p for p in paths if p.get("name") == path_name), None)
        if target is None:
            return {
                "online": False,
                "status": "offline",
                "readers": 0,
            }

        is_online = bool(target.get("ready") or target.get("online", False))
        readers = len(target.get("readers", []))

        return {
            "online": is_online,
            "status": "online" if is_online else "offline",
            "readers": readers,
            "tracks": target.get("tracks", []),
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
