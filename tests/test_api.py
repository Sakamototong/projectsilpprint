"""Integration tests สำหรับ API endpoints (ใช้ TestClient + SQLite in-memory)"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine
from app.core.security import create_access_token, hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _create_test_store(db_session):
    """Create a store directly in DB and return an auth header."""
    from app.models import Store, SessionLocal
    db = SessionLocal()
    store = Store(name="TestStore", username="testuser", hashed_password=hash_password("Test1234"))
    db.add(store)
    db.commit()
    db.refresh(store)
    db.close()
    token = create_access_token({"sub": str(store.id), "store_name": store.name})
    return {"Authorization": f"Bearer {token}"}, store.id


@pytest.fixture
def auth():
    """Return (headers, store_id) for authenticated requests."""
    return _create_test_store(None)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_member(auth):
    headers, _ = auth
    r = client.post("/members/", json={"name": "สมหญิง", "phone": "0899998888"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] >= 1
    assert data["points"] == 0

    r2 = client.get(f"/members/{data['id']}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["phone"] == "0899998888"


def test_member_not_found(auth):
    headers, _ = auth
    r = client.get("/members/999", headers=headers)
    assert r.status_code == 404


def test_member_requires_auth():
    r = client.get("/members/1")
    assert r.status_code in (401, 403)


def test_create_transaction_with_member_earns_points(auth):
    headers, _ = auth
    # สร้างสมาชิกก่อน
    mr = client.post("/members/", json={"name": "ทดสอบ", "phone": "0811111111"}, headers=headers)
    member_id = mr.json()["id"]

    tx_body = {
        "terminal_id": "t1",
        "items": [{"name": "Fuel 95", "qty": 1, "price": 500.0}],
        "subtotal": 500.0,
        "tax": 0.0,
        "total": 500.0,
        "payment_method": "cash",
        "member_id": member_id,
    }
    r = client.post("/transactions/", json=tx_body, headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 500.0

    # ตรวจสอบ points สะสม
    m = client.get(f"/members/{member_id}", headers=headers).json()
    assert m["points"] == 5


def test_create_transaction_no_member(auth):
    headers, _ = auth
    tx_body = {
        "terminal_id": "pump1",
        "items": [{"name": "Diesel", "qty": 2, "price": 300.0}],
        "subtotal": 600.0,
        "tax": 0.0,
        "total": 600.0,
        "payment_method": "cash",
        "member_id": None,
    }
    r = client.post("/transactions/", json=tx_body, headers=headers)
    assert r.status_code == 200


def test_register_password_validation():
    # Too short
    r = client.post("/auth/register", json={"name": "Test", "username": "user1", "password": "123"})
    assert r.status_code == 400

    # All digits
    r = client.post("/auth/register", json={"name": "Test", "username": "user1", "password": "12345678"})
    assert r.status_code == 400

    # Valid
    r = client.post("/auth/register", json={"name": "Test", "username": "user1", "password": "Test1234"})
    assert r.status_code == 200


def test_login_and_token():
    # Register first
    client.post("/auth/register", json={"name": "Shop", "username": "shop1", "password": "Shop1234"})
    r = client.post("/auth/login", json={"username": "shop1", "password": "Shop1234"})
    assert r.status_code == 200
    assert "access_token" in r.json()
