"""Integration tests สำหรับ Transactions API"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine, SessionLocal, Store, Member
from app.core.security import create_access_token, hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_store():
    db = SessionLocal()
    store = Store(name="TxShop", username="txshop", hashed_password=hash_password("Test1234"))
    db.add(store)
    db.commit()
    db.refresh(store)
    sid = store.id
    db.close()
    token = create_access_token({"sub": str(sid), "store_name": "TxShop"})
    return {"Authorization": f"Bearer {token}"}, sid


def _make_member(store_id):
    db = SessionLocal()
    m = Member(name="TxMember", phone="0800000001", store_id=store_id)
    db.add(m)
    db.commit()
    db.refresh(m)
    mid = m.id
    db.close()
    return mid


def _tx_body(member_id=None, total=1000.0):
    return {
        "terminal_id": "pump1",
        "items": [{"name": "Fuel 95", "qty": 1, "price": total}],
        "subtotal": total,
        "tax": 0.0,
        "total": total,
        "payment_method": "cash",
        "member_id": member_id,
    }


@patch("app.api.transactions.ReceiptService.print_to_tcp")
def test_create_transaction_basic(mock_tcp):
    h, sid = _make_store()
    r = client.post("/transactions/", json=_tx_body(), headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1000.0
    assert data["id"] >= 1


@patch("app.api.transactions.ReceiptService.print_to_tcp")
def test_transaction_awards_points(mock_tcp):
    h, sid = _make_store()
    mid = _make_member(sid)
    r = client.post("/transactions/", json=_tx_body(member_id=mid, total=500.0), headers=h)
    assert r.status_code == 200
    # 500 / 100 = 5 points
    m = client.get(f"/members/{mid}", headers=h).json()
    assert m["points"] == 5


@patch("app.api.transactions.ReceiptService.print_to_tcp")
def test_transaction_points_accumulate(mock_tcp):
    h, sid = _make_store()
    mid = _make_member(sid)
    client.post("/transactions/", json=_tx_body(member_id=mid, total=200.0), headers=h)
    client.post("/transactions/", json=_tx_body(member_id=mid, total=300.0), headers=h)
    m = client.get(f"/members/{mid}", headers=h).json()
    assert m["points"] == 5  # 2 + 3


@patch("app.api.transactions.ReceiptService.print_to_tcp")
def test_transaction_no_member_no_points(mock_tcp):
    h, _ = _make_store()
    r = client.post("/transactions/", json=_tx_body(member_id=None), headers=h)
    assert r.status_code == 200


@patch("app.api.transactions.ReceiptService.print_to_tcp", side_effect=ConnectionRefusedError)
def test_tcp_printer_failure_non_fatal(mock_tcp):
    """Printer failure should not cause 500."""
    h, _ = _make_store()
    r = client.post("/transactions/", json=_tx_body(), headers=h)
    assert r.status_code == 200


def test_transaction_requires_auth():
    r = client.post("/transactions/", json=_tx_body())
    assert r.status_code in (401, 403)
