#!/usr/bin/env python3
"""
Transport diagnostics for edge -> AWS MediaMTX publish path.

Measures Tailscale path quality and optional FFmpeg publish throughput.
Writes NDJSON evidence to debug-abbe6f.log (no secrets logged).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

DEBUG_LOG = Path(__file__).resolve().parent.parent / "debug-abbe6f.log"
SESSION_ID = "abbe6f"


def log_event(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": SESSION_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
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


def run_command(args: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, "", str(exc)


def tcp_probe(host: str, port: int, timeout: float = 5.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            rtt_ms = round((time.monotonic() - started) * 1000, 1)
            return {"reachable": True, "connect_ms": rtt_ms}
    except OSError as exc:
        return {"reachable": False, "error": str(exc)[:200]}


def tailscale_diagnostics(peer: str) -> dict[str, Any]:
    data: dict[str, Any] = {"peer": peer}
    code, stdout, stderr = run_command(["tailscale", "status"], timeout=10)
    data["status_rc"] = code
    if code == 0:
        for line in stdout.splitlines():
            if peer in line:
                data["peer_line"] = line.strip()
                data["uses_derp"] = "relay" in line.lower()
                data["direct"] = "direct" in line.lower()
                break
    code, stdout, _ = run_command(["tailscale", "ping", "-c", "4", peer], timeout=30)
    data["ping_rc"] = code
    rtts = [float(x) for x in re.findall(r"in\s+([\d.]+)(?:ms|s)", stdout)]
    if rtts:
        data["ping_samples_ms"] = rtts
        data["ping_avg_ms"] = round(sum(rtts) / len(rtts), 1)
    combined = (stdout + stderr).lower()
    data["ping_output"] = stdout.strip()[-500:]
    data["direct_established"] = (
        "via derp" not in combined
        and "direct connection not established" not in combined
    )
    code, stdout, _ = run_command(["tailscale", "netcheck"], timeout=20)
    if code == 0:
        data["nearest_derp"] = ""
        for line in stdout.splitlines():
            if "Nearest DERP:" in line:
                data["nearest_derp"] = line.split(":", 1)[-1].strip()
            if line.strip().startswith("PortMapping:"):
                data["port_mapping"] = line.split(":", 1)[-1].strip() or "none"
    log_event("H7", "transport_diagnostics.py:tailscale", "tailscale path metrics", data)
    return data


def camera_fps_probe(source_url: str, seconds: float = 5.0) -> dict[str, Any]:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", source_url,
        "-map", "0:v:0", "-c:v", "copy", "-an",
        "-t", str(seconds),
        "-f", "null", "-",
    ]
    started = time.monotonic()
    code, _, stderr = run_command(cmd, timeout=seconds + 15)
    elapsed = round(time.monotonic() - started, 2)
    frame_match = re.search(r"frame=\s*(\d+)", stderr)
    frames = int(frame_match.group(1)) if frame_match else None
    fps = round(frames / elapsed, 2) if frames and elapsed > 0 else None
    result = {"elapsed_s": elapsed, "frames": frames, "fps": fps, "rc": code}
    log_event("H8", "transport_diagnostics.py:camera_fps", "camera input fps", result)
    return result


def publish_throughput_probe(
    source_url: str,
    publish_url: str,
    seconds: float = 10.0,
) -> dict[str, Any]:
    """Short FFmpeg publish test; parses final speed= from stderr."""
    redacted_host = urlsplit(publish_url).hostname or "unknown"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-nostdin", "-rtsp_transport", "tcp",
        "-i", source_url,
        "-map", "0:v:0", "-c:v", "copy", "-an",
        "-f", "rtsp", "-rtsp_transport", "tcp",
        publish_url,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        stderr_lines: list[str] = []
        while time.monotonic() - started < seconds:
            if proc.poll() is not None:
                break
            line = proc.stderr.readline() if proc.stderr else ""
            if line:
                stderr_lines.append(line.rstrip())
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        elapsed = round(time.monotonic() - started, 2)
    except FileNotFoundError:
        return {"error": "ffmpeg not found"}

    stderr = "\n".join(stderr_lines)
    speed_match = re.findall(r"speed=\s*([\d.]+)x", stderr)
    frame_match = re.search(r"frame=\s*(\d+)", stderr)
    time_match = re.search(r"time=\s*([\d:.]+)", stderr)
    frames = int(frame_match.group(1)) if frame_match else None
    speed = float(speed_match[-1]) if speed_match else None
    result = {
        "publish_host": redacted_host,
        "elapsed_s": elapsed,
        "frames": frames,
        "video_time": time_match.group(1) if time_match else None,
        "speed_x": speed,
        "publish_fps": round(frames / elapsed, 2) if frames and elapsed > 0 else None,
    }
    log_event("H9", "transport_diagnostics.py:publish", "ffmpeg publish throughput", result)
    return result


def recommendations(metrics: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    ts = metrics.get("tailscale", {})
    if ts.get("uses_derp") or not ts.get("direct_established", True):
        recs.append(
            "Tailscale is relaying via DERP (~400ms RTT). Enable direct WireGuard: "
            "AWS SG inbound UDP 41641, router UPnP or manual UDP 41641 -> edge PC, "
            "then re-test with: tailscale ping --until-direct <aws-tailscale-ip>"
        )
    if ts.get("port_mapping") in ("none", "", None):
        recs.append(
            "Router reports no UPnP/NAT-PMP (PortMapping empty). This commonly blocks "
            "Tailscale UDP hole punching from India ISP routers. Test phone hotspot A/B."
        )
    pub = metrics.get("publish", {})
    if pub.get("speed_x") is not None and pub["speed_x"] < 0.5:
        recs.append(
            f"FFmpeg publish speed={pub['speed_x']}x indicates WAN TCP collapse (not FFmpeg/config). "
            "Fix network path before tuning application code."
        )
    if pub.get("speed_x") is not None and pub["speed_x"] < 0.5:
        recs.append(
            "If direct Tailscale still <0.5x: benchmark AWS ap-south-1 (Mumbai) vs ap-southeast-2 "
            "with identical ffmpeg publish test. India->Sydney RTT ~320-400ms is poor for RTSP/TCP."
        )
    recs.append("Remove temporary public SG rule for TCP 8554 after testing.")
    recs.append("Rotate compromised MediaMTX publisher credential.")
    return recs


def main() -> int:
    if DEBUG_LOG.exists():
        DEBUG_LOG.unlink()

    peer = os.getenv("AWS_TAILSCALE_IP", "100.101.127.80")
    publish_host = os.getenv("MEDIAMTX_HOST", peer)
    publish_port = int(os.getenv("MEDIAMTX_RTSP_PORT", "8554"))
    source = os.getenv("EDGE_SOURCE_URL", "rtsp://192.168.1.14:8080/h264.sdp")
    media_path = os.getenv("EDGE_MEDIA_PATH", "cam_transport_test")
    publish_user = os.getenv("MEDIAMTX_PUBLISH_USERNAME", "edge_publisher")
    publish_pass = os.getenv("MEDIAMTX_PUBLISH_PASSWORD", "")

    metrics: dict[str, Any] = {
        "tcp_publish": tcp_probe(publish_host, publish_port),
        "tailscale": tailscale_diagnostics(peer),
    }

    print("=== Transport Diagnostics ===")
    print(f"TCP {publish_host}:{publish_port} -> {metrics['tcp_publish']}")
    print(f"Tailscale peer {peer} -> avg RTT {metrics['tailscale'].get('ping_avg_ms')} ms, DERP={metrics['tailscale'].get('uses_derp')}")

    metrics["camera"] = camera_fps_probe(source, seconds=5.0)
    print(f"Camera input -> {metrics['camera'].get('fps')} FPS over {metrics['camera'].get('elapsed_s')}s")

    if publish_pass:
        from urllib.parse import quote

        user = quote(publish_user, safe="")
        pwd = quote(publish_pass, safe="")
        publish_url = f"rtsp://{user}:{pwd}@{publish_host}:{publish_port}/{media_path}"
        metrics["publish"] = publish_throughput_probe(source, publish_url, seconds=10.0)
        print(
            f"Publish test -> speed={metrics['publish'].get('speed_x')}x, "
            f"fps={metrics['publish'].get('publish_fps')}, frames={metrics['publish'].get('frames')}"
        )
    else:
        print("Skipping publish test (MEDIAMTX_PUBLISH_PASSWORD not set).")

    recs = recommendations(metrics)
    print("\n=== Recommendations ===")
    for item in recs:
        print(f"- {item}")

    log_event("H10", "transport_diagnostics.py:main", "diagnostics complete", {"recommendations": recs})
    return 0


if __name__ == "__main__":
    sys.exit(main())
