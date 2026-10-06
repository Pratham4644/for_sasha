from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from typing import Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from PIL import Image

from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.sagemaker")

# Global singleton cache for local YOLO model
_LOCAL_MODEL = None
_LOCAL_MODEL_LOCK = threading.Lock()
_LOCAL_MODEL_LOADED = False


def _get_local_yolo_model() -> Any:
    """Loads and caches the local YOLO26s model from known local paths."""
    global _LOCAL_MODEL, _LOCAL_MODEL_LOADED
    if _LOCAL_MODEL_LOADED:
        return _LOCAL_MODEL

    with _LOCAL_MODEL_LOCK:
        if _LOCAL_MODEL_LOADED:
            return _LOCAL_MODEL

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        candidates = [
            os.path.join(base_dir, "production", "models", "yolo26s.pt"),
            os.path.join(base_dir, "models", "yolo26s.pt"),
            os.path.join(base_dir, "friend-system", "for_sasha", "sagemaker_yolo", "yolo26s.pt"),
            os.path.join(os.path.dirname(base_dir), "friend-system", "for_sasha", "sagemaker_yolo", "yolo26s.pt"),
        ]

        model_path = None
        for p in candidates:
            if os.path.exists(p):
                model_path = p
                break

        if model_path:
            try:
                from ultralytics import YOLO
                LOGGER.info("Loading local YOLO model from %s...", model_path)
                _LOCAL_MODEL = YOLO(model_path)
                LOGGER.info("Local YOLO model successfully loaded.")
            except Exception as exc:
                LOGGER.error("Failed to load local YOLO model from %s: %s", model_path, exc)
                _LOCAL_MODEL = None
        else:
            LOGGER.warning("No local YOLO model found in candidate locations: %s", candidates)
            _LOCAL_MODEL = None

        _LOCAL_MODEL_LOADED = True
        return _LOCAL_MODEL


class SageMakerInferenceClient:
    """
    AWS SageMaker Runtime client for YOLO object detection inference.
    Falls back to high-performance local YOLO26s detector when AWS is unreachable or blocked.
    """

    # Shared telemetry across all pipeline instances
    total_inferences: int = 0
    successful_inferences: int = 0
    last_inference_at: str | None = None
    last_latency_ms: float = 0.0
    active_mode: str = "local_yolo"  # "sagemaker" or "local_yolo"

    def __init__(
        self,
        region: str | None = None,
        endpoint_name: str | None = None,
        allow_mock: bool = True,
    ) -> None:
        self.region = region or settings.sagemaker_region
        self.endpoint_name = endpoint_name or settings.sagemaker_endpoint_name
        self.allow_mock = allow_mock
        self._client: Any = None
        self._initialized = False
        self._aws_available = True

    def _get_client(self) -> Any:
        if self._client is None and not self._initialized:
            self._initialized = True
            try:
                kwargs: dict[str, Any] = {"region_name": self.region}
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    kwargs["aws_access_key_id"] = settings.aws_access_key_id
                    kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

                self._client = boto3.client("sagemaker-runtime", **kwargs)
            except Exception as exc:
                LOGGER.warning("Could not initialize boto3 SageMaker client (%s): %s", self.region, exc)
                self._aws_available = False
                self._client = None
        return self._client

    def invoke(self, image_bytes: bytes) -> tuple[dict[str, Any] | None, float]:
        """
        Invokes SageMaker endpoint or local YOLO model with JPEG image bytes.
        Returns:
            (result_dict, latency_ms)
        """
        SageMakerInferenceClient.total_inferences += 1
        start_time = time.monotonic()
        client = self._get_client()

        # 1. Attempt AWS SageMaker endpoint if available
        if client and self._aws_available:
            try:
                response = client.invoke_endpoint(
                    EndpointName=self.endpoint_name,
                    ContentType="image/jpeg",
                    Accept="application/json",
                    Body=image_bytes,
                )
                latency_ms = (time.monotonic() - start_time) * 1000.0
                raw_body = response["Body"].read().decode("utf-8")
                res = json.loads(raw_body)
                SageMakerInferenceClient.successful_inferences += 1
                SageMakerInferenceClient.active_mode = "sagemaker"
                SageMakerInferenceClient.last_inference_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                SageMakerInferenceClient.last_latency_ms = latency_ms
                return res, latency_ms
            except (ClientError, BotoCoreError, NoCredentialsError) as aws_err:
                LOGGER.debug("AWS SageMaker invocation unavailable (%s): %s", self.endpoint_name, aws_err)
                self._aws_available = False
            except Exception as exc:
                LOGGER.warning("SageMaker invoke error: %s", exc)
                self._aws_available = False

        # 2. Local Real YOLO Model Inference Fallback
        local_model = _get_local_yolo_model()
        if local_model is not None:
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                results = local_model.predict(
                    source=img,
                    conf=settings.ai_min_confidence,
                    verbose=False,
                )
                detections = []
                for result in results:
                    for box in result.boxes:
                        detections.append({
                            "class_id": int(box.cls[0]),
                            "class_name": result.names[int(box.cls[0])],
                            "confidence": round(float(box.conf[0]), 4),
                            "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                        })
                latency_ms = (time.monotonic() - start_time) * 1000.0
                SageMakerInferenceClient.successful_inferences += 1
                SageMakerInferenceClient.active_mode = "local_yolo"
                SageMakerInferenceClient.last_inference_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                SageMakerInferenceClient.last_latency_ms = latency_ms
                return {"detections": detections}, latency_ms
            except Exception as exc:
                LOGGER.error("Local YOLO inference failed: %s", exc)

        # 3. If no model is available, return empty detections (never fake objects)
        latency_ms = (time.monotonic() - start_time) * 1000.0
        return {"detections": []}, latency_ms
