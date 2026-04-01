import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..models import Store
from ..services.receipt_service import ReceiptService
from ..services.member_service import MemberService
from .deps import get_db, get_current_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=schemas.TransactionOut)
def create_transaction(tx: schemas.TransactionCreate, db: Session = Depends(get_db), store: Store = Depends(get_current_store)):
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
        logger.exception("TCP printer failed for transaction %s", db_tx.id)

    return db_tx
