from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..models import SessionLocal
from ..services.receipt_service import ReceiptService
from ..services.member_service import MemberService

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=schemas.TransactionOut)
def create_transaction(tx: schemas.TransactionCreate, db: Session = Depends(get_db)):
    db_tx = models.Transaction(total=tx.total, terminal_id=tx.terminal_id, payment_method=tx.payment_method, raw=tx.model_dump())
    if tx.member_id:
        db_tx.member_id = tx.member_id
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    # render and save receipt (sync for now)
    receipt_path = ReceiptService.render_and_save(db_tx.id, tx.model_dump())

    # store receipt record
    receipt = models.Receipt(transaction_id=db_tx.id, content_path=receipt_path, raw_payload={})
    db.add(receipt)
    db.commit()

    # award points to member if present
    if tx.member_id:
        points = MemberService.points_for_amount(tx.total)
        MemberService.add_points(db, tx.member_id, points)

    # try to send to configured TCP printer (simulator)
    try:
        ReceiptService.print_to_tcp(db_tx.id, tx.model_dump())
    except Exception:
        # do not fail the transaction if printing fails; just log
        pass

    return db_tx
