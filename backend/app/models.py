from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return str(uuid.uuid4())


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=generate_uuid)
    organization_id: str
    email: str
    name: str
    password_hash: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Organization(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Site(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    organization_id: str
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DetectionItem(BaseModel):
    class_id: int
    class_name: str
    confidence: float
    bbox: list[float] = Field(default_factory=list)  # [x1, y1, x2, y2]


class Camera(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    organization_id: str
    site_id: str
    name: str
    description: str | None = None
    source_protocol: str = "RTSP"  # RTSP, HTTP, HTTPS
    source_url_template: str
    media_path: str  # MediaMTX path e.g. camera_001
    credentials_ref: str | None = None  # Encrypted credentials (Fernet)
    enabled: bool = True
    ai_enabled: bool = True
    ai_model: str = "yolo"
    ai_endpoint: str | None = None
    configured_resolution: str = "1280x720"
    configured_fps: float = 15.0
    status: CameraStatus = CameraStatus.UNKNOWN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DetectionEvent(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: str = Field(default_factory=generate_uuid)
    organization_id: str
    site_id: str | None = None
    camera_id: str
    camera_name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    detections: list[DetectionItem] = Field(default_factory=list)
    class_name: str = "unknown"
    confidence: float = 0.0
    bounding_box: list[float] | None = None
    duration_seconds: float = 0.0
    track_id: str | None = None
    model_name: str = "yolo"
    model_endpoint: str | None = None
    inference_latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class AuditLog(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    organization_id: str | None = None
    user_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
