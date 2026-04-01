from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..models import Store
from .deps import get_db, get_current_store

router = APIRouter()


@router.get("/", response_model=schemas.PaginatedMembers)
def list_members(
    q: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    store: Store = Depends(get_current_store),
):
    query = db.query(models.Member).filter(models.Member.store_id == store.id)
    if q:
        query = query.filter(
            models.Member.name.ilike(f"%{q}%")
            | models.Member.phone.ilike(f"%{q}%")
            | models.Member.member_code.ilike(f"%{q}%")
        )
    total = query.count()
    members = query.order_by(models.Member.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": members, "total": total, "page": page, "page_size": page_size}


@router.post("/", response_model=schemas.MemberOut)
def create_member(m: schemas.MemberCreate, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    member = models.Member(name=m.name, phone=m.phone, store_id=store.id)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{member_id}", response_model=schemas.MemberOut)
def get_member(member_id: int, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    member = db.query(models.Member).filter(
        models.Member.id == member_id,
        models.Member.store_id == store.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.put("/{member_id}", response_model=schemas.MemberOut)
def update_member(member_id: int, m: schemas.MemberUpdate, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    member = db.query(models.Member).filter(
        models.Member.id == member_id,
        models.Member.store_id == store.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    for field, value in m.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
    member = db.query(models.Member).filter(
        models.Member.id == member_id,
        models.Member.store_id == store.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return {"detail": "deleted"}
