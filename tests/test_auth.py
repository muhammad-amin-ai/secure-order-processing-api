def test_register_creates_user(client):
    resp = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "Password123", "full_name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "customer"
    assert "hashed_password" not in body  # never leak password hashes


def test_register_duplicate_email_rejected(client):
    client.post("/auth/register", json={"email": "bob@example.com", "password": "Password123"})
    resp = client.post("/auth/register", json={"email": "bob@example.com", "password": "Password123"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_rejects_weak_password(client):
    resp = client.post("/auth/register", json={"email": "weak@example.com", "password": "alllettersnodigits"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_success_returns_token(client):
    client.post("/auth/register", json={"email": "carol@example.com", "password": "Password123"})
    resp = client.post("/auth/login", data={"username": "carol@example.com", "password": "Password123"})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert len(resp.json()["access_token"]) > 10


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "dave@example.com", "password": "Password123"})
    resp = client.post("/auth/login", data={"username": "dave@example.com", "password": "WrongPass1"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_LOGIN"


def test_protected_endpoint_requires_token(client):
    resp = client.get("/customers/me")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client):
    resp = client.get("/customers/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_returns_current_user(client, customer_auth_headers):
    resp = client.get("/customers/me", headers=customer_auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "customer@example.com"
