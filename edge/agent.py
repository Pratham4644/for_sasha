#!/usr/bin/env python3
"""
Edge Gateway Agent

Polls the central backend for assigned remote-edge cameras and supervises one
ingest.py worker per camera.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None

if os.name == "nt":
    import msvcrt

import requests
from dotenv import load_dotenv

load_dotenv()

EDGE_DIR = Path(__file__).resolve().parent
INGEST_SCRIPT = EDGE_DIR / "ingest.py"
_DEBUG_LOG_PATH = EDGE_DIR.parent / "debug-abbe6f.log"

EDGE_API_URL = os.getenv(
    "EDGE_API_URL",
    "https://localhost/api/v1/edge/config",
).strip()
EDGE_GATEWAY_TOKEN = os.getenv("EDGE_GATEWAY_TOKEN", "").strip()
MEDIAMTX_HOST = os.getenv("MEDIAMTX_HOST", "").strip()
MEDIAMTX_RTSP_PORT = os.getenv("MEDIAMTX_RTSP_PORT", "8554").strip()
MEDIAMTX_PUBLISH_USERNAME = os.getenv("MEDIAMTX_PUBLISH_USERNAME", "edge_publisher").strip()
MEDIAMTX_PUBLISH_PASSWORD = os.getenv("MEDIAMTX_PUBLISH_PASSWORD", "").strip()
POLL_INTERVAL = int(os.getenv("EDGE_POLL_INTERVAL", "10"))
HTTP_TIMEOUT = int(os.getenv("EDGE_HTTP_TIMEOUT", "15"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | edge-agent | %(message)s",
)
LOGGER = logging.getLogger("edge-agent")

if not INGEST_SCRIPT.exists():
    raise RuntimeError(f"ingest.py not found at {INGEST_SCRIPT}")
if not EDGE_GATEWAY_TOKEN:
    raise RuntimeError("EDGE_GATEWAY_TOKEN is not configured.")
if not MEDIAMTX_PUBLISH_PASSWORD:
    raise RuntimeError("MEDIAMTX_PUBLISH_PASSWORD is not configured.")


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
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass
    # endregion


def check_tcp_reachable(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, "ok"
    except OSError as exc:
        return False, str(exc)


def camera_fingerprint(camera: dict[str, Any]) -> str:
    runtime_config = {
        "source_url": camera.get("source_url"),
        "media_path": camera.get("media_path"),
    }
    payload = json.dumps(runtime_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+")
        try:
            self.handle.seek(0)
            if os.name == "nt":
                self.handle.write("0")
                self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self.handle.close()
            self.handle = None
            if getattr(exc, "errno", None) in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                raise RuntimeError("Another edge-agent instance is already running.") from exc
            raise

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.handle.close()
            self.handle = None


AGENT_LOCK = SingleInstanceLock(EDGE_DIR / ".edge-agent.lock")


def terminate_process_tree(process: subprocess.Popen, timeout: float = 12.0) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            process.wait(timeout=3)
            return
        except (subprocess.TimeoutExpired, OSError):
            pass
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass


class CameraWorker:
    def __init__(self, camera: dict[str, Any], mediamtx_host: str, mediamtx_port: str):
        self.camera = camera
        self.mediamtx_host = mediamtx_host
        self.mediamtx_port = mediamtx_port
        self.process: subprocess.Popen | None = None

    @property
    def camera_id(self) -> str:
        return self.camera["camera_id"]

    @property
    def media_path(self) -> str:
        return self.camera["media_path"]

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if self.is_running():
            return

        env = os.environ.copy()
        env["EDGE_CAMERA_ID"] = self.camera_id
        env["EDGE_SOURCE_URL"] = self.camera["source_url"]
        env["EDGE_MEDIA_PATH"] = self.media_path
        env["MEDIAMTX_HOST"] = self.mediamtx_host
        env["MEDIAMTX_RTSP_PORT"] = self.mediamtx_port
        env["MEDIAMTX_PUBLISH_USERNAME"] = MEDIAMTX_PUBLISH_USERNAME
        env["MEDIAMTX_PUBLISH_PASSWORD"] = MEDIAMTX_PUBLISH_PASSWORD

        self.process = subprocess.Popen(
            [sys.executable, str(INGEST_SCRIPT)],
            env=env,
            stdin=subprocess.DEVNULL,
        )
        LOGGER.info(
            "Camera worker started: %s | PID=%s | path=%s | host=%s",
            self.camera_id,
            self.process.pid,
            self.media_path,
            self.mediamtx_host,
        )

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            LOGGER.info("Stopping camera worker: %s", self.camera_id)
            terminate_process_tree(self.process)
        self.process = None

    def update_camera(self, camera: dict[str, Any], mediamtx_host: str, mediamtx_port: str) -> None:
        self.camera = camera
        self.mediamtx_host = mediamtx_host
        self.mediamtx_port = mediamtx_port


class EdgeAgent:
    def __init__(self) -> None:
        self.workers: dict[str, dict[str, Any]] = {}
        self.running = True
        self.mediamtx_host = MEDIAMTX_HOST
        self.mediamtx_port = MEDIAMTX_RTSP_PORT

    def fetch_config(self) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {EDGE_GATEWAY_TOKEN}",
            "Accept": "application/json",
        }
        response = requests.get(EDGE_API_URL, headers=headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def reconcile(self, cameras: list[dict[str, Any]]) -> None:
        desired: dict[str, dict[str, Any]] = {}
        for camera in cameras:
            camera_id = camera.get("camera_id")
            if not camera_id or not camera.get("media_path") or not camera.get("source_url"):
                continue
            desired[camera_id] = camera

        for camera_id, camera in desired.items():
            desired_fingerprint = camera_fingerprint(camera)
            existing = self.workers.get(camera_id)

            if existing is None:
                worker = CameraWorker(camera, self.mediamtx_host, self.mediamtx_port)
                worker.start()
                self.workers[camera_id] = {"worker": worker, "fingerprint": desired_fingerprint}
                continue

            worker: CameraWorker = existing["worker"]
            if existing["fingerprint"] != desired_fingerprint:
                LOGGER.info("Runtime configuration changed: %s", camera_id)
                worker.stop()
                worker = CameraWorker(camera, self.mediamtx_host, self.mediamtx_port)
                worker.start()
                self.workers[camera_id] = {"worker": worker, "fingerprint": desired_fingerprint}
                continue

            worker.update_camera(camera, self.mediamtx_host, self.mediamtx_port)
            if not worker.is_running():
                LOGGER.warning("Camera worker stopped unexpectedly: %s", camera_id)
                worker.start()

        removed = set(self.workers.keys()) - set(desired.keys())
        for camera_id in removed:
            LOGGER.info("Camera no longer assigned. Stopping worker: %s", camera_id)
            entry = self.workers.pop(camera_id)
            entry["worker"].stop()

    def shutdown(self) -> None:
        if not self.running:
            return
        LOGGER.info("Shutting down Edge Gateway...")
        self.running = False
        for camera_id, entry in list(self.workers.items()):
            LOGGER.info("Stopping camera: %s", camera_id)
            entry["worker"].stop()
        self.workers.clear()
        LOGGER.info("Edge Gateway stopped.")

    def run(self) -> None:
        LOGGER.info("Edge Gateway Agent starting")
        LOGGER.info("API: %s", EDGE_API_URL)
        LOGGER.info("Poll interval: %ss", POLL_INTERVAL)

        while self.running:
            try:
                config = self.fetch_config()
                publish_host = config.get("mediamtx_publish_host") or self.mediamtx_host
                publish_port = str(config.get("mediamtx_rtsp_port") or self.mediamtx_port)
                if publish_host:
                    self.mediamtx_host = publish_host
                if publish_port:
                    self.mediamtx_port = publish_port

                reachable, reason = check_tcp_reachable(self.mediamtx_host, int(self.mediamtx_port))
                _debug_log(
                    "H6",
                    "agent.py:run",
                    "publish endpoint tcp check",
                    {
                        "host": self.mediamtx_host,
                        "port": self.mediamtx_port,
                        "reachable": reachable,
                        "reason": reason[:200] if reason else "",
                    },
                )
                if not reachable:
                    LOGGER.error(
                        "MediaMTX publish endpoint unreachable at %s:%s (%s). "
                        "Allow inbound TCP %s from this edge machine on AWS Security Group.",
                        self.mediamtx_host,
                        self.mediamtx_port,
                        reason,
                        self.mediamtx_port,
                    )

                cameras = config.get("cameras", [])
                _debug_log(
                    "H5",
                    "agent.py:run",
                    "edge config polled",
                    {
                        "camera_count": len(cameras),
                        "publish_host": self.mediamtx_host,
                        "publish_port": self.mediamtx_port,
                    },
                )
                LOGGER.info("Received %d assigned camera(s)", len(cameras))
                self.reconcile(cameras)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else "unknown"
                LOGGER.error("Edge API HTTP error: %s", status_code)
                _debug_log("H4", "agent.py:run", "edge api http error", {"status_code": status_code})
            except requests.RequestException as exc:
                LOGGER.error("Edge API connection error: %s", exc)
                _debug_log("H4", "agent.py:run", "edge api connection error", {"error": str(exc)[:200]})
            except Exception:
                LOGGER.exception("Unexpected Edge Agent error")

            time.sleep(POLL_INTERVAL)


agent = EdgeAgent()


def handle_shutdown(_signum, _frame) -> None:
    LOGGER.info("Shutdown signal received.")
    agent.shutdown()


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


if __name__ == "__main__":
    AGENT_LOCK.acquire()
    try:
        agent.run()
    finally:
        agent.shutdown()
        AGENT_LOCK.release()
