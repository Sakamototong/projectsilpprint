"""Integration tests สำหรับ Members CRUD API (full lifecycle)"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine, SessionLocal, Store
from app.core.security import create_access_token, hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_store(name="Shop1", username="shop1"):
    db = SessionLocal()
    store = Store(name=name, username=username, hashed_password=hash_password("Test1234"))
    db.add(store)
    db.commit()
    db.refresh(store)
    store_id = store.id
    db.close()
    token = create_access_token({"sub": str(store_id), "store_name": name})
    return {"Authorization": f"Bearer {token}"}, store_id


# -- list / paginate --

def test_list_members_empty():
    h, _ = _make_store()
    r = client.get("/members/", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


def test_list_members_pagination():
    h, _ = _make_store()
    for i in range(25):
        client.post("/members/", json={"name": f"M{i}", "phone": f"08{i:08d}"}, headers=h)
    r = client.get("/members/?page=1&page_size=10", headers=h)
    body = r.json()
    assert len(body["items"]) == 10
    assert body["total"] == 25
    assert body["page"] == 1

    r2 = client.get("/members/?page=3&page_size=10", headers=h)
    body2 = r2.json()
    assert len(body2["items"]) == 5
    assert body2["page"] == 3


def test_list_members_search():
    h, _ = _make_store()
    client.post("/members/", json={"name": "สมชาย", "phone": "0811111111"}, headers=h)
    client.post("/members/", json={"name": "สมหญิง", "phone": "0822222222"}, headers=h)
    r = client.get("/members/?q=สมชาย", headers=h)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "สมชาย"


def test_list_members_search_by_phone():
    h, _ = _make_store()
    client.post("/members/", json={"name": "Test", "phone": "0899887766"}, headers=h)
    r = client.get("/members/?q=089988", headers=h)
    assert r.json()["total"] == 1


# -- create --

def test_create_member():
    h, _ = _make_store()
    r = client.post("/members/", json={"name": "ทดสอบ", "phone": "0800000001"}, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "ทดสอบ"
    assert data["points"] == 0


def test_create_member_no_phone():
    h, _ = _make_store()
    r = client.post("/members/", json={"name": "NoPhone"}, headers=h)
    assert r.status_code == 200
    assert r.json()["phone"] is None


# -- update --

def test_update_member():
    h, _ = _make_store()
    cr = client.post("/members/", json={"name": "Old", "phone": "0801111111"}, headers=h)
    mid = cr.json()["id"]
    r = client.put(f"/members/{mid}", json={"name": "New", "tier": "gold"}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["tier"] == "gold"


def test_update_member_not_found():
    h, _ = _make_store()
    r = client.put("/members/9999", json={"name": "X"}, headers=h)
    assert r.status_code == 404


def test_update_partial():
    h, _ = _make_store()
    cr = client.post("/members/", json={"name": "A", "phone": "0801234567"}, headers=h)
    mid = cr.json()["id"]
    # update only phone, name should not change
    r = client.put(f"/members/{mid}", json={"phone": "0809999999"}, headers=h)
    assert r.json()["name"] == "A"
    assert r.json()["phone"] == "0809999999"


# -- delete --

def test_delete_member():
    h, _ = _make_store()
    cr = client.post("/members/", json={"name": "ToDelete"}, headers=h)
    mid = cr.json()["id"]
    r = client.delete(f"/members/{mid}", headers=h)
    assert r.status_code == 200
    assert r.json()["detail"] == "deleted"
    # confirm gone
    r2 = client.get(f"/members/{mid}", headers=h)
    assert r2.status_code == 404


def test_delete_member_not_found():
    h, _ = _make_store()
    r = client.delete("/members/9999", headers=h)
    assert r.status_code == 404


# -- store isolation --

def test_store_isolation():
    """Store A should not see Store B's members."""
    h_a, _ = _make_store("StoreA", "storea")
    h_b, _ = _make_store("StoreB", "storeb")
    cr = client.post("/members/", json={"name": "A-member"}, headers=h_a)
    mid = cr.json()["id"]
    # Store B cannot read A's member
    r = client.get(f"/members/{mid}", headers=h_b)
    assert r.status_code == 404
    # Store B cannot update A's member
    r = client.put(f"/members/{mid}", json={"name": "hack"}, headers=h_b)
    assert r.status_code == 404
    # Store B cannot delete A's member
    r = client.delete(f"/members/{mid}", headers=h_b)
    assert r.status_code == 404


# -- auth enforcement --

def test_no_auth_returns_error():
    r = client.get("/members/")
    assert r.status_code in (401, 403)


def test_invalid_token():
    r = client.get("/members/", headers={"Authorization": "Bearer invalid.token.here"})
    assert r.status_code in (401, 403)


def test_suspended_store_blocked():
    db = SessionLocal()
    store = Store(name="Bad", username="bad1", hashed_password=hash_password("Test1234"), store_status="suspended")
    db.add(store)
    db.commit()
    db.refresh(store)
    db.close()
    token = create_access_token({"sub": str(store.id), "store_name": "Bad"})
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/members/", headers=h)
    assert r.status_code == 403
