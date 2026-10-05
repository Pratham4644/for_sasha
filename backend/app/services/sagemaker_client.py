from __future__ import annotations

import json
import logging
import random
import time
from typing import Any
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from backend.app.config import settings

LOGGER = logging.getLogger("camera.platform.sagemaker")


class SageMakerInferenceClient:
    """
    AWS SageMaker Runtime client for YOLO object detection inference.
    Includes automated fallback to local/simulated detector for offline development.
    """

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
        Invokes SageMaker endpoint with JPEG image bytes.
        Returns:
            (result_dict, latency_ms)
        """
        start_time = time.monotonic()
        client = self._get_client()

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
                return json.loads(raw_body), latency_ms
            except (ClientError, BotoCoreError, NoCredentialsError) as aws_err:
                LOGGER.debug("AWS SageMaker invocation unavailable (%s): %s", self.endpoint_name, aws_err)
                self._aws_available = False
            except Exception as exc:
                LOGGER.warning("SageMaker invoke error: %s", exc)
                self._aws_available = False

        # Fallback to local mock if enabled
        if self.allow_mock or settings.ai_mock_fallback:
            return self._mock_detect(image_bytes), (time.monotonic() - start_time) * 1000.0

        return None, 0.0

    def _mock_detect(self, image_bytes: bytes) -> dict[str, Any]:
        """Simulated detector providing realistic object detections for local verification."""
        # Realistic CCTV classes
        classes = ["person", "car", "bicycle", "backpack", "truck"]
        # Determine 1-2 realistic detections
        num_dets = random.choice([1, 1, 2])
        detections = []
        for _ in range(num_dets):
            cls = random.choice(classes)
            conf = round(random.uniform(0.65, 0.96), 2)
            # Normalized box within typical 1280x720 coordinates
            x1 = random.randint(100, 600)
            y1 = random.randint(100, 350)
            x2 = x1 + random.randint(120, 300)
            y2 = y1 + random.randint(150, 350)
            detections.append({
                "class_id": classes.index(cls),
                "class_name": cls,
                "confidence": conf,
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
            })

        return {"detections": detections}
