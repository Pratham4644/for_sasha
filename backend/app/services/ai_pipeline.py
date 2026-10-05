from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import quote

import cv2
import httpx
import numpy as np

from backend.app.config import settings
from backend.app.db import db
from backend.app.models import Camera, DetectionEvent, DetectionItem, generate_uuid, utc_now
from backend.app.services.sagemaker_client import SageMakerInferenceClient
from backend.app.websocket_manager import websocket_manager

LOGGER = logging.getLogger("camera.platform.ai_pipeline")


class CameraAIPipeline:
    """
    Independent AI inference worker and stream overlay generator for a camera.
    Adapted from friend-system's proven pipeline, generalized for dynamic cameras.
    """

    def __init__(
        self,
        camera: Camera,
        inference_client: SageMakerInferenceClient | None = None,
    ) -> None:
        self.camera_id = camera.id
        self.camera_name = camera.name
        self.organization_id = camera.organization_id
        self.site_id = camera.site_id
        self.media_path = camera.media_path
        self.confidence_threshold = settings.ai_min_confidence
        self.inference_interval = settings.ai_inference_interval

        self.sagemaker = inference_client or SageMakerInferenceClient(
            endpoint_name=camera.ai_endpoint or settings.sagemaker_endpoint_name,
        )

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._ffmpeg_proc: subprocess.Popen | None = None

        # Build RTSP URLs
        host = settings.mediamtx_host
        port = settings.mediamtx_rtsp_port
        pub_u = settings.mediamtx_publish_username
        pub_p = settings.mediamtx_publish_password
        read_u = settings.mediamtx_read_username
        read_p = settings.mediamtx_read_password

        # Input stream from MediaMTX
        if read_u and read_p:
            self.input_url = f"rtsp://{quote(read_u, safe='')}:{quote(read_p, safe='')}@{host}:{port}/{self.media_path}"
        else:
            self.input_url = f"rtsp://{host}:{port}/{self.media_path}"

        # Output stream with AI bounding boxes published to {media_path}-ai
        if pub_u and pub_p:
            self.output_url = f"rtsp://{quote(pub_u, safe='')}:{quote(pub_p, safe='')}@{host}:{port}/{self.media_path}-ai"
        else:
            self.output_url = f"rtsp://{host}:{port}/{self.media_path}-ai"

    def _is_source_ready(self) -> bool:
        """Return true only when MediaMTX reports an active publisher for this path."""
        api_url = settings.mediamtx_api_url.rstrip("/")
        auth = None
        if settings.mediamtx_publish_username and settings.mediamtx_publish_password:
            auth = (settings.mediamtx_publish_username, settings.mediamtx_publish_password)
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{api_url}/v3/paths/get/{self.media_path}", auth=auth)
            if res.status_code != 200:
                return False
            detail = res.json()
            return bool(detail.get("sourceReady", detail.get("ready", False)))
        except Exception as exc:
            LOGGER.debug("AI readiness check failed for %s: %s", self.camera_id, exc)
            return False

    def start(self) -> None:
        """Starts the AI pipeline background worker."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_pipeline,
            name=f"ai-pipeline-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("AI Pipeline started for camera %s (path: %s)", self.camera_id, self.media_path)

    def stop(self) -> None:
        """Stops the AI pipeline and cleanly terminates the FFmpeg publisher."""
        LOGGER.info("Stopping AI Pipeline for camera %s...", self.camera_id)
        self._stop_event.set()
        self._stop_ffmpeg_publisher()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        LOGGER.info("AI Pipeline stopped for camera %s", self.camera_id)

    def _stop_ffmpeg_publisher(self) -> None:
        """Terminates any existing AI overlay FFmpeg publisher (no duplicates)."""
        proc = self._ffmpeg_proc
        self._ffmpeg_proc = None
        if not proc:
            return
        try:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _start_ffmpeg_publisher(self, width: int, height: int, fps: float) -> subprocess.Popen:
        """Starts the FFmpeg subprocess to publish the annotated frames to MediaMTX."""
        ffmpeg_bin = shutil.which(settings.ffmpeg_binary) or "ffmpeg"
        fps_str = str(int(fps)) if fps == int(fps) else f"{fps:.2f}"
        gop_str = str(int(fps))

        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "warning",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", fps_str,
            "-i", "-",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-g", gop_str,
            "-an",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            self.output_url,
        ]

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def _run_pipeline(self) -> None:
        """Main AI pipeline execution loop."""
        # Give MediaMTX a moment to establish the primary camera stream
        time.sleep(1.0)

        cap: cv2.VideoCapture | None = None
        retries = 0
        max_retries = 30

        while not self._stop_event.is_set():
            if cap is None or not cap.isOpened():
                if not self._is_source_ready():
                    retries += 1
                    if retries > max_retries:
                        LOGGER.info("AI Pipeline for %s waiting for MediaMTX publisher on %s", self.camera_id, self.media_path)
                        retries = 0
                    time.sleep(2.0)
                    continue

                cap = cv2.VideoCapture(self.input_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    retries += 1
                    time.sleep(1.0)
                    if retries > max_retries:
                        LOGGER.warning("AI Pipeline for %s waiting for stream on %s", self.camera_id, self.input_url)
                        retries = 0
                    continue
                LOGGER.info("AI Pipeline connected to stream for camera %s", self.camera_id)

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
            fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
            if fps <= 0 or fps > 60:
                fps = 15.0

            # Start FFmpeg publisher for AI processed stream (replace any leftover)
            try:
                self._stop_ffmpeg_publisher()
                self._ffmpeg_proc = self._start_ffmpeg_publisher(width, height, fps)
            except Exception as exc:
                LOGGER.error("Failed to start AI stream FFmpeg publisher: %s", exc)

            last_sample_time = 0.0
            current_detections: list[dict[str, Any]] = []

            try:
                while not self._stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        LOGGER.debug("AI Pipeline read empty frame on %s", self.camera_id)
                        time.sleep(0.05)
                        break

                    now = time.monotonic()

                    # Sample frame for AI inference at configured interval
                    if now - last_sample_time >= self.inference_interval:
                        last_sample_time = now
                        # Encode frame as JPEG for SageMaker
                        success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        if success:
                            jpeg_bytes = encoded.tobytes()
                            result, latency_ms = self.sagemaker.invoke(jpeg_bytes)
                            if result and isinstance(result, dict):
                                raw_dets = result.get("detections", [])
                                valid_dets = [
                                    d for d in raw_dets
                                    if d.get("confidence", 0.0) >= self.confidence_threshold
                                ]
                                current_detections = valid_dets

                                # If detections were made, record event to MongoDB and broadcast
                                if valid_dets:
                                    self._persist_and_broadcast(valid_dets, latency_ms)

                    # Overlay bounding boxes on the frame
                    annotated_frame = frame.copy()
                    for det in current_detections:
                        class_name = det.get("class_name", "object")
                        conf = det.get("confidence", 0.0)
                        bbox = det.get("bbox", [])
                        if len(bbox) == 4:
                            x1, y1, x2, y2 = map(int, bbox)
                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            label = f"{class_name} {conf:.0%}"
                            cv2.putText(
                                annotated_frame,
                                label,
                                (x1, max(25, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                (0, 255, 0),
                                2,
                            )

                    # Send processed frame to FFmpeg publisher
                    if self._ffmpeg_proc and self._ffmpeg_proc.stdin:
                        try:
                            self._ffmpeg_proc.stdin.write(annotated_frame.tobytes())
                        except (BrokenPipeError, OSError):
                            LOGGER.debug("AI FFmpeg pipe closed, will restart publisher.")
                            break
            finally:
                self._stop_ffmpeg_publisher()
                if cap:
                    cap.release()
                    cap = None

        if cap:
            cap.release()
            self._stop_ffmpeg_publisher()

    def _persist_and_broadcast(
        self,
        detections: list[dict[str, Any]],
        latency_ms: float,
    ) -> None:
        """Stores structured DetectionEvent into MongoDB and broadcasts to WebSocket clients."""
        try:
            top_det = max(detections, key=lambda d: d.get("confidence", 0.0))
            retention_days = settings.detection_retention_days
            expires_at = utc_now() + timedelta(days=retention_days)

            det_items = [
                DetectionItem(
                    class_id=d.get("class_id", 0),
                    class_name=d.get("class_name", "object"),
                    confidence=d.get("confidence", 0.0),
                    bbox=d.get("bbox", []),
                )
                for d in detections
            ]

            event = DetectionEvent(
                id=generate_uuid(),
                organization_id=self.organization_id,
                site_id=self.site_id,
                camera_id=self.camera_id,
                camera_name=self.camera_name,
                timestamp=utc_now(),
                detections=det_items,
                class_name=top_det.get("class_name", "object"),
                confidence=top_det.get("confidence", 0.0),
                bounding_box=top_det.get("bbox"),
                model_name=settings.ai_model_name,
                model_endpoint=settings.sagemaker_endpoint_name,
                inference_latency_ms=round(latency_ms, 2),
                created_at=utc_now(),
                expires_at=expires_at,
            )

            # Insert into MongoDB
            doc = event.model_dump(mode="json")

            async def _save_and_broadcast():
                try:
                    await db.detection_events.insert_one(doc)
                    # Broadcast event to WebSocket clients
                    await websocket_manager.broadcast({
                        "type": "detection_event",
                        "data": {
                            "id": event.id,
                            "camera_id": event.camera_id,
                            "camera_name": event.camera_name,
                            "timestamp": event.timestamp.isoformat(),
                            "class_name": event.class_name,
                            "confidence": event.confidence,
                            "bounding_box": event.bounding_box,
                            "detections_count": len(event.detections),
                            "inference_latency_ms": event.inference_latency_ms,
                        },
                    })
                except Exception as exc:
                    LOGGER.debug("Async persistence/broadcast error: %s", exc)

            loop = ai_pipeline_manager.main_loop
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(_save_and_broadcast(), loop)
            else:
                try:
                    cur = asyncio.get_event_loop()
                    if cur.is_running():
                        asyncio.run_coroutine_threadsafe(_save_and_broadcast(), cur)
                except Exception:
                    pass
        except Exception as exc:
            LOGGER.error("Failed to persist and broadcast detection event: %s", exc)


class AIPipelineManager:
    """Manages independent AI pipelines across all cameras."""

    def __init__(self) -> None:
        self.pipelines: dict[str, CameraAIPipeline] = {}
        self.lock = threading.Lock()
        self.main_loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the application's primary event loop for thread-safe event dispatch."""
        self.main_loop = loop

    def start_pipeline(self, camera: Camera) -> None:
        """Starts an AI pipeline for the camera if not already active."""
        if not camera.ai_enabled or not settings.ai_enabled:
            return

        with self.lock:
            existing = self.pipelines.get(camera.id)
            if existing:
                return

            pipeline = CameraAIPipeline(camera)
            pipeline.start()
            self.pipelines[camera.id] = pipeline

    def stop_pipeline(self, camera_id: str) -> None:
        """Stops the AI pipeline for a camera."""
        with self.lock:
            pipeline = self.pipelines.pop(camera_id, None)
            if pipeline:
                pipeline.stop()

    def is_running(self, camera_id: str) -> bool:
        with self.lock:
            return camera_id in self.pipelines

    def stop_all(self) -> None:
        with self.lock:
            pipelines = list(self.pipelines.values())
            self.pipelines.clear()
        for p in pipelines:
            p.stop()


ai_pipeline_manager = AIPipelineManager()
