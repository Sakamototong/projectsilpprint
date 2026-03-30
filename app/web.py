from pathlib import Path
from typing import Optional
import json

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .models import SessionLocal, Store, Member, Transaction, Receipt, BillingProfile, Product, StaffUser
from .core.security import hash_password, verify_password, create_access_token, decode_token
from .services.member_service import MemberService

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


# ──────────────────────────────────────────
# Thai baht number-to-words helper
# ──────────────────────────────────────────
def thai_baht_text(amount: float) -> str:
    _ones = ['', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']

    def _digits(n: int) -> str:
        if n == 0:
            return 'ศูนย์'
        if n >= 1_000_000:
            return _digits(n // 1_000_000) + 'ล้าน' + (_digits(n % 1_000_000) if n % 1_000_000 else '')
        result = ''
        for level in range(5, -1, -1):
            digit = (n // (10 ** level)) % 10
            if digit == 0:
                continue
            if level == 1:
                if digit == 1:
                    result += 'สิบ'
                elif digit == 2:
                    result += 'ยี่สิบ'
                else:
                    result += _ones[digit] + 'สิบ'
            elif level == 0 and n >= 10 and digit == 1:
                result += 'เอ็ด'
            else:
                units = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']
                result += _ones[digit] + units[level]
        return result

    amount = round(float(amount), 2)
    baht_int = int(amount)
    satang = round((amount - baht_int) * 100)
    result = _digits(baht_int) + 'บาท'
    if satang:
        result += _digits(satang) + 'สตางค์'
    else:
        result += 'ถ้วน'
    return result


# ──────────────────────────────────────────
# DB helper
# ──────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────
# Auth helper: ดึง Store จาก cookie JWT
# ──────────────────────────────────────────
def _get_store(request: Request, db: Session) -> Optional[Store]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        store_id = int(payload.get("sub", 0))
        return db.query(Store).filter(Store.id == store_id).first()
    except Exception:
        return None


def _get_products(db: Session, store_id: int):
    return db.query(Product).filter(Product.store_id == store_id, Product.is_active == True).all()


# ──────────────────────────────────────────
# Login / Logout
# ──────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    store = db.query(Store).filter(Store.username == username).first()
    if store and verify_password(password, store.hashed_password):
        token = create_access_token({"sub": str(store.id), "store_name": store.name})
    else:
        # ลองค้นหาจาก StaffUser
        staff = db.query(StaffUser).filter(
            StaffUser.username == username,
            StaffUser.is_active == True,
        ).first()
        if not staff or not verify_password(password, staff.hashed_password):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"},
            )
        token = create_access_token({"sub": str(staff.store_id), "store_name": staff.store.name})
    resp = RedirectResponse("/web/members", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=28800)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp


# ──────────────────────────────────────────
# ลงทะเบียนร้านค้าใหม่
# ──────────────────────────────────────────
@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.post("/register")
def register_post(
    request: Request,
    store_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "รหัสผ่านไม่ตรงกัน"},
        )
    if db.query(Store).filter(Store.username == username).first():
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "ชื่อผู้ใช้นี้มีอยู่แล้ว"},
        )
    store = Store(
        name=store_name,
        username=username,
        hashed_password=hash_password(password),
    )
    db.add(store)
    db.commit()
    return RedirectResponse("/web/login?registered=1", status_code=302)


# ──────────────────────────────────────────
# รายชื่อสมาชิก
# ──────────────────────────────────────────
@router.get("/members", response_class=HTMLResponse)
def members_page(
    request: Request,
    q: str = None,
    enrolled: str = None,
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)

    query = db.query(Member).filter(Member.store_id == store.id)
    if q:
        query = query.filter(
            Member.name.ilike(f"%{q}%")
            | Member.phone.ilike(f"%{q}%")
            | Member.member_code.ilike(f"%{q}%")
        )
    members = query.order_by(Member.id.desc()).all()
    return templates.TemplateResponse(
        request,
        "members.html",
        {
            "store_name": store.name,
            "members": members,
            "total": len(members),
            "q": q or "",
            "enrolled": enrolled,
        },
    )


