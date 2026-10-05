from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.stream_manager")


class StreamManager:
    """
    Generalized stream supervisor managing independent FFmpeg ingestion processes.
    Proven FFmpeg RTSP streaming implementation adapted from friend-system.
    """

    def __init__(self) -> None:
        # camera_id -> subprocess.Popen
        self.processes: dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()
        self._last_errors: dict[str, str] = {}

    def _build_source_url(
        self,
        camera_url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """
        Builds a sanitized and properly authenticated camera source URL.
        Supports RTSP, HTTP, HTTPS protocols.
        """
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

            if parsed.port:
                host_part = f"{hostname}:{parsed.port}"
            else:
                host_part = hostname

            netloc = f"{encoded_username}:{encoded_password}@{host_part}"
            source_url = urlunsplit((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
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

        # Parse width and height
        try:
            w, h = resolution.split("x")
            scale_filter = f"scale={int(w)}:{int(h)}"
        except Exception:
            scale_filter = "scale=1280:720"

        fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.2f}"
        gop_str = str(int(fps))

        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "warning",
        ]

        if source_url.lower().startswith("rtsp://"):
            cmd.extend(["-rtsp_transport", "tcp"])
        elif source_url.lower().startswith("http://") or source_url.lower().startswith("https://"):
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
            # AMD hardware encoder
            cmd.extend([
                "-vf", scale_filter,
                "-r", fps_str,
                "-c:v", "h264_amf",
                "-usage", "ultralowlatency",
                "-rc", "cbr",
                "-b:v", settings.stream_bitrate,
                "-maxrate", settings.stream_bitrate,
                "-bufsize", "500K",
                "-g", gop_str,
            ])
        elif encoder == "h264_nvenc":
            # NVIDIA hardware encoder
            cmd.extend([
                "-vf", scale_filter,
                "-r", fps_str,
                "-c:v", "h264_nvenc",
                "-preset", "p1",
                "-tune", "ull",
                "-b:v", settings.stream_bitrate,
                "-g", gop_str,
            ])
        else:
            # Universal CPU H.264 encoder (default, works on any platform)
            cmd.extend([
                "-vf", scale_filter,
                "-r", fps_str,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-pix_fmt", "yuv420p",
                "-b:v", settings.stream_bitrate,
                "-maxrate", settings.stream_bitrate,
                "-bufsize", "500K",
                "-g", gop_str,
            ])

        # CCTV stream: video only, publish RTSP over TCP to MediaMTX
        cmd.extend([
            "-an",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            destination_url,
        ])
        return cmd

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
        """Starts an independent FFmpeg relay subprocess for a given camera."""
        with self.lock:
            # 1. Check if process is already running
            existing = self.processes.get(camera_id)
            if existing is not None:
                if existing.poll() is None:
                    LOGGER.info("Camera %s is already streaming (PID %d)", camera_id, existing.pid)
                    return True
                # Clean up finished/stale process
                del self.processes[camera_id]

            # 2. Build source URL
            try:
                source_url = self._build_source_url(camera_url, username, password)
            except Exception as err:
                LOGGER.error("Invalid source URL for camera %s: %s", camera_id, err)
                self._last_errors[camera_id] = str(err)
                return False

            # 3. Build destination URL in MediaMTX
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

            # 4. Construct command
            cmd = self._get_ffmpeg_cmd(source_url, destination_url, resolution, fps)
            LOGGER.info("Starting FFmpeg for camera '%s' -> %s", camera_id, path_name)

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
                LOGGER.error("Failed to launch FFmpeg for camera %s: %s", camera_id, exc)
                self._last_errors[camera_id] = str(exc)
                return False

            self.processes[camera_id] = proc

            # 5. Launch monitor thread
            thread = threading.Thread(
                target=self._monitor_process,
                args=(camera_id, proc),
                daemon=True,
                name=f"ffmpeg-monitor-{camera_id}",
            )
            thread.start()
            return True

    def _monitor_process(self, camera_id: str, proc: subprocess.Popen) -> None:
        """Monitors process stderr, logs output, and cleans up dictionary on exit."""
        try:
            if proc.stderr:
                for line in proc.stderr:
                    clean_line = line.strip()
                    if clean_line:
                        LOGGER.debug("[FFmpeg:%s] %s", camera_id, clean_line)
                        if "error" in clean_line.lower() or "fatal" in clean_line.lower():
                            self._last_errors[camera_id] = clean_line
        except Exception as exc:
            LOGGER.debug("Error reading FFmpeg stderr for %s: %s", camera_id, exc)
        finally:
            code = proc.poll()
            LOGGER.info("FFmpeg process for camera %s exited with return code %s", camera_id, code)
            with self.lock:
                if self.processes.get(camera_id) == proc:
                    del self.processes[camera_id]

    def stop_camera(self, camera_id: str) -> bool:
        """Stops the FFmpeg process for the specified camera."""
        with self.lock:
            proc = self.processes.get(camera_id)
            if proc is None:
                LOGGER.info("Camera %s is not actively streaming.", camera_id)
                return False

            if proc.poll() is None:
                LOGGER.info("Terminating FFmpeg process for camera %s (PID %d)", camera_id, proc.pid)
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("FFmpeg for camera %s did not terminate, sending KILL signal", camera_id)
                    proc.kill()
                except Exception as exc:
                    LOGGER.error("Error stopping camera %s: %s", camera_id, exc)
                    return False

            del self.processes[camera_id]
            return True

    def restart_camera(self, *args, **kwargs) -> bool:
        """Restarts a camera stream cleanly."""
        camera_id = kwargs.get("camera_id") or (args[0] if args else None)
        if camera_id:
            self.stop_camera(camera_id)
        return self.start_camera(*args, **kwargs)

    def is_running(self, camera_id: str) -> bool:
        """Checks if FFmpeg process is running for the given camera."""
        with self.lock:
            proc = self.processes.get(camera_id)
            if proc is None:
                return False
            return proc.poll() is None

    def get_running_cameras(self) -> list[str]:
        """Returns list of all camera IDs currently streaming."""
        with self.lock:
            return [cam_id for cam_id, p in self.processes.items() if p.poll() is None]

    def get_last_error(self, camera_id: str) -> str | None:
        return self._last_errors.get(camera_id)

    def stop_all(self) -> None:
        """Stops all running camera FFmpeg processes."""
        with self.lock:
            cams = list(self.processes.keys())
        for cam in cams:
            self.stop_camera(cam)
        LOGGER.info("All camera streams stopped.")


stream_manager = StreamManager()
