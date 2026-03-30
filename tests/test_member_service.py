"""Unit tests สำหรับ MemberService"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Member
from app.services.member_service import MemberService

# ใช้ SQLite in-memory สำหรับ tests (ไม่ต้องการ Postgres)
engine = create_engine("sqlite:///:memory:")
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


def test_points_for_amount():
    assert MemberService.points_for_amount(1100.0) == 1100
    assert MemberService.points_for_amount(0) == 0
    assert MemberService.points_for_amount(99.9) == 99


def test_add_points_accumulate(db):
    member = Member(name="ทดสอบ", phone="0800000001")
    db.add(member)
    db.commit()
    db.refresh(member)

    updated = MemberService.add_points(db, member.id, 500)
    assert updated.points == 500

    updated = MemberService.add_points(db, member.id, 200)
    assert updated.points == 700


def test_add_points_member_not_found(db):
    result = MemberService.add_points(db, 9999, 100)
    assert result is None
