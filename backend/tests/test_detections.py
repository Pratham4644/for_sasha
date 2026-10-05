import uuid


def test_detections_pipeline(client, admin_auth_headers: dict):
    # 1. Create a dummy camera first
    cam_id = f"cam_det_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/cameras",
        json={
            "name": "Detection Test Cam",
            "camera_id": cam_id,
            "source_protocol": "RTSP",
            "source_url": "rtsp://127.0.0.1:8554/dummy",
        },
        headers=admin_auth_headers,
    )

    # 2. Ingest detection event
    event_payload = {
        "camera_id": cam_id,
        "class_name": "person",
        "confidence": 0.94,
        "bounding_box": [120.0, 150.0, 320.0, 480.0],
        "model_name": "yolo",
        "inference_latency_ms": 115.5,
    }

    ingest_res = client.post("/api/detection-events", json=event_payload, headers=admin_auth_headers)
    assert ingest_res.status_code == 201
    event_data = ingest_res.json()["data"]
    assert event_data["class_name"] == "person"
    assert event_data["confidence"] == 0.94
    event_id = event_data["id"]

    # 3. Query Detections with Filter
    list_res = client.get(
        "/api/detections",
        params={"camera_id": cam_id, "class_name": "person", "min_confidence": 0.8},
        headers=admin_auth_headers,
    )
    assert list_res.status_code == 200
    res_data = list_res.json()["data"]
    assert res_data["total"] >= 1
    assert any(item["id"] == event_id for item in res_data["items"])

    # 4. Get Single Detection
    get_res = client.get(f"/api/detections/{event_id}", headers=admin_auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == event_id

    # 5. Get Latest Detection for Camera
    latest_res = client.get(f"/api/cameras/{cam_id}/detections/latest", headers=admin_auth_headers)
    assert latest_res.status_code == 200
    latest = latest_res.json()["data"]
    assert latest is not None
    assert latest["camera_id"] == cam_id
    assert latest["class_name"] == "person"

    # 6. Test CSV Export
    csv_res = client.get("/api/detection-logs/export", params={"camera_id": cam_id}, headers=admin_auth_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "person" in csv_res.text

    # Cleanup camera
    client.delete(f"/api/cameras/{cam_id}", headers=admin_auth_headers)
