def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "version" in data


def test_health_probes(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert "database" in res.json()

    res_db = client.get("/health/database")
    assert res_db.status_code == 200

    res_ai = client.get("/health/ai")
    assert res_ai.status_code == 200
    assert res_ai.json()["enabled"] is True

    res_sys = client.get("/api/system/status")
    assert res_sys.status_code == 200
    assert "streaming" in res_sys.json()
