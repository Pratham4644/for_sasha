from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import DetectionItem, IngestionMode, UserRole

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    success: bool = True
    data: T | None = None
    error: dict[str, Any] | None = None
    message: str | None = None


# --- Auth & User Schemas ---

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    organization_id: str


class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: UserRole = UserRole.VIEWER
    organization_id: str | None = None


class UserResponse(BaseModel):
    id: str
    organization_id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Camera Schemas ---

class CameraCreate(BaseModel):
    name: str
    site_id: str | None = None
    camera_id: str | None = None  # Optional custom string ID, defaults to generated
    source_protocol: str = "RTSP"
    source_url: str
    media_path: str | None = None
    username: str | None = None
    password: str | None = None
    ingestion_mode: IngestionMode | None = None
    edge_gateway_id: str | None = None
    configured_resolution: str = "1280x720"
    configured_fps: float = 15.0
    enabled: bool = True
    ai_enabled: bool = True
    ai_model: str = "yolo"
    ai_endpoint: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    site_id: str | None = None
    source_url: str | None = None
    media_path: str | None = None
    username: str | None = None
    password: str | None = None
    ingestion_mode: IngestionMode | None = None
    edge_gateway_id: str | None = None
    configured_resolution: str | None = None
    configured_fps: float | None = None
    enabled: bool | None = None
    ai_enabled: bool | None = None
    ai_model: str | None = None
    ai_endpoint: str | None = None


class CameraResponse(BaseModel):
    id: str
    camera_id: str
    organization_id: str
    site_id: str
    name: str
    description: str | None = None
    source_protocol: str
    stream_url: str  # Sanitized URL without credentials
    source_url: str  # Same as stream_url for compatibility
    media_path: str
    configured_resolution: str
    configured_fps: float
    enabled: bool
    ai_enabled: bool
    ai_model: str
    ingestion_mode: str
    edge_gateway_id: str | None = None
    stream_paused: bool = False
    status: str
    created_at: datetime
    updated_at: datetime


class CameraPlaybackResponse(BaseModel):
    camera_id: str
    name: str
    media_path: str
    whep_url: str
    whep_ai_url: str | None = None
    hls_url: str
    hls_ai_url: str | None = None
    rtsp_url: str
    rtsp_ai_url: str | None = None
    reader_credentials: dict[str, str] | None = None


class CameraStreamResponse(BaseModel):
    camera_id: str
    status: str
    online: bool
    streams: dict[str, str]


# --- Detection Schemas ---

class DetectionEventCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    camera_id: str
    site_id: str | None = None
    timestamp: datetime | None = None
    class_name: str
    confidence: float
    bounding_box: list[float] | None = None
    duration_seconds: float = 0.0
    track_id: str | None = None
    detections: list[DetectionItem] = Field(default_factory=list)
    model_name: str = "yolo"
    model_endpoint: str | None = None
    inference_latency_ms: float = 0.0


class DetectionEventResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: str
    camera_id: str
    camera_name: str | None = None
    site_id: str | None = None
    timestamp: datetime
    class_name: str
    confidence: float
    bounding_box: list[float] | None = None
    detections: list[DetectionItem] = Field(default_factory=list)
    model_name: str = "yolo"
    inference_latency_ms: float = 0.0
    created_at: datetime


class DetectionLogsResponse(BaseModel):
    items: list[DetectionEventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
