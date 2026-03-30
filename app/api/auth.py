from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..models import SessionLocal, Store
from ..core.security import hash_password, verify_password, create_access_token

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=schemas.StoreOut)
def register_store(data: schemas.StoreCreate, db: Session = Depends(get_db)):
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
def login(data: schemas.StoreLogin, db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.username == data.username).first()
    if not store or not verify_password(data.password, store.hashed_password):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    token = create_access_token({"sub": str(store.id), "store_name": store.name})
    return {"access_token": token, "token_type": "bearer"}
