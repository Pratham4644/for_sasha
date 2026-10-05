import uuid


def test_auth_flow(client):
    random_str = uuid.uuid4().hex[:6]
    email = f"user_{random_str}@example.com"
    password = "SecurePassword123!"

    # 1. Register
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Test Operator",
            "organization_name": f"Org_{random_str}",
        },
    )
    assert reg_res.status_code == 201
    user_data = reg_res.json()["data"]
    assert user_data["email"] == email
    token = user_data["token"]
    assert token is not None

    # 2. Get Me using Bearer Token
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["data"]["email"] == email

    # 3. Login
    login_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    assert login_res.json()["data"]["token"] is not None

    # 4. Invalid Password
    bad_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 5. Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
