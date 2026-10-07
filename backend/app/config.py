from __future__ import annotations

import os
from typing import Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "production", "testing"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    app_name: str = Field(
        default="Dynamic Remote Camera & AI Platform",
        validation_alias="APP_NAME",
    )
    debug: bool = Field(
        default=False,
        validation_alias="DEBUG",
    )
    app_host: str = Field(
        default="127.0.0.1",
        validation_alias="APP_HOST",
    )
    app_port: int = Field(
        default=8000,
        validation_alias="APP_PORT",
    )
    public_api_url: str = Field(
        default="http://localhost:8000",
        validation_alias="PUBLIC_API_URL",
    )

    # Database (MongoDB / MongoDB Atlas)
    mongodb_uri: str = Field(
        default="mongodb://127.0.0.1:27017",
        validation_alias="MONGODB_URI",
    )
    mongodb_database: str = Field(
        default="camera_ai_platform",
        validation_alias="MONGODB_DATABASE",
    )

    # Auth & Security
    jwt_secret: str = Field(
        default="dev_secret_key_minimum_32_chars_long_for_security_12345",
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    access_token_expire_minutes: int = Field(
        default=720,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # Cookies
    cookie_name: str = Field(
        default="camera_session",
        validation_alias="COOKIE_NAME",
    )
    cookie_secure: bool = Field(
        default=False,
        validation_alias="COOKIE_SECURE",
    )
    cookie_http_only: bool = Field(
        default=True,
        validation_alias="COOKIE_HTTP_ONLY",
    )
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        validation_alias="COOKIE_SAMESITE",
    )

    # Camera Credential Encryption
    camera_encryption_key: str = Field(
        default="GsN70SjxmJEaPzDVKCgOHRCp1rpu_cOdgLzNLV_37Wo",
        validation_alias="CAMERA_ENCRYPTION_KEY",
    )

    # MediaMTX
    mediamtx_host: str = Field(
        default="127.0.0.1",
        validation_alias="MEDIAMTX_HOST",
    )
    mediamtx_rtsp_port: int = Field(
        default=8554,
        validation_alias="MEDIAMTX_RTSP_PORT",
    )
    mediamtx_webrtc_port: int = Field(
        default=8889,
        validation_alias="MEDIAMTX_WEBRTC_PORT",
    )
    mediamtx_hls_port: int = Field(
        default=8888,
        validation_alias="MEDIAMTX_HLS_PORT",
    )
    mediamtx_api_url: str = Field(
        default="http://127.0.0.1:9997",
        validation_alias="MEDIAMTX_API_URL",
    )
    public_webrtc_url: str = Field(
        default="http://localhost:8889",
        validation_alias="PUBLIC_WEBRTC_URL",
    )
    public_hls_url: str = Field(
        default="http://localhost:8888",
        validation_alias="PUBLIC_HLS_URL",
    )
    mediamtx_publish_username: str = Field(
        default="edge_publisher",
        validation_alias="MEDIAMTX_PUBLISH_USERNAME",
    )
    mediamtx_publish_password: str = Field(
        default="dev_mediamtx_pub_pwd_secure",
        validation_alias="MEDIAMTX_PUBLISH_PASSWORD",
    )
    mediamtx_read_username: str = Field(
        default="webrtc_reader",
        validation_alias="MEDIAMTX_READ_USERNAME",
    )
    mediamtx_read_password: str = Field(
        default="dev_mediamtx_read_pwd_secure",
        validation_alias="MEDIAMTX_READ_PASSWORD",
    )

    # Streaming / FFmpeg
    ffmpeg_binary: str = Field(
        default="ffmpeg",
        validation_alias="FFMPEG_BINARY",
    )
    ffmpeg_encoder: str = Field(
        default="libx264",
        validation_alias="FFMPEG_ENCODER",
    )
    stream_resolution: str = Field(
        default="1280x720",
        validation_alias="STREAM_RESOLUTION",
    )
    stream_fps: float = Field(
        default=15.0,
        validation_alias="STREAM_FPS",
    )
    stream_bitrate: str = Field(
        default="1M",
        validation_alias="STREAM_BITRATE",
    )

    # AI Pipeline & SageMaker
    ai_enabled: bool = Field(
        default=True,
        validation_alias="AI_ENABLED",
    )
    ai_model_name: str = Field(
        default="yolo",
        validation_alias="AI_MODEL_NAME",
    )
    ai_inference_interval: float = Field(
        default=1.0,
        validation_alias="AI_INFERENCE_INTERVAL",
    )
    ai_min_confidence: float = Field(
        default=0.35,
        validation_alias="AI_MIN_CONFIDENCE",
    )
    ai_mock_fallback: bool = Field(
        default=True,
        validation_alias="AI_MOCK_FALLBACK",
    )
    sagemaker_region: str = Field(
        default="us-east-1",
        validation_alias="SAGEMAKER_REGION",
    )
    sagemaker_endpoint_name: str = Field(
        default="yolo26s-cctv-endpoint",
        validation_alias="SAGEMAKER_ENDPOINT_NAME",
    )
    aws_access_key_id: str | None = Field(
        default=None,
        validation_alias="AWS_ACCESS_KEY_ID",
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        validation_alias="AWS_SECRET_ACCESS_KEY",
    )

    # CORS
    frontend_origin: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000",
        validation_alias="FRONTEND_ORIGIN",
    )

    # Retention
    detection_retention_days: int = Field(
        default=30,
        validation_alias="DETECTION_RETENTION_DAYS",
    )
    retention_cleanup_hours: int = Field(
        default=24,
        validation_alias="RETENTION_CLEANUP_HOURS",
    )

    # Edge Gateway (remote LAN camera ingestion)
    edge_gateway_token: str | None = Field(
        default=None,
        validation_alias="EDGE_GATEWAY_TOKEN",
    )
    edge_gateway_org_id: str | None = Field(
        default=None,
        validation_alias="EDGE_GATEWAY_ORG_ID",
    )
    mediamtx_publish_host: str | None = Field(
        default=None,
        validation_alias="MEDIAMTX_PUBLISH_HOST",
    )
    remote_edge_status_interval_seconds: int = Field(
        default=15,
        validation_alias="REMOTE_EDGE_STATUS_INTERVAL_SECONDS",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> object:
        if isinstance(value, str):
            clean = value.strip().lower()
            if clean in {"release", "prod", "production", "off", "no", "false", "0"}:
                return False
            if clean in {"debug", "dev", "development", "on", "yes", "true", "1"}:
                return True
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [orig.strip() for orig in self.frontend_origin.split(",") if orig.strip()]

    @property
    def edge_publish_host(self) -> str:
        """Public hostname/IP edge workers use to publish RTSP into MediaMTX."""
        if self.mediamtx_publish_host:
            return self.mediamtx_publish_host.strip()
        return self.mediamtx_host

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        is_prod = self.app_env == "production"
        if is_prod:
            if not self.jwt_secret or len(self.jwt_secret) < 32 or "dev_" in self.jwt_secret:
                raise ValueError("In production, JWT_SECRET must be at least 32 characters and non-default.")
            if not self.camera_encryption_key or "dev_" in self.camera_encryption_key:
                raise ValueError("In production, CAMERA_ENCRYPTION_KEY must be set securely.")
            object.__setattr__(self, "cookie_secure", True)
        return self


settings = Settings()
