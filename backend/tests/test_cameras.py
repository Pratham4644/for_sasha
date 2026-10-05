import uuid


def test_camera_crud_lifecycle(client, admin_auth_headers):
    cam_id = f"cam_test_{uuid.uuid4().hex[:6]}"

    # 1. Create Camera
    create_payload = {
        "name": "Front Gate Test Camera",
        "camera_id": cam_id,
        "source_protocol": "RTSP",
        "source_url": "rtsp://192.168.1.100:554/live/ch0",
        "username": "admin",
        "password": "secretpassword",
        "configured_resolution": "1280x720",
        "configured_fps": 15.0,
        "enabled": True,
        "ai_enabled": True,
    }

    res = client.post("/api/cameras", json=create_payload, headers=admin_auth_headers)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["name"] == "Front Gate Test Camera"
    assert data["camera_id"] == cam_id
    # Ensure plain password is never exposed in response
    assert "password" not in data
    assert "secretpassword" not in str(data)

    # 2. Get Camera List
    list_res = client.get("/api/cameras", headers=admin_auth_headers)
    assert list_res.status_code == 200
    cameras = list_res.json()["data"]
    assert any(c["camera_id"] == cam_id for c in cameras)

    # 3. Get Single Camera
    get_res = client.get(f"/api/cameras/{cam_id}", headers=admin_auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["name"] == "Front Gate Test Camera"

    # 4. Update Camera
    update_res = client.patch(
        f"/api/cameras/{cam_id}",
        json={"name": "Updated Front Gate"},
        headers=admin_auth_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["data"]["name"] == "Updated Front Gate"

    # 5. Check Status
    status_res = client.get(f"/api/cameras/{cam_id}/status", headers=admin_auth_headers)
    assert status_res.status_code == 200
    assert "online" in status_res.json()["data"]

    # 6. Check Stream URLs
    stream_res = client.get(f"/api/cameras/{cam_id}/stream", headers=admin_auth_headers)
    assert stream_res.status_code == 200
    stream_data = stream_res.json()["data"]
    assert "webrtc" in stream_data["streams"]
    assert "hls" in stream_data["streams"]
    assert "webrtc_ai" in stream_data["streams"]

    # 7. Check Playback (WHEP)
    pb_res = client.get(f"/api/cameras/{cam_id}/playback", headers=admin_auth_headers)
    assert pb_res.status_code == 200
    pb_data = pb_res.json()["data"]
    assert "whep" in pb_data["whep_url"]
    assert pb_data["whep_ai_url"] is not None

    # 8. Delete Camera
    del_res = client.delete(f"/api/cameras/{cam_id}", headers=admin_auth_headers)
    assert del_res.status_code == 200

    # 9. Verify Deleted
    get_del = client.get(f"/api/cameras/{cam_id}", headers=admin_auth_headers)
    assert get_del.status_code == 404
