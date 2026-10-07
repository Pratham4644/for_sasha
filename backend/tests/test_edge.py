from __future__ import annotations

import pytest

from backend.app.config import settings
from backend.app.models import Camera, CameraStatus, IngestionMode
from backend.app.services.ingestion import effective_ingestion_mode, is_private_source


@pytest.fixture(autouse=True)
def configure_edge_token(monkeypatch):
    monkeypatch.setattr(settings, "edge_gateway_token", "test-edge-token")
    monkeypatch.setattr(settings, "edge_gateway_org_id", "org-test-123")


def test_private_source_detection():
    assert is_private_source("rtsp://192.168.1.11:8080/h264.sdp") is True
    assert is_private_source("rtsp://10.0.0.5/stream") is True
    assert is_private_source("rtsp://camera.example.com/stream") is False


def test_effective_ingestion_mode_auto_remote_edge():
    camera = Camera(
        id="cam-1",
        organization_id="org-test-123",
        site_id="site-test-123",
        name="LAN Camera",
        source_url_template="rtsp://192.168.1.3:554/stream",
        media_path="cam_lan_1",
    )
    assert effective_ingestion_mode(camera) == IngestionMode.REMOTE_EDGE


def test_edge_config_requires_token(client):
    response = client.get("/api/v1/edge/config")
    assert response.status_code == 401


def test_edge_config_returns_private_cameras(client, setup_mock_db):
    sync_db = setup_mock_db
    camera = Camera(
        id="cam-edge-1",
        organization_id="org-test-123",
        site_id="site-test-123",
        name="Warehouse Cam",
        source_url_template="rtsp://192.168.1.11:8080/h264.sdp",
        media_path="cam_bf082f0e",
        ingestion_mode=IngestionMode.REMOTE_EDGE,
        enabled=True,
        status=CameraStatus.OFFLINE,
    )
    sync_db["cameras"].insert_one(camera.model_dump(mode="json"))

    response = client.get(
        "/api/v1/edge/config",
        headers={"Authorization": "Bearer test-edge-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_id"] == "org-test-123"
    assert len(payload["cameras"]) == 1
    assert payload["cameras"][0]["media_path"] == "cam_bf082f0e"
    assert payload["cameras"][0]["source_url"].startswith("rtsp://192.168.1.11")


def test_edge_config_excludes_paused_cameras(client, setup_mock_db):
    sync_db = setup_mock_db
    camera = Camera(
        id="cam-edge-2",
        organization_id="org-test-123",
        site_id="site-test-123",
        name="Paused Cam",
        source_url_template="rtsp://192.168.1.3:554/stream",
        media_path="cam_paused",
        ingestion_mode=IngestionMode.REMOTE_EDGE,
        enabled=True,
        stream_paused=True,
        status=CameraStatus.OFFLINE,
    )
    sync_db["cameras"].insert_one(camera.model_dump(mode="json"))

    response = client.get(
        "/api/v1/edge/config",
        headers={"Authorization": "Bearer test-edge-token"},
    )
    assert response.status_code == 200
    assert response.json()["cameras"] == []
