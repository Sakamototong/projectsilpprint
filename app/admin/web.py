"""Admin web routes for /admin/*"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy import func

from ..models import (
    SessionLocal,
    PlatformAdmin,
    Store,
    SubscriptionPlan,
    StoreSubscription,
    SubscriptionInvoice,
)
from .auth import (
    ADMIN_COOKIE,
    create_admin_token,
    hash_password,
    require_admin,
    verify_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_TH_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_label(dt: datetime, cycle: str) -> str:
    if cycle == "yearly":
        return f"ปี {dt.year}"
    return f"{_TH_MONTHS[dt.month]} {dt.year}"


# ─── Login / Logout ────────────────────────────────────────────────────────────

@router.get("/login")
def admin_login_page(request: Request):
    # If already logged in redirect to dashboard
    try:
        from .auth import get_admin_ctx
        if get_admin_ctx(request):
            return RedirectResponse("/admin/dashboard", status_code=302)
    except Exception:
        pass
    return templates.TemplateResponse(request, "admin/login.html", {"admin_ctx": None})


@router.post("/login")
def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()
    try:
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.username == username).first()
        if not admin or not verify_password(password, admin.hashed_password):
            return templates.TemplateResponse(
                request,
                "admin/login.html",
                {"error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "admin_ctx": None},
                status_code=401,
            )
        token = create_admin_token(admin.id, admin.username)
        resp = RedirectResponse("/admin/dashboard", status_code=302)
        resp.set_cookie(ADMIN_COOKIE, token, httponly=True, samesite="lax")
        return resp
    finally:
        db.close()


@router.post("/logout")
def admin_logout(request: Request):
    resp = RedirectResponse("/admin/login", status_code=302)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def admin_dashboard(request: Request):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        now = _now()
        total_stores = db.query(func.count(Store.id)).scalar()
        active_subs = db.query(func.count(StoreSubscription.id)).filter(
            StoreSubscription.status == "active"
        ).scalar()
        pending_invoices = db.query(func.count(SubscriptionInvoice.id)).filter(
            SubscriptionInvoice.status == "pending"
        ).scalar()
        expiring_soon = db.query(func.count(StoreSubscription.id)).filter(
            StoreSubscription.status == "active",
            StoreSubscription.expires_at <= now + timedelta(days=7),
        ).scalar()
        recent_stores = db.query(Store).order_by(Store.created_at.desc()).limit(8).all()
        recent_inv_rows = (
            db.query(SubscriptionInvoice, Store.name.label("store_name"))
            .join(Store, Store.id == SubscriptionInvoice.store_id)
            .order_by(SubscriptionInvoice.created_at.desc())
            .limit(8)
            .all()
        )
        recent_invoices = [
            {
                "id": inv.id,
                "store_name": sname,
                "amount": inv.amount,
                "status": inv.status,
                "created_at": inv.created_at,
            }
            for inv, sname in recent_inv_rows
        ]
        stats = {
            "total_stores": total_stores,
            "active_subs": active_subs,
            "pending_invoices": pending_invoices,
            "expiring_soon": expiring_soon,
        }
        return templates.TemplateResponse(
            request,
            "admin/dashboard.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "dashboard",
                "stats": stats,
                "recent_stores": recent_stores,
                "recent_invoices": recent_invoices,
            },
        )
    finally:
        db.close()


# ─── Stores ────────────────────────────────────────────────────────────────────

@router.get("/stores")
def admin_stores(
    request: Request,
    status: Optional[str] = None,
    sub_status: Optional[str] = None,
    q: Optional[str] = None,
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        query = db.query(Store)
        if status:
            query = query.filter(Store.store_status == status)
        if sub_status:
            query = query.filter(Store.subscription_status == sub_status)
        if q:
            query = query.filter(Store.name.ilike(f"%{q}%"))
        stores_raw = query.order_by(Store.created_at.desc()).all()

        # Attach requested plan names
        plan_map = {p.id: p.name for p in db.query(SubscriptionPlan).all()}
        stores = []
        for s in stores_raw:
            obj = {
                "id": s.id,
                "name": s.name,
                "username": s.username,
                "business_type": s.business_type,
                "requested_plan_id": s.requested_plan_id,
                "requested_plan_name": plan_map.get(s.requested_plan_id) if s.requested_plan_id else None,
                "store_status": s.store_status,
                "subscription_status": s.subscription_status,
                "created_at": s.created_at,
            }
            stores.append(obj)

        return templates.TemplateResponse(
            request,
            "admin/stores.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "stores",
                "stores": stores,
                "status_filter": status or "",
                "sub_filter": sub_status or "",
                "q": q or "",
            },
        )
    finally:
        db.close()


@router.get("/stores/{store_id}")
def admin_store_detail(request: Request, store_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            return RedirectResponse("/admin/stores", status_code=302)
        plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
        subscriptions = (
            db.query(StoreSubscription)
            .filter(StoreSubscription.store_id == store_id)
            .order_by(StoreSubscription.created_at.desc())
            .all()
        )
        invoices = (
            db.query(SubscriptionInvoice)
            .filter(SubscriptionInvoice.store_id == store_id)
            .order_by(SubscriptionInvoice.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request,
            "admin/store_detail.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "stores",
                "store": store,
                "plans": plans,
                "subscriptions": subscriptions,
                "invoices": invoices,
            },
        )
    finally:
        db.close()


@router.post("/stores/{store_id}/approve")
def admin_approve_store(
    request: Request,
    store_id: int,
    plan_id: int = Form(...),
    billing_cycle: str = Form("monthly"),
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            return RedirectResponse("/admin/stores", status_code=302)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if not plan:
            return RedirectResponse(f"/admin/stores/{store_id}", status_code=302)

        now = _now()
        if billing_cycle == "yearly":
            expires_at = now + timedelta(days=365)
            grace_until = expires_at + timedelta(days=7)
            amount = plan.price_yearly
        else:
            expires_at = now + timedelta(days=30)
            grace_until = expires_at + timedelta(days=7)
            amount = plan.price_monthly

        # Cancel old active subscriptions for this store
        db.query(StoreSubscription).filter(
            StoreSubscription.store_id == store_id,
            StoreSubscription.status == "active",
        ).update({"status": "cancelled"})

        sub = StoreSubscription(
            store_id=store_id,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            status="active",
            started_at=now,
            expires_at=expires_at,
            grace_until=grace_until,
        )
        db.add(sub)
        db.flush()

        period = _period_label(now, billing_cycle)
        due_date = now + timedelta(days=7)
        invoice = SubscriptionInvoice(
            store_id=store_id,
            subscription_id=sub.id,
            amount=amount,
            billing_cycle=billing_cycle,
            period_label=period,
            status="pending",
            due_date=due_date,
        )
        db.add(invoice)

        store.store_status = "active"
        store.subscription_status = "active"
        store.rejection_reason = None
        db.commit()
        return RedirectResponse(f"/admin/stores/{store_id}?flash=approved", status_code=302)
    finally:
        db.close()


@router.post("/stores/{store_id}/reject")
def admin_reject_store(
    request: Request,
    store_id: int,
    reason: str = Form(""),
    hard_delete: Optional[str] = Form(None),
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            return RedirectResponse("/admin/stores", status_code=302)
        if hard_delete == "1":
            db.delete(store)
            db.commit()
            return RedirectResponse("/admin/stores?flash=deleted", status_code=302)
        store.store_status = "rejected"
        store.rejection_reason = reason.strip() or None
        db.commit()
        return RedirectResponse(f"/admin/stores/{store_id}?flash=rejected", status_code=302)
    finally:
        db.close()


# ─── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/plans")
def admin_plans(request: Request):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.id).all()
        return templates.TemplateResponse(
            request,
            "admin/plans.html",
            {"admin_ctx": admin_ctx, "active_page": "plans", "plans": plans},
        )
    finally:
        db.close()


@router.post("/plans/new")
def admin_plan_new(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    price_monthly: float = Form(0),
    price_yearly: float = Form(0),
    max_members: int = Form(0),
    max_staff: int = Form(0),
    max_receipts_per_month: int = Form(0),
    max_products: int = Form(0),
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        plan = SubscriptionPlan(
            name=name.strip(),
            description=description.strip() or None,
            price_monthly=price_monthly,
            price_yearly=price_yearly,
            max_members=max_members,
            max_staff=max_staff,
            max_receipts_per_month=max_receipts_per_month,
            max_products=max_products,
        )
        db.add(plan)
        db.commit()
        return RedirectResponse("/admin/plans", status_code=302)
    finally:
        db.close()


@router.post("/plans/{plan_id}/edit")
def admin_plan_edit(
    request: Request,
    plan_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price_monthly: float = Form(0),
    price_yearly: float = Form(0),
    max_members: int = Form(0),
    max_staff: int = Form(0),
    max_receipts_per_month: int = Form(0),
    max_products: int = Form(0),
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if plan:
            plan.name = name.strip()
            plan.description = description.strip() or None
            plan.price_monthly = price_monthly
            plan.price_yearly = price_yearly
            plan.max_members = max_members
            plan.max_staff = max_staff
            plan.max_receipts_per_month = max_receipts_per_month
            plan.max_products = max_products
            db.commit()
        return RedirectResponse("/admin/plans", status_code=302)
    finally:
        db.close()


@router.post("/plans/{plan_id}/delete")
def admin_plan_delete(request: Request, plan_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
        if plan:
            plan.is_active = False
            db.commit()
        return RedirectResponse("/admin/plans", status_code=302)
    finally:
        db.close()


# ─── Invoices ──────────────────────────────────────────────────────────────────

@router.get("/invoices")
def admin_invoices(request: Request, status: Optional[str] = None):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        query = db.query(SubscriptionInvoice, Store.name.label("store_name")).join(
            Store, Store.id == SubscriptionInvoice.store_id
        )
        if status:
            query = query.filter(SubscriptionInvoice.status == status)
        rows = query.order_by(SubscriptionInvoice.created_at.desc()).all()
        invoices = [
            {
                "id": inv.id,
                "store_id": inv.store_id,
                "store_name": sname,
                "period_label": inv.period_label,
                "billing_cycle": inv.billing_cycle,
                "amount": inv.amount,
                "status": inv.status,
                "due_date": inv.due_date,
                "paid_at": inv.paid_at,
                "created_at": inv.created_at,
            }
            for inv, sname in rows
        ]
        return templates.TemplateResponse(
            request,
            "admin/invoices.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "invoices",
                "invoices": invoices,
                "status_filter": status or "",
            },
        )
    finally:
        db.close()


@router.post("/invoices/{invoice_id}/confirm-payment")
def admin_confirm_payment(request: Request, invoice_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        inv = db.query(SubscriptionInvoice).filter(SubscriptionInvoice.id == invoice_id).first()
        if inv and inv.status != "paid":
            now = _now()
            inv.status = "paid"
            inv.paid_at = now
            # Extend subscription expiry
            sub = db.query(StoreSubscription).filter(
                StoreSubscription.id == inv.subscription_id
            ).first()
            if sub:
                base = max(sub.expires_at or now, now)
                if inv.billing_cycle == "yearly":
                    sub.expires_at = base + timedelta(days=365)
                else:
                    sub.expires_at = base + timedelta(days=30)
                sub.grace_until = sub.expires_at + timedelta(days=7)
                sub.status = "active"
                # Update store subscription_status
                store = db.query(Store).filter(Store.id == inv.store_id).first()
                if store:
                    store.subscription_status = "active"
            db.commit()
        referrer = request.headers.get("referer", "/admin/invoices")
        return RedirectResponse(referrer, status_code=302)
    finally:
        db.close()


@router.post("/invoices/{invoice_id}/mark-overdue")
def admin_mark_overdue(request: Request, invoice_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        inv = db.query(SubscriptionInvoice).filter(SubscriptionInvoice.id == invoice_id).first()
        if inv and inv.status == "pending":
            inv.status = "overdue"
            db.commit()
        referrer = request.headers.get("referer", "/admin/invoices")
        return RedirectResponse(referrer, status_code=302)
    finally:
        db.close()


# ─── Subscription Renew ────────────────────────────────────────────────────────

@router.post("/subscriptions/{sub_id}/renew")
def admin_subscription_renew(request: Request, sub_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        sub = db.query(StoreSubscription).filter(StoreSubscription.id == sub_id).first()
        if not sub:
            return RedirectResponse("/admin/stores", status_code=302)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        now = _now()
        base = max(sub.expires_at or now, now)
        if sub.billing_cycle == "yearly":
            sub.expires_at = base + timedelta(days=365)
            amount = plan.price_yearly if plan else 0
        else:
            sub.expires_at = base + timedelta(days=30)
            amount = plan.price_monthly if plan else 0
        sub.grace_until = sub.expires_at + timedelta(days=7)
        sub.status = "active"

        period = _period_label(now, sub.billing_cycle)
        invoice = SubscriptionInvoice(
            store_id=sub.store_id,
            subscription_id=sub.id,
            amount=amount,
            billing_cycle=sub.billing_cycle,
            period_label=period,
            status="pending",
            due_date=now + timedelta(days=7),
        )
        db.add(invoice)
        store = db.query(Store).filter(Store.id == sub.store_id).first()
        if store:
            store.subscription_status = "active"
        db.commit()
        return RedirectResponse(f"/admin/stores/{sub.store_id}", status_code=302)
    finally:
        db.close()
