from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.stream_manager")

# ── Reconnect backoff schedule ────────────────────────────────────────────────
# Each retry waits at most 30 seconds, never exceeds that ceiling.
BACKOFF_STEPS = [2, 4, 8, 16, 30]
BACKOFF_MAX = 30

# How long to wait after FFmpeg starts before checking MediaMTX for publisher
PUBLISHER_VERIFICATION_DELAY = 4.0  # seconds

# Max seconds to wait for MediaMTX to show publisher after FFmpeg starts
PUBLISHER_WAIT_TIMEOUT = 12.0  # seconds


class StreamState(str, Enum):
    STOPPED = "STOPPED"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class CameraStreamInfo:
    """Tracks per-camera stream state independently from other cameras."""
    camera_id: str
    state: StreamState = StreamState.STOPPED
    process: subprocess.Popen | None = None
    last_error: str | None = None
    reconnect_attempt: int = 0
    started_at: float = 0.0
    last_connected_at: float = 0.0
    _stop_requested: bool = False
    _lifecycle_active: bool = False  # True while a lifecycle thread owns this camera

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


def check_dns_resolvable(host: str) -> tuple[bool, str]:
    """Tests if hostname can be resolved via DNS."""
    try:
        ip = socket.gethostbyname(host)
        return True, ip
    except socket.gaierror as exc:
        return False, str(exc)


