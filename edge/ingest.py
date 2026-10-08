#!/usr/bin/env python3
"""
Low-latency camera ingest worker.

Pipeline: Camera RTSP -> FFmpeg (H.264 copy) -> MediaMTX -> browser playback.

One ingest.py process = one camera = one FFmpeg process.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit

try:
    import fcntl
except ImportError:
    fcntl = None

if os.name == "nt":
    import msvcrt

try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)
except ImportError:
    pass

FFMPEG_BIN = "ffmpeg"
CAMERA_ID = ""
SOURCE_URL = ""
MEDIA_PATH = ""
MEDIAMTX_HOST = "127.0.0.1"
MEDIAMTX_RTSP_PORT = 8554
PUBLISH_USERNAME = "edge_publisher"
PUBLISH_PASSWORD = ""
RECONNECT_INITIAL_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
STABLE_CONNECTION_SECONDS = 10.0
LOG_LEVEL = "INFO"
_DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "debug-abbe6f.log"
PUBLISH_TCP_TIMEOUT = 5.0

EDGE_DIR = Path(__file__).resolve().parent
CAMERA_KEY = hashlib.sha256(CAMERA_ID.encode("utf-8")).hexdigest()[:16] if CAMERA_ID else "unknown"
CAMERA_LOCK_PATH = EDGE_DIR / f".ingest-{CAMERA_KEY}.lock"
FFMPEG_PID_PATH = EDGE_DIR / f".ffmpeg-{CAMERA_KEY}.pid"

STOP_EVENT = threading.Event()
PROCESS_LOCK = threading.Lock()
CURRENT_PROCESS: Optional[subprocess.Popen] = None

logger = logging.getLogger("camera-ingest")

MEDIA_PATH_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


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


def load_runtime_config() -> None:
    """Load configuration from environment variables and optional CLI overrides."""
    global FFMPEG_BIN, CAMERA_ID, SOURCE_URL, MEDIA_PATH, MEDIAMTX_HOST
    global MEDIAMTX_RTSP_PORT, PUBLISH_USERNAME, PUBLISH_PASSWORD
    global RECONNECT_INITIAL_DELAY, RECONNECT_MAX_DELAY, STABLE_CONNECTION_SECONDS
    global LOG_LEVEL, PUBLISH_TCP_TIMEOUT

    FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg").strip()
    CAMERA_ID = os.getenv("EDGE_CAMERA_ID", "").strip()
    SOURCE_URL = os.getenv("EDGE_SOURCE_URL", "").strip()
    MEDIA_PATH = os.getenv("EDGE_MEDIA_PATH", "").strip()
    MEDIAMTX_HOST = os.getenv("MEDIAMTX_HOST", "127.0.0.1").strip()
    MEDIAMTX_RTSP_PORT = int(os.getenv("MEDIAMTX_RTSP_PORT", "8554"))
    PUBLISH_USERNAME = os.getenv("MEDIAMTX_PUBLISH_USERNAME", "edge_publisher").strip()
    PUBLISH_PASSWORD = os.getenv("MEDIAMTX_PUBLISH_PASSWORD", "").strip()
    RECONNECT_INITIAL_DELAY = float(os.getenv("RECONNECT_INITIAL_DELAY", "1"))
    RECONNECT_MAX_DELAY = float(os.getenv("RECONNECT_MAX_DELAY", "30"))
    STABLE_CONNECTION_SECONDS = float(os.getenv("STABLE_CONNECTION_SECONDS", "10"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    PUBLISH_TCP_TIMEOUT = float(os.getenv("PUBLISH_TCP_TIMEOUT", "5"))

    if len(sys.argv) > 1:
        SOURCE_URL = sys.argv[1].strip()
    if len(sys.argv) > 2:
        MEDIA_PATH = sys.argv[2].strip()
    if len(sys.argv) > 3:
        MEDIAMTX_HOST = sys.argv[3].strip()
    if not CAMERA_ID:
        CAMERA_ID = MEDIA_PATH.lstrip("/") or "edge_cam"

    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s | %(levelname)s | ingest | %(message)s",
        force=True,
    )


def check_publish_endpoint_reachable() -> tuple[bool, str]:
    """Verify TCP connectivity to the central MediaMTX RTSP publish port."""
    try:
        with socket.create_connection(
            (MEDIAMTX_HOST, MEDIAMTX_RTSP_PORT),
            timeout=PUBLISH_TCP_TIMEOUT,
        ):
            return True, "ok"
    except OSError as exc:
        return False, str(exc)


def validate_media_path(media_path: str) -> str:
    if not media_path or not MEDIA_PATH_REGEX.match(media_path):
        raise ValueError(
            f"Invalid media_path '{media_path}'. Must match ^[a-zA-Z0-9_-]+$."
        )
    return media_path


def redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.username is None:
            return url
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
        return urlunsplit(
            (parsed.scheme, f"{quote(parsed.username)}:***@{hostname}", parsed.path, parsed.query, parsed.fragment)
        )
    except Exception:
        return "<redacted-url>"


def normalize_rtsp_source_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username is None:
        return url

    username = parsed.username or ""
    password = parsed.password or ""
    for _ in range(3):
        decoded_username = unquote(username)
        decoded_password = unquote(password)
        if decoded_username == username and decoded_password == password:
            break
        username = decoded_username
        password = decoded_password

    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"

    return urlunsplit(
        (
            parsed.scheme,
            f"{quote(username, safe='')}:{quote(password, safe='')}@{hostname}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def build_publish_url() -> str:
    clean_path = validate_media_path(MEDIA_PATH.lstrip("/"))
    user_enc = quote(PUBLISH_USERNAME, safe="")
    pass_enc = quote(PUBLISH_PASSWORD, safe="")
    return f"rtsp://{user_enc}:{pass_enc}@{MEDIAMTX_HOST}:{MEDIAMTX_RTSP_PORT}/{clean_path}"


def build_ffmpeg_command(source_url: str, publish_url: str) -> list[str]:
    # IMPORTANT: Never add -use_wallclock_as_timestamps 1 — it breaks PTS and
    # causes false "low FPS" symptoms. WAN throughput issues are network-layer.
    return [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostdin",
        "-rtsp_transport", "tcp",
        "-fflags", "+genpts",
        "-analyzeduration", "500000",
        "-probesize", "500000",
        "-i", source_url,
        "-map", "0:v:0",
        "-c:v", "copy",
        "-an",
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        "-muxdelay", "0",
        "-flush_packets", "1",
        publish_url,
    ]


class CameraIngestLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
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
                if fcntl is None:
                    raise RuntimeError("fcntl is unavailable on this platform")
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError) as exc:
            try:
                self.handle.close()
            except Exception:
                pass
            self.handle = None
            if getattr(exc, "errno", None) in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                return False
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
            try:
                self.handle.close()
            except Exception:
                pass
            self.handle = None


def _read_pid_file() -> Optional[int]:
    try:
        return int(FFMPEG_PID_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _is_ffmpeg_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return "ffmpeg.exe" in result.stdout.lower()
        except OSError:
            return False
    try:
        return "ffmpeg" in Path(f"/proc/{pid}/cmdline").read_text(errors="ignore").lower()
    except OSError:
        return False


def cleanup_stale_ffmpeg() -> None:
    pid = _read_pid_file()
    if pid is None:
        return
    if _is_ffmpeg_pid(pid):
        logger.warning("Found stale FFmpeg process | camera=%s | pid=%s", CAMERA_ID, pid)
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    try:
        FFMPEG_PID_PATH.unlink()
    except FileNotFoundError:
        pass


def write_ffmpeg_pid(pid: int) -> None:
    FFMPEG_PID_PATH.write_text(str(pid), encoding="utf-8")


def clear_ffmpeg_pid(pid: int) -> None:
    try:
        if _read_pid_file() == pid:
            FFMPEG_PID_PATH.unlink()
    except FileNotFoundError:
        pass


def drain_stderr(process: subprocess.Popen) -> None:
    if process.stderr is None:
        return
    try:
        for raw_line in iter(process.stderr.readline, b""):
            if STOP_EVENT.is_set():
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                logger.warning("FFmpeg[%s] %s", CAMERA_ID, line)
    except Exception as exc:
        logger.debug("FFmpeg stderr reader stopped: %s", exc)
    finally:
        try:
            process.stderr.close()
        except Exception:
            pass


def terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        clear_ffmpeg_pid(process.pid)
        return
    logger.info("Stopping FFmpeg | camera=%s | pid=%s", CAMERA_ID, process.pid)
    try:
        process.terminate()
    except Exception as exc:
        logger.debug("FFmpeg terminate failed: %s", exc)
    try:
        process.wait(timeout=5)
        clear_ffmpeg_pid(process.pid)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
        process.wait(timeout=3)
    except Exception as exc:
        logger.error("Failed to kill FFmpeg: %s", exc)
    clear_ffmpeg_pid(process.pid)


def start_ffmpeg() -> subprocess.Popen:
    publish_url = build_publish_url()
    source_url = normalize_rtsp_source_url(SOURCE_URL)
    command = build_ffmpeg_command(source_url, publish_url)

    _debug_log(
        "H6",
        "ingest.py:start_ffmpeg",
        "starting ffmpeg publish",
        {
            "camera_id": CAMERA_ID,
            "media_path": MEDIA_PATH,
            "mediamtx_host": MEDIAMTX_HOST,
            "mediamtx_port": MEDIAMTX_RTSP_PORT,
        },
    )

    logger.info("Starting FFmpeg | camera=%s", CAMERA_ID)
    logger.info("Source=%s", redact_url(source_url))
    logger.info("Destination=rtsp://%s:%s/%s", MEDIAMTX_HOST, MEDIAMTX_RTSP_PORT, MEDIA_PATH.lstrip("/"))

    process_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        process_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(command, **process_kwargs)
    write_ffmpeg_pid(process.pid)

    global CURRENT_PROCESS
    with PROCESS_LOCK:
        CURRENT_PROCESS = process

    threading.Thread(
        target=drain_stderr,
        args=(process,),
        name=f"ffmpeg-stderr-{CAMERA_ID}",
        daemon=True,
    ).start()

    logger.info("FFmpeg started | camera=%s | pid=%s", CAMERA_ID, process.pid)
    return process


def run_worker() -> None:
    delay = RECONNECT_INITIAL_DELAY
    while not STOP_EVENT.is_set():
        reachable, reason = check_publish_endpoint_reachable()
        _debug_log(
            "H6",
            "ingest.py:run_worker",
            "publish endpoint tcp check",
            {
                "camera_id": CAMERA_ID,
                "host": MEDIAMTX_HOST,
                "port": MEDIAMTX_RTSP_PORT,
                "reachable": reachable,
                "reason": reason[:200] if reason else "",
            },
        )
        if not reachable:
            logger.error(
                "MediaMTX publish endpoint unreachable at %s:%s (%s). "
                "Check AWS Security Group allows TCP %s from this edge machine public IP.",
                MEDIAMTX_HOST,
                MEDIAMTX_RTSP_PORT,
                reason,
                MEDIAMTX_RTSP_PORT,
            )
            STOP_EVENT.wait(min(delay, RECONNECT_MAX_DELAY))
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
            continue

        process: Optional[subprocess.Popen] = None
        started_at = time.monotonic()
        try:
            process = start_ffmpeg()
            return_code = process.wait()
            runtime = time.monotonic() - started_at
            if STOP_EVENT.is_set():
                break
            logger.warning(
                "FFmpeg exited | camera=%s | return_code=%s | runtime=%.1fs",
                CAMERA_ID,
                return_code,
                runtime,
            )
            _debug_log(
                "H6",
                "ingest.py:run_worker",
                "ffmpeg exited",
                {"camera_id": CAMERA_ID, "return_code": return_code, "runtime": round(runtime, 1)},
            )
            delay = RECONNECT_INITIAL_DELAY if runtime >= STABLE_CONNECTION_SECONDS else min(delay * 2, RECONNECT_MAX_DELAY)
        except FileNotFoundError:
            logger.error("FFmpeg executable not found: %s", FFMPEG_BIN)
            break
        except Exception:
            logger.exception("Unexpected ingest error | camera=%s", CAMERA_ID)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        finally:
            if process is not None:
                terminate_process(process)
            with PROCESS_LOCK:
                CURRENT_PROCESS = None

        if STOP_EVENT.is_set():
            break
        logger.info("Reconnect scheduled | camera=%s | delay=%.1fs", CAMERA_ID, delay)
        STOP_EVENT.wait(delay)


def validate_config() -> None:
    missing = [
        name
        for name, value in {
            "EDGE_SOURCE_URL": SOURCE_URL,
            "EDGE_MEDIA_PATH": MEDIA_PATH,
            "MEDIAMTX_HOST": MEDIAMTX_HOST,
            "MEDIAMTX_PUBLISH_PASSWORD": PUBLISH_PASSWORD,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing required configuration: " + ", ".join(missing))
    validate_media_path(MEDIA_PATH.lstrip("/"))


def request_shutdown(signum: int, _frame) -> None:
    logger.info("Shutdown signal received | signal=%s | camera=%s", signum, CAMERA_ID)
    STOP_EVENT.set()
    with PROCESS_LOCK:
        process = CURRENT_PROCESS
    if process is not None:
        terminate_process(process)


def main() -> int:
    load_runtime_config()
    try:
        validate_config()
    except Exception as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    reachable, reason = check_publish_endpoint_reachable()
    _debug_log(
        "H6",
        "ingest.py:main",
        "startup publish endpoint tcp check",
        {
            "camera_id": CAMERA_ID,
            "host": MEDIAMTX_HOST,
            "port": MEDIAMTX_RTSP_PORT,
            "reachable": reachable,
            "reason": reason[:200] if reason else "",
        },
    )
    if not reachable:
        logger.error(
            "Cannot reach MediaMTX publish endpoint %s:%s (%s)",
            MEDIAMTX_HOST,
            MEDIAMTX_RTSP_PORT,
            reason,
        )

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    ingest_lock = CameraIngestLock(CAMERA_LOCK_PATH)
    if not ingest_lock.acquire():
        logger.error("Another ingest worker is already running for camera=%s", CAMERA_ID)
        return 1

    try:
        cleanup_stale_ffmpeg()
        run_worker()
    except KeyboardInterrupt:
        STOP_EVENT.set()
    finally:
        with PROCESS_LOCK:
            process = CURRENT_PROCESS
        if process is not None:
            terminate_process(process)
        ingest_lock.release()

    return 0


if __name__ == "__main__":
    sys.exit(main())