# ──────────────────────────────────────────
# สมัครสมาชิก
# ──────────────────────────────────────────
@router.get("/enroll", response_class=HTMLResponse)
def enroll_page(request: Request, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    return templates.TemplateResponse(
        request, "enroll.html", {"store_name": store.name}
    )


@router.post("/enroll")
def enroll_post(
    request: Request,
    name: str = Form(...),
    phone: str = Form(None),
    email: str = Form(None),
    member_code: str = Form(None),
    birthdate: str = Form(None),
    tier: str = Form("general"),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)

    # ตรวจสอบเบอร์ซ้ำในร้านเดียวกัน
    if phone:
        existing = (
            db.query(Member)
            .filter(Member.phone == phone, Member.store_id == store.id)
            .first()
        )
        if existing:
            return templates.TemplateResponse(
                request,
                "enroll.html",
                {
                    "store_name": store.name,
                    "error": f"เบอร์ {phone} มีอยู่ในระบบแล้ว",
                    "form": {
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "birthdate": birthdate,
                        "tier": tier,
                    },
                },
            )

    member = Member(
        name=name,
        phone=phone or None,
        email=email or None,
        birthdate=birthdate or None,
        tier=tier,
        store_id=store.id,
    )
    db.add(member)
    db.flush()  # รับ id ก่อน commit

    # สร้างรหัสสมาชิกอัตโนมัติถ้าไม่ได้กรอกมา
    member.member_code = member_code.strip() if member_code and member_code.strip() else f"M{store.id:04d}{member.id:07d}"
    db.commit()

    return RedirectResponse(f"/web/members?enrolled=1", status_code=302)


# ──────────────────────────────────────────
# รายละเอียดสมาชิก
# ──────────────────────────────────────────
@router.get("/members/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, member_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.store_id == store.id)
        .first()
    )
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    receipts = (
        db.query(Receipt)
        .join(Transaction)
        .filter(Transaction.member_id == member_id)
        .order_by(Receipt.printed_at.desc())
        .limit(20)
        .all()
    )
    billing_profiles = db.query(BillingProfile).filter(BillingProfile.member_id == member_id).all()
    return templates.TemplateResponse(
        request,
        "member_detail.html",
        {"store_name": store.name, "member": member, "receipts": receipts, "billing_profiles": billing_profiles},
    )


# ──────────────────────────────────────────
# ออกบิล / ใบเสร็จ
# ──────────────────────────────────────────
@router.get("/members/{member_id}/new-bill", response_class=HTMLResponse)
def new_bill_page(request: Request, member_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.store_id == store.id)
        .first()
    )
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    billing_profiles = db.query(BillingProfile).filter(BillingProfile.member_id == member_id).all()
    products = _get_products(db, store.id)
    return templates.TemplateResponse(
        request, "new_bill.html", {
            "store_name": store.name,
            "store": store,
            "member": member,
            "billing_profiles": billing_profiles,
            "products": products,
        }
    )


