"""Integration tests สำหรับ Auth API (register + login)"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine, SessionLocal, Store
from app.core.security import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    # Clear rate limiter storage between tests
    from app.api.auth import limiter
    try:
        limiter._limiter.storage.reset()
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# -- Register --

def test_register_success():
    r = client.post("/auth/register", json={"name": "MyShop", "username": "myshop", "password": "Shop1234"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "MyShop"
    assert data["username"] == "myshop"


def test_register_duplicate_username():
    client.post("/auth/register", json={"name": "A", "username": "dup", "password": "Test1234"})
    r = client.post("/auth/register", json={"name": "B", "username": "dup", "password": "Test1234"})
    assert r.status_code in (400, 409, 500)


def test_register_weak_password_short():
    r = client.post("/auth/register", json={"name": "X", "username": "x1", "password": "Ab1"})
    assert r.status_code == 400


def test_register_weak_password_digits_only():
    r = client.post("/auth/register", json={"name": "X", "username": "x2", "password": "12345678"})
    assert r.status_code == 400


def test_register_weak_password_alpha_only():
    r = client.post("/auth/register", json={"name": "X", "username": "x3", "password": "abcdefgh"})
    assert r.status_code == 400


# -- Login --

def test_login_success():
    client.post("/auth/register", json={"name": "LoginShop", "username": "loginshop", "password": "Login123"})
    r = client.post("/auth/login", json={"username": "loginshop", "password": "Login123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    client.post("/auth/register", json={"name": "S", "username": "s1", "password": "Good1234"})
    r = client.post("/auth/login", json={"username": "s1", "password": "Wrong999"})
    assert r.status_code == 401


def test_login_nonexistent_user():
    r = client.post("/auth/login", json={"username": "nobody", "password": "Test1234"})
    assert r.status_code == 401


def test_login_suspended_store():
    """Suspended stores should not be able to log in."""
    db = SessionLocal()
    store = Store(name="Suspended", username="sus1", hashed_password=hash_password("Test1234"), store_status="suspended")
    db.add(store)
    db.commit()
    db.close()
    r = client.post("/auth/login", json={"username": "sus1", "password": "Test1234"})
    # Should be blocked
    assert r.status_code in (401, 403)


def test_token_works_for_api():
    """Token from login should work to access protected endpoints."""
    client.post("/auth/register", json={"name": "Token", "username": "tokentest", "password": "Token123"})
    r = client.post("/auth/login", json={"username": "tokentest", "password": "Token123"})
    token = r.json()["access_token"]
    r2 = client.get("/members/", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