def check_tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    """Tests if TCP port is open and responding."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_camera_connectivity(
    camera_url: str,
    username: str | None = None,
    password: str | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """
    Performs comprehensive 5-stage RTSP source connectivity test:
    1. DNS resolution
    2. TCP port reachability
    3. RTSP stream probe (ffprobe)
    4. RTSP authentication validation
    5. FFmpeg frame decode test (reads 2 actual frames to null sink)

    Returns structured diagnostic information:
    Diagnostic codes: OK, CAMERA_UNREACHABLE, RTSP_CONNECTION_FAILED,
    RTSP_AUTH_FAILED, NO_VIDEO_FRAMES, FFMPEG_FAILED.
    """
    import json
    from urllib.parse import urlsplit, quote, urlunsplit

    # 1. URL Parse & Validation
    if not camera_url or not camera_url.strip():
        return {
            "success": False,
            "diagnostic_code": "CAMERA_UNREACHABLE",
            "message": "Camera source URL is empty.",
            "dns_resolvable": False,
            "port_reachable": False,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }

    raw_url = camera_url.strip()
    if "://" not in raw_url:
        raw_url = f"rtsp://{raw_url}"

    parsed = urlsplit(raw_url)
    hostname = parsed.hostname or ""
    port = parsed.port or (554 if parsed.scheme == "rtsp" else 80)

    if not hostname:
        return {
            "success": False,
            "diagnostic_code": "CAMERA_UNREACHABLE",
            "message": f"Could not determine hostname from URL: {camera_url}",
            "dns_resolvable": False,
            "port_reachable": False,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }

    # 2. DNS Check
    dns_ok, ip_or_err = check_dns_resolvable(hostname)
    if not dns_ok:
        return {
            "success": False,
            "diagnostic_code": "CAMERA_UNREACHABLE",
            "message": f"DNS resolution failed for '{hostname}': {ip_or_err}",
            "dns_resolvable": False,
            "port_reachable": False,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }

    # 3. TCP Port Check
    port_ok = check_tcp_reachable(hostname, port, timeout=3.0)
    if not port_ok:
        return {
            "success": False,
            "diagnostic_code": "RTSP_CONNECTION_FAILED",
            "message": f"Connection refused or timed out on {hostname}:{port}.",
            "dns_resolvable": True,
            "port_reachable": False,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }

    # Build authenticated probe URL
    if username and password:
        enc_u = quote(username, safe="")
        enc_p = quote(password, safe="")
        host_part = f"{hostname}:{port}" if parsed.port else hostname
        auth_url = urlunsplit((
            parsed.scheme, f"{enc_u}:{enc_p}@{host_part}",
            parsed.path, parsed.query, parsed.fragment,
        ))
    else:
        auth_url = raw_url

    # 4. ffprobe Stream Inspection
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    timeout_us = str(int(timeout * 1_000_000))
    probe_cmd = [
        ffprobe_bin,
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-timeout", timeout_us,
        "-show_streams",
        "-show_format",
        "-print_format", "json",
        auth_url,
    ]

    try:
        probe_res = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 2.0,
        )
        stderr_text = (probe_res.stderr or "").lower()

        if "401" in stderr_text or "unauthorized" in stderr_text or "authentication failed" in stderr_text:
            return {
                "success": False,
                "diagnostic_code": "RTSP_AUTH_FAILED",
                "message": "RTSP authentication failed (401 Unauthorized). Check camera credentials.",
                "dns_resolvable": True,
                "port_reachable": True,
                "auth_valid": False,
                "stream_openable": False,
                "frames_decodable": False,
            }

        if probe_res.returncode != 0:
            if "refused" in stderr_text or "timeout" in stderr_text:
                return {
                    "success": False,
                    "diagnostic_code": "RTSP_CONNECTION_FAILED",
                    "message": f"RTSP connection failed: {probe_res.stderr.strip()[:200]}",
                    "dns_resolvable": True,
                    "port_reachable": True,
                    "auth_valid": False,
                    "stream_openable": False,
                    "frames_decodable": False,
                }
            return {
                "success": False,
                "diagnostic_code": "FFMPEG_FAILED",
                "message": f"ffprobe error: {probe_res.stderr.strip()[:200]}",
                "dns_resolvable": True,
                "port_reachable": True,
                "auth_valid": True,
                "stream_openable": False,
                "frames_decodable": False,
            }

        # Check for video streams
        data = json.loads(probe_res.stdout) if probe_res.stdout else {}
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

        if not video_stream:
            return {
                "success": False,
                "diagnostic_code": "NO_VIDEO_FRAMES",
                "message": "RTSP connection succeeded, but no video track found in stream.",
                "dns_resolvable": True,
                "port_reachable": True,
                "auth_valid": True,
                "stream_openable": True,
                "frames_decodable": False,
            }

        codec_name = video_stream.get("codec_name", "unknown")
        width = video_stream.get("width")
        height = video_stream.get("height")
        resolution = f"{width}x{height}" if width and height else "unknown"

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "diagnostic_code": "RTSP_CONNECTION_FAILED",
            "message": f"RTSP stream probe timed out after {timeout}s.",
            "dns_resolvable": True,
            "port_reachable": True,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }
    except Exception as exc:
        return {
            "success": False,
            "diagnostic_code": "FFMPEG_FAILED",
            "message": f"Unexpected error probing RTSP stream: {exc}",
            "dns_resolvable": True,
            "port_reachable": True,
            "auth_valid": False,
            "stream_openable": False,
            "frames_decodable": False,
        }

    # 5. FFmpeg Frame Decode Test (Verify actual video frames)
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    decode_cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-timeout", timeout_us,
        "-i", auth_url,
        "-vframes", "2",
        "-f", "null",
        "-",
    ]

    try:
        decode_res = subprocess.run(
            decode_cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 2.0,
        )
        if decode_res.returncode == 0:
            return {
                "success": True,
                "diagnostic_code": "OK",
                "message": "Camera connectivity test passed successfully. Video frames verified.",
                "dns_resolvable": True,
                "port_reachable": True,
                "auth_valid": True,
                "stream_openable": True,
                "frames_decodable": True,
                "video_codec": codec_name,
                "resolution": resolution,
            }
        else:
            return {
                "success": False,
                "diagnostic_code": "FFMPEG_FAILED",
                "message": f"FFmpeg failed to decode frames: {decode_res.stderr.strip()[:200]}",
                "dns_resolvable": True,
                "port_reachable": True,
                "auth_valid": True,
                "stream_openable": True,
                "frames_decodable": False,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "diagnostic_code": "NO_VIDEO_FRAMES",
            "message": "FFmpeg frame decode timed out waiting for video frames.",
            "dns_resolvable": True,
            "port_reachable": True,
            "auth_valid": True,
            "stream_openable": True,
            "frames_decodable": False,
        }
    except Exception as exc:
        return {
            "success": False,
            "diagnostic_code": "FFMPEG_FAILED",
            "message": f"Frame decode verification error: {exc}",
            "dns_resolvable": True,
            "port_reachable": True,
            "auth_valid": True,
            "stream_openable": True,
            "frames_decodable": False,
        }


class StreamManager:
    """
    Generalized stream supervisor managing independent FFmpeg ingestion processes.
    Each camera runs in isolation — one camera's failure never affects another.
    Supports automatic exponential-backoff reconnection.
    """

    def __init__(self) -> None:
        self._cameras: dict[str, CameraStreamInfo] = {}
        self._lock = threading.Lock()

        # Callbacks allow the camera routes to update DB status without circular imports
        self._status_callbacks: list[Callable[[str, StreamState, str | None], None]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def register_status_callback(
        self,
        cb: Callable[[str, StreamState, str | None], None],
    ) -> None:
        """Register a callback invoked whenever a camera's stream state changes."""
        self._status_callbacks.append(cb)

    def start_camera(
        self,
        camera_id: str,
        camera_url: str,
        username: str | None = None,
        password: str | None = None,
        media_path: str | None = None,
        resolution: str = "1280x720",
        fps: float = 15.0,
    ) -> bool:
        """
        Starts an independent FFmpeg relay subprocess for a given camera.
        Returns True if the start process was initiated (not necessarily streaming yet).
        """
        with self._lock:
            info = self._cameras.get(camera_id)
            if info and (info.is_running or info._lifecycle_active):
                LOGGER.info(
                    "Camera %s already has an active stream lifecycle (running=%s)",
                    camera_id,
                    info.is_running,
                )
                return True

            if info is None:
                info = CameraStreamInfo(camera_id=camera_id)
                self._cameras[camera_id] = info

            info._stop_requested = False
            info._lifecycle_active = True
            info.state = StreamState.CONNECTING
            info.reconnect_attempt = 0
            info.last_error = None

        # Launch in background thread so this call is non-blocking
        thread = threading.Thread(
            target=self._run_camera_lifecycle,
            args=(camera_id, camera_url, username, password, media_path, resolution, fps),
            daemon=True,
            name=f"stream-{camera_id}",
        )
        thread.start()
        self._notify_status(camera_id, StreamState.CONNECTING, None)
        LOGGER.info("Stream lifecycle thread started for camera %s", camera_id)
        return True

    def stop_camera(self, camera_id: str) -> bool:
        """Stops the camera stream and prevents automatic reconnection."""
        with self._lock:
            info = self._cameras.get(camera_id)
            if info is None:
                return False

            info._stop_requested = True
            info._lifecycle_active = False
            info.state = StreamState.STOPPED
            proc = info.process
            info.process = None

        if proc and proc.poll() is None:
            LOGGER.info("Terminating FFmpeg for camera %s (PID %d)", camera_id, proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                LOGGER.warning("FFmpeg for %s did not terminate gracefully, killing.", camera_id)
                proc.kill()
            except Exception as exc:
                LOGGER.error("Error stopping camera %s: %s", camera_id, exc)

        self._notify_status(camera_id, StreamState.STOPPED, None)
        return True

    def restart_camera(
        self,
        camera_id: str,
        camera_url: str,
        username: str | None = None,
        password: str | None = None,
        media_path: str | None = None,
        resolution: str = "1280x720",
        fps: float = 15.0,
    ) -> bool:
        """Stops then starts a camera cleanly."""
        self.stop_camera(camera_id)
        time.sleep(0.5)
        return self.start_camera(
            camera_id, camera_url, username, password, media_path, resolution, fps
        )

    def is_running(self, camera_id: str) -> bool:
        """Returns True only if FFmpeg process is alive."""
        with self._lock:
            info = self._cameras.get(camera_id)
            return info is not None and info.is_running

    def get_state(self, camera_id: str) -> StreamState | None:
        with self._lock:
            info = self._cameras.get(camera_id)
            return info.state if info else None

    def get_running_cameras(self) -> list[str]:
        with self._lock:
            return [cid for cid, info in self._cameras.items() if info.is_running]

    def get_last_error(self, camera_id: str) -> str | None:
        with self._lock:
            info = self._cameras.get(camera_id)
            return info.last_error if info else None

    def get_stream_info(self, camera_id: str) -> dict[str, Any]:
        with self._lock:
            info = self._cameras.get(camera_id)
            if not info:
                return {"state": "STOPPED", "running": False}
            return {
                "state": info.state.value,
                "running": info.is_running,
                "last_error": info.last_error,
                "reconnect_attempt": info.reconnect_attempt,
                "pid": info.process.pid if info.process and info.process.poll() is None else None,
            }

    def stop_all(self) -> None:
        with self._lock:
            camera_ids = list(self._cameras.keys())
        for cid in camera_ids:
            self.stop_camera(cid)
        LOGGER.info("All camera streams stopped.")

    # ── Private: Camera Lifecycle ─────────────────────────────────────────────

    def _run_camera_lifecycle(
        self,
        camera_id: str,
        camera_url: str,
        username: str | None,
        password: str | None,
        media_path: str | None,
        resolution: str,
        fps: float,
    ) -> None:
        """
        Runs the full camera lifecycle loop including automatic reconnection.
        This runs in a dedicated daemon thread per camera.
        """
        attempt = 0

        try:
            while True:
                with self._lock:
                    info = self._cameras.get(camera_id)
                    if info is None or info._stop_requested:
                        LOGGER.info("Camera %s lifecycle stopping (stop requested).", camera_id)
                        return

                attempt += 1
                LOGGER.info("Camera %s: connection attempt #%d", camera_id, attempt)

                with self._lock:
                    info = self._cameras[camera_id]
                    info.reconnect_attempt = attempt

                success = self._connect_and_stream(
                    camera_id, camera_url, username, password, media_path, resolution, fps
                )

                with self._lock:
                    info = self._cameras.get(camera_id)
                    if info is None or info._stop_requested:
                        return

                if success:
                    # Connection was established and cleanly ended — reset backoff
                    LOGGER.info("Camera %s stream ended cleanly. Scheduling reconnect.", camera_id)
                    attempt = 0
                    backoff = BACKOFF_STEPS[0]
                else:
                    # Connection failed
                    backoff_idx = min(attempt - 1, len(BACKOFF_STEPS) - 1)
                    backoff = BACKOFF_STEPS[backoff_idx]
                    LOGGER.info(
                        "Camera %s stream failed (attempt %d). Retrying in %ds.",
                        camera_id, attempt, backoff
                    )

                self._set_state(camera_id, StreamState.RECONNECTING, None)

                # Sleep in small intervals so stop_camera() can interrupt
                for _ in range(backoff * 10):
                    time.sleep(0.1)
                    with self._lock:
                        info = self._cameras.get(camera_id)
                        if info is None or info._stop_requested:
                            return
        finally:
            with self._lock:
                info = self._cameras.get(camera_id)
                if info:
                    info._lifecycle_active = False

    def _connect_and_stream(
        self,
        camera_id: str,
        camera_url: str,
        username: str | None,
        password: str | None,
        media_path: str | None,
        resolution: str,
        fps: float,
    ) -> bool:
        """
        Single connection attempt:
        1. Build source URL
        2. Spawn FFmpeg
        3. Monitor FFmpeg process
        Returns True if a stream was established (even if later dropped).
        Returns False if we couldn't start at all.
        """
        # 1. Build authenticated source URL
        try:
            source_url = self._build_source_url(camera_url, username, password)
        except Exception as exc:
            err = f"Invalid source URL: {exc}"
            LOGGER.error("Camera %s: %s", camera_id, err)
            self._set_state(camera_id, StreamState.ERROR, err)
            return False

        # 2. Build destination RTSP publish URL in MediaMTX
        path_name = media_path or camera_id
        pub_user = settings.mediamtx_publish_username
        pub_pass = settings.mediamtx_publish_password
        if pub_user and pub_pass:
            destination_url = (
                f"rtsp://{quote(pub_user, safe='')}:{quote(pub_pass, safe='')}@"
                f"{settings.mediamtx_host}:{settings.mediamtx_rtsp_port}/{path_name}"
            )
        else:
            destination_url = (
                f"rtsp://{settings.mediamtx_host}:{settings.mediamtx_rtsp_port}/{path_name}"
            )

        # 3. Build FFmpeg command
        cmd = self._get_ffmpeg_cmd(source_url, destination_url, resolution, fps)
        log_cmd = self._safe_log_cmd(cmd)
        LOGGER.info("Camera %s: launching FFmpeg -> %s", camera_id, path_name)
        LOGGER.debug("Camera %s FFmpeg cmd: %s", camera_id, " ".join(log_cmd))

        # 4. Spawn FFmpeg process
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            err = f"Failed to launch FFmpeg: {exc}"
            LOGGER.error("Camera %s: %s", camera_id, err)
            self._set_state(camera_id, StreamState.ERROR, err)
            return False

        with self._lock:
            info = self._cameras.get(camera_id)
            if info:
                info.process = proc
                info.started_at = time.monotonic()

        # 5. Start stderr monitor in background thread
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(camera_id, proc),
            daemon=True,
            name=f"stderr-{camera_id}",
        )
        stderr_thread.start()

        # 6. Wait for FFmpeg to either crash immediately or show signs of life
        time.sleep(1.5)
        if proc.poll() is not None:
            code = proc.poll()
            err = self._get_last_stderr_error(camera_id) or f"FFmpeg exited immediately (code {code})"
            LOGGER.error("Camera %s: FFmpeg died immediately: %s", camera_id, err)
            self._set_state(camera_id, StreamState.ERROR, err)
            return False

        # 7. FFmpeg is alive — mark as CONNECTING, wait for MediaMTX to show publisher
        self._set_state(camera_id, StreamState.CONNECTING, None)

        # 8. Poll MediaMTX for publisher arrival (up to PUBLISHER_WAIT_TIMEOUT)
        publisher_detected = self._wait_for_publisher(camera_id, path_name, proc)

        if publisher_detected:
            LOGGER.info(
                "Camera %s: publisher detected in MediaMTX path '%s' → ONLINE",
                camera_id, path_name
            )
            with self._lock:
                info = self._cameras.get(camera_id)
                if info:
                    info.last_connected_at = time.monotonic()
            self._set_state(camera_id, StreamState.ONLINE, None)
        else:
            if proc.poll() is not None:
                err = self._get_last_stderr_error(camera_id) or "FFmpeg exited before publisher was detected"
                LOGGER.warning("Camera %s: FFmpeg exited before publisher confirmed: %s", camera_id, err)
                self._set_state(camera_id, StreamState.ERROR, err)
                return False
            else:
                err = f"No publisher detected in MediaMTX path '{path_name}' after {PUBLISHER_WAIT_TIMEOUT}s"
                LOGGER.warning("Camera %s: %s", camera_id, err)
                self._set_state(camera_id, StreamState.ERROR, err)
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
                return False

        # 9. Monitor until FFmpeg exits
        while True:
            ret = proc.poll()
            if ret is not None:
                with self._lock:
                    info = self._cameras.get(camera_id)
                    if info and info._stop_requested:
                        LOGGER.info("Camera %s FFmpeg exited (stop was requested).", camera_id)
                        return True  # Clean stop

                err = self._get_last_stderr_error(camera_id)
                code_msg = f"FFmpeg exited with code {ret}"
                if err:
                    code_msg += f": {err}"
                LOGGER.warning("Camera %s: %s", camera_id, code_msg)
                self._set_state(camera_id, StreamState.RECONNECTING, code_msg)
                # Return True → lifecycle will reconnect
                return True

            # Check if stop was requested
            with self._lock:
                info = self._cameras.get(camera_id)
                if info and info._stop_requested:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return True

            time.sleep(1.0)

    def _wait_for_publisher(
        self,
        camera_id: str,
        path_name: str,
        proc: subprocess.Popen,
    ) -> bool:
        """
        Polls MediaMTX API until the publisher is detected or timeout.
        Uses a synchronous HTTP check from this thread.
        """
        import httpx

        api_url = settings.mediamtx_api_url.rstrip("/")
        auth = None
        if settings.mediamtx_publish_username and settings.mediamtx_publish_password:
            auth = (settings.mediamtx_publish_username, settings.mediamtx_publish_password)

        deadline = time.monotonic() + PUBLISHER_WAIT_TIMEOUT
        poll_interval = 1.0

        while time.monotonic() < deadline:
            # Check if FFmpeg already died
            if proc.poll() is not None:
                return False

            # Check if stop requested
            with self._lock:
                info = self._cameras.get(camera_id)
                if info and info._stop_requested:
                    return False

            try:
                with httpx.Client(timeout=2.0) as client:
                    # Try direct path query first
                    res = client.get(f"{api_url}/v3/paths/get/{path_name}", auth=auth)
                    if res.status_code == 200:
                        detail = res.json()
                        source_ready = bool(detail.get("sourceReady", detail.get("ready", False)))
                        if source_ready:
                            return True
                    elif res.status_code == 404:
                        # Path not yet registered — FFmpeg hasn't published yet
                        pass
                    else:
                        LOGGER.debug(
                            "Camera %s: MediaMTX path check returned %d",
                            camera_id, res.status_code
                        )
            except Exception as exc:
                LOGGER.debug("Camera %s: publisher poll error: %s", camera_id, exc)

            time.sleep(poll_interval)

        return False

    def _read_stderr(self, camera_id: str, proc: subprocess.Popen) -> None:
        """Reads FFmpeg stderr in background and stores last error."""
        try:
            if proc.stderr:
                for line in proc.stderr:
                    clean = line.strip()
                    if not clean:
                        continue
                    lower = clean.lower()
                    if any(kw in lower for kw in ("error", "fatal", "failed", "invalid", "refused", "timeout")):
                        LOGGER.warning("[FFmpeg:%s] %s", camera_id, clean)
                        with self._lock:
                            info = self._cameras.get(camera_id)
                            if info:
                                info.last_error = clean
                    else:
                        LOGGER.debug("[FFmpeg:%s] %s", camera_id, clean)
        except Exception as exc:
            LOGGER.debug("Camera %s stderr reader exited: %s", camera_id, exc)

    def _get_last_stderr_error(self, camera_id: str) -> str | None:
        with self._lock:
            info = self._cameras.get(camera_id)
            return info.last_error if info else None

    def _set_state(self, camera_id: str, state: StreamState, error: str | None) -> None:
        with self._lock:
            info = self._cameras.get(camera_id)
            if info:
                info.state = state
                if error:
                    info.last_error = error
        self._notify_status(camera_id, state, error)

    def _notify_status(self, camera_id: str, state: StreamState, error: str | None) -> None:
        for cb in self._status_callbacks:
            try:
                cb(camera_id, state, error)
            except Exception as exc:
                LOGGER.debug("Status callback error for camera %s: %s", camera_id, exc)

    # ── URL & Command Helpers ─────────────────────────────────────────────────

    def _build_source_url(
        self,
        camera_url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Builds a sanitized and properly authenticated camera source URL."""
        if not camera_url:
            raise ValueError("Camera URL is empty")

        if "://" in camera_url:
            source_url = camera_url.strip()
        else:
            source_url = f"http://{camera_url.strip()}"

        if username and password:
            parsed = urlsplit(source_url)
            encoded_username = quote(username, safe="")
            encoded_password = quote(password, safe="")

            hostname = parsed.hostname
            if not hostname:
                raise ValueError(f"Invalid camera URL: {camera_url}")

            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"

            host_part = f"{hostname}:{parsed.port}" if parsed.port else hostname
            netloc = f"{encoded_username}:{encoded_password}@{host_part}"
            source_url = urlunsplit((
                parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment,
            ))

        return source_url

    def _get_ffmpeg_cmd(
        self,
        source_url: str,
        destination_url: str,
        resolution: str = "1280x720",
        fps: float = 15.0,
    ) -> list[str]:
        """Constructs FFmpeg command line arguments based on configured encoder."""
        ffmpeg_bin = shutil.which(settings.ffmpeg_binary) or "ffmpeg"
        encoder = settings.ffmpeg_encoder.lower().strip()

        try:
            w, h = resolution.split("x")
            scale_filter = f"scale={int(w)}:{int(h)}"
        except Exception:
            scale_filter = "scale=1280:720"

        fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.2f}"
        gop_str = str(int(fps))

        cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "warning"]

        if source_url.lower().startswith("rtsp://"):
            cmd.extend([
                "-rtsp_transport", "tcp",
                "-timeout", "5000000",   # 5s RTSP socket I/O timeout in microseconds
            ])
        elif source_url.lower().startswith(("http://", "https://")):
            cmd.extend([
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
            ])

        cmd.extend(["-i", source_url])

        if encoder == "copy":
            cmd.extend(["-c:v", "copy"])
        elif encoder == "h264_amf":
            cmd.extend([
                "-vf", scale_filter, "-r", fps_str,
                "-c:v", "h264_amf", "-usage", "ultralowlatency",
                "-rc", "cbr", "-b:v", settings.stream_bitrate,
                "-maxrate", settings.stream_bitrate, "-bufsize", "500K", "-g", gop_str,
            ])
        elif encoder == "h264_nvenc":
            cmd.extend([
                "-vf", scale_filter, "-r", fps_str,
                "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ull",
                "-b:v", settings.stream_bitrate, "-g", gop_str,
            ])
        else:
            # Default: CPU libx264 (works everywhere)
            cmd.extend([
                "-vf", scale_filter, "-r", fps_str,
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-b:v", settings.stream_bitrate,
                "-maxrate", settings.stream_bitrate, "-bufsize", "500K", "-g", gop_str,
            ])

        # Video-only RTSP publish to MediaMTX
        cmd.extend(["-an", "-f", "rtsp", "-rtsp_transport", "tcp", destination_url])
        return cmd

    def _safe_log_cmd(self, cmd: list[str]) -> list[str]:
        """Redacts passwords from command list for safe logging."""
        safe = []
        skip_next = False
        for token in cmd:
            if skip_next:
                safe.append("***")
                skip_next = False
            elif "://" in token and "@" in token:
                # Redact credentials embedded in URL
                parsed = urlsplit(token)
                safe.append(urlunsplit((
                    parsed.scheme, f"***:***@{parsed.hostname}:{parsed.port}",
                    parsed.path, parsed.query, parsed.fragment
                )))
            else:
                safe.append(token)
        return safe


stream_manager = StreamManager()
