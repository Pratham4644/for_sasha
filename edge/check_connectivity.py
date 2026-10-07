#!/usr/bin/env python3
"""Validate edge machine connectivity to backend edge API and MediaMTX publish port."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

EDGE_DIR = Path(__file__).resolve().parent
load_dotenv(EDGE_DIR / ".env")

EDGE_API_URL = os.getenv("EDGE_API_URL", "").strip()
EDGE_GATEWAY_TOKEN = os.getenv("EDGE_GATEWAY_TOKEN", "").strip()
MEDIAMTX_HOST = os.getenv("MEDIAMTX_HOST", "").strip()
MEDIAMTX_RTSP_PORT = int(os.getenv("MEDIAMTX_RTSP_PORT", "8554"))
DEBUG_LOG = EDGE_DIR.parent / "debug-abbe6f.log"


def debug_log(message: str, data: dict, hypothesis_id: str = "H6") -> None:
    # region agent log
    payload = {
        "sessionId": "abbe6f",
        "hypothesisId": hypothesis_id,
        "location": "edge/check_connectivity.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass
    # endregion


def main() -> int:
    errors: list[str] = []

    if not EDGE_API_URL:
        errors.append("EDGE_API_URL is not configured")
    if not EDGE_GATEWAY_TOKEN:
        errors.append("EDGE_GATEWAY_TOKEN is not configured")
    if not MEDIAMTX_HOST:
        errors.append("MEDIAMTX_HOST is not configured")

    publish_host = MEDIAMTX_HOST
    publish_port = MEDIAMTX_RTSP_PORT

    if EDGE_API_URL and EDGE_GATEWAY_TOKEN:
        try:
            response = requests.get(
                EDGE_API_URL,
                headers={"Authorization": f"Bearer {EDGE_GATEWAY_TOKEN}"},
                timeout=15,
            )
            debug_log(
                "edge api probe",
                {"status_code": response.status_code, "url": EDGE_API_URL},
                "H4",
            )
            if response.status_code != 200:
                errors.append(f"Edge API returned HTTP {response.status_code}")
            else:
                payload = response.json()
                publish_host = payload.get("mediamtx_publish_host") or publish_host
                publish_port = int(payload.get("mediamtx_rtsp_port") or publish_port)
                camera_count = len(payload.get("cameras", []))
                print(f"Edge API OK | assigned cameras={camera_count} | publish={publish_host}:{publish_port}")
        except requests.RequestException as exc:
            errors.append(f"Edge API connection failed: {exc}")
            debug_log("edge api probe failed", {"error": str(exc)[:200]}, "H4")

    if publish_host:
        try:
            with socket.create_connection((publish_host, publish_port), timeout=5):
                print(f"MediaMTX publish TCP OK | {publish_host}:{publish_port}")
                debug_log(
                    "mediamtx tcp probe",
                    {"host": publish_host, "port": publish_port, "reachable": True},
                )
        except OSError as exc:
            errors.append(
                f"MediaMTX publish TCP failed for {publish_host}:{publish_port} ({exc})"
            )
            debug_log(
                "mediamtx tcp probe",
                {
                    "host": publish_host,
                    "port": publish_port,
                    "reachable": False,
                    "error": str(exc)[:200],
                },
            )

    if errors:
        print("Connectivity check FAILED:")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("Connectivity check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
