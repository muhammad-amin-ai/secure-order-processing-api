import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.security import hash_password  # noqa: E402

TEST_DB_URL = "sqlite:///./test_order_api.db"


@pytest.fixture(scope="function")
def db_session():
    """Fresh, isolated SQLite database for every single test function."""
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        if os.path.exists("./test_order_api.db"):
            os.remove("./test_order_api.db")


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register_and_login(client, email, password="Password123", full_name="Test User"):
    client.post("/auth/register", json={"email": email, "password": password, "full_name": full_name})
    resp = client.post("/auth/login", data={"username": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def customer_auth_headers(client):
    return _register_and_login(client, "customer@example.com")


@pytest.fixture
def admin_auth_headers(client, db_session):
    headers = _register_and_login(client, "admin@example.com", full_name="Admin User")
    # Promote to admin directly in the DB (no public "become admin" endpoint by design).
    user = db_session.query(models.User).filter(models.User.email == "admin@example.com").first()
    user.role = models.UserRole.ADMIN
    db_session.commit()
    # Re-login so the JWT's embedded role claim reflects the promotion.
    resp = client.post("/auth/login", data={"username": "admin@example.com", "password": "Password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
