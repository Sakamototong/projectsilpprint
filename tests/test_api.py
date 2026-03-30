"""Integration tests สำหรับ API endpoints (ใช้ TestClient + SQLite in-memory)"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_member():
    r = client.post("/members/", json={"name": "สมหญิง", "phone": "0899998888"})
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 1
    assert data["points"] == 0

    r2 = client.get("/members/1")
    assert r2.status_code == 200
    assert r2.json()["phone"] == "0899998888"


def test_member_not_found():
    r = client.get("/members/999")
    assert r.status_code == 404


def test_create_transaction_with_member_earns_points():
    # สร้างสมาชิกก่อน
    client.post("/members/", json={"name": "ทดสอบ", "phone": "0811111111"})

    tx_body = {
        "terminal_id": "t1",
        "items": [{"name": "Fuel 95", "qty": 1, "price": 500.0}],
        "subtotal": 500.0,
        "tax": 0.0,
        "total": 500.0,
        "payment_method": "cash",
        "member_id": 1,
    }
    r = client.post("/transactions/", json=tx_body)
    assert r.status_code == 200
    assert r.json()["total"] == 500.0

    # ตรวจสอบ points สะสม
    m = client.get("/members/1").json()
    assert m["points"] == 500


def test_create_transaction_no_member():
    tx_body = {
        "terminal_id": "pump1",
        "items": [{"name": "Diesel", "qty": 2, "price": 300.0}],
        "subtotal": 600.0,
        "tax": 0.0,
        "total": 600.0,
        "payment_method": "cash",
        "member_id": None,
    }
    r = client.post("/transactions/", json=tx_body)
    assert r.status_code == 200
    assert r.json()["id"] == 1