@router.post("/members/{member_id}/new-bill")
def new_bill_post(
    request: Request,
    member_id: int,
    items_json: str = Form(...),
    payment_method: str = Form("cash"),
    note: str = Form(""),
    billing_profile_id: str = Form(""),
    vat_type: str = Form("none"),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.store_id == store.id)
        .first()
    )
    if not member:
        return RedirectResponse("/web/members", status_code=302)

    items = json.loads(items_json)
    item_total = sum(float(i["qty"]) * float(i["price"]) for i in items)
    vat_rate = store.vat_rate or 7.0

    # VAT: none / exclusive (บวกเพิ่ม) / inclusive (รวมอยู่แล้ว)
    if vat_type == "exclusive":
        subtotal = round(item_total, 2)
        vat_amount = round(subtotal * vat_rate / 100, 2)
        total = round(subtotal + vat_amount, 2)
    elif vat_type == "inclusive":
        total = round(item_total, 2)
        subtotal = round(total / (1 + vat_rate / 100), 2)
        vat_amount = round(total - subtotal, 2)
    else:  # none
        subtotal = round(item_total, 2)
        vat_amount = 0.0
        vat_rate = 0.0
        total = subtotal

    points_earned = MemberService.points_for_amount(total)

    # Billing profile
    bp = None
    if billing_profile_id:
        try:
            bp = db.query(BillingProfile).filter(
                BillingProfile.id == int(billing_profile_id),
                BillingProfile.member_id == member_id,
            ).first()
        except (ValueError, Exception):
            pass

    tx = Transaction(
        total=total,
        payment_method=payment_method,
        member_id=member_id,
        terminal_id="web",
        raw={"items": items, "subtotal": subtotal, "vat_amount": vat_amount,
             "vat_rate": vat_rate, "vat_type": vat_type, "total": total,
             "payment_method": payment_method, "note": note},
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    receipt = Receipt(
        transaction_id=tx.id,
        raw_payload={
            "items": items,
            "subtotal": subtotal,
            "vat_amount": vat_amount,
            "vat_rate": vat_rate,
            "vat_type": vat_type,
            "total": total,
            "payment_method": payment_method,
            "note": note,
            "points_earned": points_earned,
            "billing_profile": {
                "company_name": bp.company_name if bp else None,
                "tax_id": bp.tax_id if bp else None,
                "address": bp.address if bp else None,
                "phone": bp.phone if bp else None,
                "label": bp.label if bp else None,
            } if bp else None,
        },
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    MemberService.add_points(db, member_id, points_earned)

    return RedirectResponse(f"/web/receipts/{receipt.id}", status_code=302)


@router.get("/receipts/{receipt_id}", response_class=HTMLResponse)
def receipt_view(request: Request, receipt_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        return RedirectResponse("/web/members", status_code=302)
    tx = receipt.transaction
    member = None
    if tx and tx.member_id:
        member = (
            db.query(Member)
            .filter(Member.id == tx.member_id, Member.store_id == store.id)
            .first()
        )
        if not member:
            return RedirectResponse("/web/members", status_code=302)
    payload = receipt.raw_payload or {}
    points_earned = payload.get("points_earned", 0)
    amount_text = thai_baht_text(payload.get("total", 0))
    return templates.TemplateResponse(
        request,
        "receipt_view.html",
        {
            "store_name": store.name,
            "store": store,
            "receipt": receipt,
            "transaction": tx,
            "member": member,
            "payload": payload,
            "points_earned": points_earned,
            "amount_text": amount_text,
        },
    )


# ──────────────────────────────────────────
# แก้ไข / ลบ ใบเสร็จ
# ──────────────────────────────────────────
@router.get("/receipts/{receipt_id}/edit", response_class=HTMLResponse)
def receipt_edit_page(request: Request, receipt_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        return RedirectResponse("/web/members", status_code=302)
    tx = receipt.transaction
    member = None
    if tx and tx.member_id:
        member = db.query(Member).filter(Member.id == tx.member_id, Member.store_id == store.id).first()
        if not member:
            return RedirectResponse("/web/members", status_code=302)
    payload = receipt.raw_payload or {}
    billing_profiles = db.query(BillingProfile).filter(BillingProfile.member_id == tx.member_id).all() if tx else []
    products = _get_products(db, store.id)
    return templates.TemplateResponse(request, "receipt_edit.html", {
        "store_name": store.name,
        "store": store,
        "receipt": receipt,
        "member": member,
        "payload": payload,
        "billing_profiles": billing_profiles,
        "products": products,
    })


@router.post("/receipts/{receipt_id}/edit")
def receipt_edit_post(
    request: Request,
    receipt_id: int,
    items_json: str = Form(...),
    payment_method: str = Form("cash"),
    note: str = Form(""),
    billing_profile_id: str = Form(""),
    vat_type: str = Form("none"),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        return RedirectResponse("/web/members", status_code=302)
    tx = receipt.transaction
    member = db.query(Member).filter(Member.id == tx.member_id, Member.store_id == store.id).first() if tx else None
    if not member:
        return RedirectResponse("/web/members", status_code=302)

    # Reverse old points
    old_points = (receipt.raw_payload or {}).get("points_earned", 0)
    MemberService.add_points(db, member.id, -old_points)

    items = json.loads(items_json)
    item_total = sum(float(i["qty"]) * float(i["price"]) for i in items)
    vat_rate = store.vat_rate or 7.0
    if vat_type == "exclusive":
        subtotal = round(item_total, 2)
        vat_amount = round(subtotal * vat_rate / 100, 2)
        total = round(subtotal + vat_amount, 2)
    elif vat_type == "inclusive":
        total = round(item_total, 2)
        subtotal = round(total / (1 + vat_rate / 100), 2)
        vat_amount = round(total - subtotal, 2)
    else:
        subtotal = round(item_total, 2)
        vat_amount = 0.0
        vat_rate = 0.0
        total = subtotal

    points_earned = MemberService.points_for_amount(total)

    bp = None
    if billing_profile_id:
        try:
            bp = db.query(BillingProfile).filter(
                BillingProfile.id == int(billing_profile_id),
                BillingProfile.member_id == member.id,
            ).first()
        except (ValueError, Exception):
            pass

    # Update transaction
    tx.total = total
    tx.payment_method = payment_method
    tx.raw = {"items": items, "subtotal": subtotal, "vat_amount": vat_amount,
              "vat_rate": vat_rate, "vat_type": vat_type, "total": total,
              "payment_method": payment_method, "note": note}
    # Update receipt
    receipt.raw_payload = {
        "items": items, "subtotal": subtotal, "vat_amount": vat_amount,
        "vat_rate": vat_rate, "vat_type": vat_type, "total": total,
        "payment_method": payment_method, "note": note,
        "points_earned": points_earned,
        "billing_profile": {
            "company_name": bp.company_name if bp else None,
            "tax_id": bp.tax_id if bp else None,
            "address": bp.address if bp else None,
            "phone": bp.phone if bp else None,
            "label": bp.label if bp else None,
        } if bp else None,
    }
    db.add(tx)
    db.add(receipt)
    db.commit()

    MemberService.add_points(db, member.id, points_earned)

    return RedirectResponse(f"/web/receipts/{receipt_id}", status_code=302)


@router.post("/receipts/{receipt_id}/delete")
def receipt_delete(request: Request, receipt_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        return RedirectResponse("/web/members", status_code=302)
    tx = receipt.transaction
    member_id = tx.member_id if tx else None
    # Reverse points
    old_points = (receipt.raw_payload or {}).get("points_earned", 0)
    if member_id and old_points:
        MemberService.add_points(db, member_id, -old_points)
    db.delete(receipt)
    if tx:
        db.delete(tx)
    db.commit()
    if member_id:
        return RedirectResponse(f"/web/members/{member_id}", status_code=302)
    return RedirectResponse("/web/members", status_code=302)


# ──────────────────────────────────────────
# แก้ไขข้อมูลสมาชิก
# ──────────────────────────────────────────
@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
def member_edit_page(request: Request, member_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = db.query(Member).filter(Member.id == member_id, Member.store_id == store.id).first()
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    receipts_count = (
        db.query(Receipt)
        .join(Transaction)
        .filter(Transaction.member_id == member_id)
        .count()
    )
    return templates.TemplateResponse(request, "edit_member.html", {
        "store_name": store.name, "member": member, "receipts_count": receipts_count,
    })


@router.post("/members/{member_id}/edit")
def member_edit_post(
    request: Request,
    member_id: int,
    name: str = Form(...),
    phone: str = Form(None),
    email: str = Form(None),
    member_code: str = Form(None),
    birthdate: str = Form(None),
    tier: str = Form("general"),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = db.query(Member).filter(Member.id == member_id, Member.store_id == store.id).first()
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    # ตรวจสอบเบอร์ซ้ำ (ยกเว้นตัวเอง)
    if phone:
        dup = db.query(Member).filter(
            Member.phone == phone,
            Member.store_id == store.id,
            Member.id != member_id,
        ).first()
        if dup:
            return templates.TemplateResponse(request, "edit_member.html", {
                "store_name": store.name,
                "member": member,
                "error": f"เบอร์ {phone} มีอยู่ในระบบแล้ว (สมาชิก {dup.name})",
            })
    member.name = name
    member.phone = phone or None
    member.email = email or None
    member.member_code = member_code.strip() if member_code and member_code.strip() else member.member_code
    member.birthdate = birthdate or None
    member.tier = tier
    db.commit()
    return RedirectResponse(f"/web/members/{member_id}?updated=1", status_code=302)


@router.post("/members/{member_id}/delete")
def member_delete(request: Request, member_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = db.query(Member).filter(Member.id == member_id, Member.store_id == store.id).first()
    if member:
        # ลบใบเสร็จและ transaction ที่เกี่ยวข้อง
        txs = db.query(Transaction).filter(Transaction.member_id == member_id).all()
        for tx in txs:
            db.query(Receipt).filter(Receipt.transaction_id == tx.id).delete()
        db.query(Transaction).filter(Transaction.member_id == member_id).delete()
        db.query(BillingProfile).filter(BillingProfile.member_id == member_id).delete()
        db.delete(member)
        db.commit()
    return RedirectResponse("/web/members?deleted=1", status_code=302)


# ──────────────────────────────────────────
# เพิ่มคะแนนด้วยมือ (staff action)
# ──────────────────────────────────────────
@router.post("/members/{member_id}/add-points")
def add_points_post(
    request: Request,
    member_id: int,
    points: int = Form(...),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.store_id == store.id)
        .first()
    )
    if member:
        member.points = (member.points or 0) + points
        db.commit()
    return RedirectResponse(f"/web/members/{member_id}?updated=1", status_code=302)


# ──────────────────────────────────────────
# ที่อยู่ออกบิล (Billing Profiles) ของสมาชิก
# ──────────────────────────────────────────
@router.get("/members/{member_id}/billing-profiles", response_class=HTMLResponse)
def billing_profiles_page(request: Request, member_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = db.query(Member).filter(Member.id == member_id, Member.store_id == store.id).first()
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    profiles = db.query(BillingProfile).filter(BillingProfile.member_id == member_id).all()
    return templates.TemplateResponse(request, "billing_profiles.html", {
        "store_name": store.name, "member": member, "profiles": profiles,
    })


@router.post("/members/{member_id}/billing-profiles")
def billing_profiles_post(
    request: Request, member_id: int,
    label: str = Form(...),
    company_name: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    is_default: str = Form(""),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    member = db.query(Member).filter(Member.id == member_id, Member.store_id == store.id).first()
    if not member:
        return RedirectResponse("/web/members", status_code=302)
    if is_default:
        db.query(BillingProfile).filter(BillingProfile.member_id == member_id).update({"is_default": False})
    bp = BillingProfile(
        member_id=member_id, label=label,
        company_name=company_name or None, tax_id=tax_id or None,
        address=address or None, phone=phone or None,
        email=email or None, is_default=bool(is_default),
    )
    db.add(bp)
    db.commit()
    return RedirectResponse(f"/web/members/{member_id}?saved=1", status_code=302)


@router.post("/members/{member_id}/billing-profiles/{bp_id}/delete")
def billing_profile_delete(request: Request, member_id: int, bp_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    bp = db.query(BillingProfile).filter(BillingProfile.id == bp_id, BillingProfile.member_id == member_id).first()
    if bp:
        db.delete(bp)
        db.commit()
    return RedirectResponse(f"/web/members/{member_id}", status_code=302)


# ──────────────────────────────────────────
# ตั้งค่าร้านค้า (Store Settings)
# ──────────────────────────────────────────
@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    staff_list = db.query(StaffUser).filter(StaffUser.store_id == store.id).all()
    return templates.TemplateResponse(request, "store_settings.html", {
        "store_name": store.name, "store": store, "staff_list": staff_list,
    })


@router.post("/settings/profile")
def settings_profile_post(
    request: Request,
    store_name: str = Form(...),
    address: str = Form(""),
    tax_id: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    vat_rate: float = Form(7.0),
    include_vat: str = Form(""),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    store.name = store_name
    store.address = address or None
    store.tax_id = tax_id or None
    store.phone = phone or None
    store.email = email or None
    store.vat_rate = vat_rate
    store.include_vat = bool(include_vat)
    db.commit()
    return RedirectResponse("/web/settings?saved=1", status_code=302)


@router.post("/settings/staff/add")
def settings_staff_add(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    if db.query(StaffUser).filter(StaffUser.username == username).first() or \
       db.query(Store).filter(Store.username == username).first():
        staff_list = db.query(StaffUser).filter(StaffUser.store_id == store.id).all()
        return templates.TemplateResponse(request, "store_settings.html", {
            "store_name": store.name, "store": store, "staff_list": staff_list,
            "staff_error": f"username '{username}' ถูกใช้งานแล้ว",
        })
    su = StaffUser(store_id=store.id, name=name, username=username, hashed_password=hash_password(password))
    db.add(su)
    db.commit()
    return RedirectResponse("/web/settings?staff_added=1", status_code=302)


@router.post("/settings/staff/{staff_id}/delete")
def settings_staff_delete(request: Request, staff_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    su = db.query(StaffUser).filter(StaffUser.id == staff_id, StaffUser.store_id == store.id).first()
    if su:
        db.delete(su)
        db.commit()
    return RedirectResponse("/web/settings", status_code=302)


# ──────────────────────────────────────────
# รายการสินค้า (Products)
# ──────────────────────────────────────────
@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    products = db.query(Product).filter(Product.store_id == store.id).order_by(Product.category, Product.name).all()
    return templates.TemplateResponse(request, "products.html", {
        "store_name": store.name, "products": products,
    })


@router.post("/products/add")
def product_add(
    request: Request,
    name: str = Form(...),
    unit: str = Form("ลิตร"),
    price: float = Form(0.0),
    category: str = Form("fuel"),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    p = Product(store_id=store.id, name=name, unit=unit, price=price, category=category)
    db.add(p)
    db.commit()
    return RedirectResponse("/web/products?saved=1", status_code=302)


@router.post("/products/{product_id}/edit")
def product_edit(
    request: Request,
    product_id: int,
    name: str = Form(...),
    unit: str = Form("ลิตร"),
    price: float = Form(0.0),
    category: str = Form("fuel"),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    p = db.query(Product).filter(Product.id == product_id, Product.store_id == store.id).first()
    if p:
        p.name = name; p.unit = unit; p.price = price
        p.category = category; p.is_active = bool(is_active)
        db.commit()
    return RedirectResponse("/web/products?saved=1", status_code=302)


@router.post("/products/{product_id}/delete")
def product_delete(request: Request, product_id: int, db: Session = Depends(get_db)):
    store = _get_store(request, db)
    if not store:
        return RedirectResponse("/web/login", status_code=302)
    p = db.query(Product).filter(Product.id == product_id, Product.store_id == store.id).first()
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/web/products", status_code=302)
