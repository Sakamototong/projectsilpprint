from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from .. import schemas
from ..models import Store
from ..core.security import hash_password, verify_password, create_access_token, validate_password
from .deps import get_db

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=schemas.StoreOut)
@limiter.limit("5/minute")
def register_store(request: Request, data: schemas.StoreCreate, db: Session = Depends(get_db)):
    pwd_error = validate_password(data.password)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)
    if db.query(Store).filter(Store.username == data.username).first():
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้มีอยู่แล้ว")
    store = Store(
        name=data.name,
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.post("/login", response_model=schemas.Token)
@limiter.limit("10/minute")
def login(request: Request, data: schemas.StoreLogin, db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.username == data.username).first()
    if not store or not verify_password(data.password, store.hashed_password):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if getattr(store, "store_status", "active") in ("rejected", "suspended"):
        raise HTTPException(status_code=403, detail="บัญชีร้านค้าถูกระงับ")
    token = create_access_token({"sub": str(store.id), "store_name": store.name})
    return {"access_token": token, "token_type": "bearer"}
