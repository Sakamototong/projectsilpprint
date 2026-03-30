from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..models import SessionLocal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=schemas.MemberOut)
def create_member(m: schemas.MemberCreate, db: Session = Depends(get_db)):
    member = models.Member(name=m.name, phone=m.phone)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{member_id}", response_model=schemas.MemberOut)
def get_member(member_id: int, db: Session = Depends(get_db)):
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member
