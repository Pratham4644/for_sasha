"""
Edge Ingest Gateway - Remote Camera Ingestion
Runs at remote customer sites to ingest private camera RTSP streams
and publish them securely to the central MediaMTX streaming server.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from urllib.parse import quote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EdgeIngest] %(message)s",
)
LOGGER = logging.getLogger("edge_ingest")


def sanitize_url_for_logging(url: str) -> str:
    """Masks passwords in RTSP URLs for secure logging."""
    if "@" not in url or "://" not in url:
        return url
    prefix, rest = url.split("://", 1)
    creds, host_path = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{prefix}://{user}:***@{host_path}"
    return f"{prefix}://***@{host_path}"


def run_ingest(
    source_url: str,
    publish_url: str,
    camera_id: str = "edge_cam",
) -> None:
    """Supervises FFmpeg process with bounded exponential backoff."""
    backoff = 2.0
    max_backoff = 30.0

    LOGGER.info("Starting ingest for camera %s", camera_id)
    LOGGER.info("Source: %s", sanitize_url_for_logging(source_url))
    LOGGER.info("Publish: %s", sanitize_url_for_logging(publish_url))

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "warning",
        "-rtsp_transport", "tcp",
        "-i", source_url,
        "-c:v", "copy",
        "-an",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        publish_url,
    ]

    while True:
        start_time = time.time()
        LOGGER.info("Spawning FFmpeg process...")
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            duration = time.time() - start_time
            LOGGER.warning("FFmpeg process exited with code %s after %.1fs", proc.returncode, duration)

            # Reset backoff if streamed successfully for more than 60s
            if duration > 60:
                backoff = 2.0
            else:
                backoff = min(backoff * 2, max_backoff)

        except KeyboardInterrupt:
            LOGGER.info("Shutting down edge ingest on interrupt...")
            break
        except Exception as exc:
            LOGGER.error("Failed to run FFmpeg: %s", exc)
            backoff = min(backoff * 2, max_backoff)

        LOGGER.info("Reconnecting in %.1fs...", backoff)
        time.sleep(backoff)


if __name__ == "__main__":
    src = os.getenv("EDGE_SOURCE_URL")
    media_path = os.getenv("EDGE_MEDIA_PATH", "edge_camera")
    host = os.getenv("MEDIAMTX_HOST", "127.0.0.1")
    port = os.getenv("MEDIAMTX_RTSP_PORT", "8554")
    user = os.getenv("MEDIAMTX_PUBLISH_USERNAME", "edge_publisher")
    pwd = os.getenv("MEDIAMTX_PUBLISH_PASSWORD", "dev_mediamtx_pub_pwd_secure")

    if not src:
        if len(sys.argv) > 1:
            src = sys.argv[1]
        else:
            print("Usage: python ingest.py <rtsp_source_url> [media_path] [mediamtx_host]")
            sys.exit(1)

    if len(sys.argv) > 2:
        media_path = sys.argv[2]
    if len(sys.argv) > 3:
        host = sys.argv[3]

    encoded_user = quote(user, safe="")
    encoded_pwd = quote(pwd, safe="")
    target_url = f"rtsp://{encoded_user}:{encoded_pwd}@{host}:{port}/{media_path}"

    run_ingest(src, target_url, media_path)
