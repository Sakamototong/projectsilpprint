"""Admin web routes for /admin/*"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy import func

import secrets
import string

from ..models import (
    SessionLocal,
    PlatformAdmin,
    Store,
    StaffUser,
    Member,
    Product,
    Receipt,
    Transaction,
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


def _random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _usage_for_store(store: Store, db) -> dict:
    """Return current usage counts for a store."""
    now = _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    member_count = db.query(func.count(Member.id)).filter(Member.store_id == store.id).scalar() or 0
    staff_count = db.query(func.count(StaffUser.id)).filter(StaffUser.store_id == store.id).scalar() or 0
    product_count = (
        db.query(func.count(Product.id))
        .filter(Product.store_id == store.id, Product.is_active == True)
        .scalar() or 0
    )
    receipt_count = (
        db.query(func.count(Receipt.id))
        .join(Transaction, Transaction.id == Receipt.transaction_id)
        .join(Member, Member.id == Transaction.member_id)
        .filter(Member.store_id == store.id, Receipt.printed_at >= month_start)
        .scalar() or 0
    )
    return {
        "member_count": member_count,
        "staff_count": staff_count,
        "product_count": product_count,
        "receipt_count": receipt_count,
    }

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ── Number format filters (comma thousand separator) ──
def _fmt(v, d=2):
    try: return f"{float(v):,.{d}f}"
    except (TypeError, ValueError): return "0." + "0"*d
templates.env.filters["fmt"]  = lambda v: _fmt(v, 2)
templates.env.filters["fmt0"] = lambda v: _fmt(v, 0)
templates.env.filters["fmt1"] = lambda v: _fmt(v, 1)

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
        staff_users = (
            db.query(StaffUser)
            .filter(StaffUser.store_id == store_id)
            .order_by(StaffUser.created_at.desc())
            .all()
        )
        usage = _usage_for_store(store, db)
        # Get active plan limits for this store
        active_sub = (
            db.query(StoreSubscription)
            .filter(StoreSubscription.store_id == store_id, StoreSubscription.status == "active")
            .order_by(StoreSubscription.started_at.desc())
            .first()
        )
        plan_limits = None
        if active_sub:
            plan_limits = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == active_sub.plan_id).first()
        flash_msg = request.query_params.get("flash")
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
                "staff_users": staff_users,
                "usage": usage,
                "plan_limits": plan_limits,
                "flash_msg": flash_msg,
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


# ─── User Management ──────────────────────────────────────────────────────────

@router.get("/users")
def admin_users(
    request: Request,
    store_id: Optional[int] = None,
    role: Optional[str] = None,
    active: Optional[str] = None,
    q: Optional[str] = None,
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        query = db.query(StaffUser, Store.name.label("store_name")).join(
            Store, Store.id == StaffUser.store_id
        )
        if store_id:
            query = query.filter(StaffUser.store_id == store_id)
        if role:
            query = query.filter(StaffUser.role == role)
        if active == "1":
            query = query.filter(StaffUser.is_active == True)
        elif active == "0":
            query = query.filter(StaffUser.is_active == False)
        if q:
            query = query.filter(
                StaffUser.name.ilike(f"%{q}%") | StaffUser.username.ilike(f"%{q}%")
            )
        rows = query.order_by(StaffUser.created_at.desc()).all()
        users = [
            {
                "id": u.id,
                "store_id": u.store_id,
                "store_name": sname,
                "name": u.name,
                "username": u.username,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at,
            }
            for u, sname in rows
        ]
        stores_list = db.query(Store).order_by(Store.name).all()
        flash_msg = request.query_params.get("flash")
        flash_data = request.query_params.get("flash_data")
        return templates.TemplateResponse(
            request,
            "admin/users.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "users",
                "users": users,
                "stores_list": stores_list,
                "store_id_filter": store_id or "",
                "role_filter": role or "",
                "active_filter": active or "",
                "q": q or "",
                "flash_msg": flash_msg,
                "flash_data": flash_data,
            },
        )
    finally:
        db.close()


@router.post("/users/{user_id}/toggle")
def admin_user_toggle(request: Request, user_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        user = db.query(StaffUser).filter(StaffUser.id == user_id).first()
        if user:
            user.is_active = not user.is_active
            db.commit()
        referrer = request.headers.get("referer", "/admin/users")
        return RedirectResponse(referrer, status_code=302)
    finally:
        db.close()


@router.post("/users/{user_id}/reset-password")
def admin_user_reset_password(request: Request, user_id: int):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        user = db.query(StaffUser).filter(StaffUser.id == user_id).first()
        if not user:
            return RedirectResponse("/admin/users", status_code=302)
        new_pw = _random_password()
        user.hashed_password = hash_password(new_pw)
        db.commit()
        # Redirect back with new password in query param (one-time display)
        referrer = request.headers.get("referer", "/admin/users")
        import urllib.parse
        base = referrer.split("?")[0]
        return RedirectResponse(
            f"{base}?flash=reset&flash_data={urllib.parse.quote(new_pw)}",
            status_code=302,
        )
    finally:
        db.close()


# ─── Usage Overview ───────────────────────────────────────────────────────────

_FREE_LIMITS = {"max_members": 50, "max_staff": 2, "max_receipts_per_month": 100, "max_products": 10}


@router.get("/usage")
def admin_usage(request: Request, q: Optional[str] = None):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        store_query = db.query(Store)
        if q:
            store_query = store_query.filter(Store.name.ilike(f"%{q}%"))
        stores = store_query.order_by(Store.name).all()

        # Build plan map: store_id -> active plan
        active_subs = (
            db.query(StoreSubscription, SubscriptionPlan)
            .join(SubscriptionPlan, SubscriptionPlan.id == StoreSubscription.plan_id)
            .filter(StoreSubscription.status == "active")
            .all()
        )
        plan_by_store: dict[int, SubscriptionPlan] = {}
        for sub, plan in active_subs:
            plan_by_store[sub.store_id] = plan

        rows = []
        for store in stores:
            usage = _usage_for_store(store, db)
            plan = plan_by_store.get(store.id)
            limits = {
                "max_members": plan.max_members if plan else _FREE_LIMITS["max_members"],
                "max_staff": plan.max_staff if plan else _FREE_LIMITS["max_staff"],
                "max_receipts_per_month": plan.max_receipts_per_month if plan else _FREE_LIMITS["max_receipts_per_month"],
                "max_products": plan.max_products if plan else _FREE_LIMITS["max_products"],
            }
            rows.append({
                "store": store,
                "plan_name": plan.name if plan else "Free",
                "usage": usage,
                "limits": limits,
            })

        return templates.TemplateResponse(
            request,
            "admin/usage.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "usage",
                "rows": rows,
                "q": q or "",
            },
        )
    finally:
        db.close()


# ─── Reports ──────────────────────────────────────────────────────────────────

def _month_range(year: int, month: int):
    """Return (start, end) datetime for a given year+month in UTC."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


@router.get("/reports")
def admin_reports(request: Request):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        now = _now()

        # ── Platform KPIs ─────────────────────────────────────────────
        total_stores = db.query(func.count(Store.id)).scalar() or 0
        active_stores = db.query(func.count(Store.id)).filter(Store.store_status == "active").scalar() or 0
        total_members = db.query(func.count(Member.id)).scalar() or 0
        total_transactions = db.query(func.count(Transaction.id)).scalar() or 0
        total_tx_amount = db.query(func.coalesce(func.sum(Transaction.total), 0)).scalar() or 0

        total_revenue_collected = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.status == "paid")
            .scalar() or 0
        )
        total_revenue_pending = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.status == "pending")
            .scalar() or 0
        )
        total_revenue_overdue = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.status == "overdue")
            .scalar() or 0
        )

        # ── Subscription breakdown by plan ────────────────────────────
        plan_rows = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
        plan_breakdown = []
        for plan in plan_rows:
            count = (
                db.query(func.count(StoreSubscription.id))
                .filter(StoreSubscription.plan_id == plan.id, StoreSubscription.status == "active")
                .scalar() or 0
            )
            plan_breakdown.append({"plan": plan, "count": count})
        free_count = (
            db.query(func.count(Store.id))
            .filter(Store.subscription_status == "free")
            .scalar() or 0
        )

        # ── Expiring soon (next 14 days) ──────────────────────────────
        expiring_subs = (
            db.query(StoreSubscription, Store.name.label("store_name"))
            .join(Store, Store.id == StoreSubscription.store_id)
            .filter(
                StoreSubscription.status == "active",
                StoreSubscription.expires_at <= now + timedelta(days=14),
                StoreSubscription.expires_at >= now,
            )
            .order_by(StoreSubscription.expires_at)
            .all()
        )
        expiring = [
            {"sub": sub, "store_name": sname}
            for sub, sname in expiring_subs
        ]

        # ── Monthly billing revenue (last 12 months) ──────────────────
        monthly_revenue = []
        for i in range(11, -1, -1):
            target = now - timedelta(days=i * 30)
            m_start, m_end = _month_range(target.year, target.month)
            paid = (
                db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
                .filter(
                    SubscriptionInvoice.status == "paid",
                    SubscriptionInvoice.paid_at >= m_start,
                    SubscriptionInvoice.paid_at < m_end,
                )
                .scalar() or 0
            )
            pending = (
                db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
                .filter(
                    SubscriptionInvoice.status.in_(["pending", "overdue"]),
                    SubscriptionInvoice.created_at >= m_start,
                    SubscriptionInvoice.created_at < m_end,
                )
                .scalar() or 0
            )
            monthly_revenue.append({
                "label": f"{_TH_MONTHS[target.month]} {target.year}",
                "paid": paid,
                "pending": pending,
            })

        # ── Top stores by transaction volume ─────────────────────────
        top_stores_rows = (
            db.query(Store, func.count(Transaction.id).label("tx_count"),
                     func.coalesce(func.sum(Transaction.total), 0).label("tx_total"))
            .join(Member, Member.store_id == Store.id)
            .join(Transaction, Transaction.member_id == Member.id)
            .group_by(Store.id)
            .order_by(func.sum(Transaction.total).desc())
            .limit(10)
            .all()
        )
        top_stores = [
            {"store": s, "tx_count": tc, "tx_total": tt}
            for s, tc, tt in top_stores_rows
        ]

        kpis = {
            "total_stores": total_stores,
            "active_stores": active_stores,
            "total_members": total_members,
            "total_transactions": total_transactions,
            "total_tx_amount": total_tx_amount,
            "total_revenue_collected": total_revenue_collected,
            "total_revenue_pending": total_revenue_pending,
            "total_revenue_overdue": total_revenue_overdue,
        }
        return templates.TemplateResponse(
            request,
            "admin/reports.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "reports",
                "kpis": kpis,
                "plan_breakdown": plan_breakdown,
                "free_count": free_count,
                "expiring": expiring,
                "monthly_revenue": monthly_revenue,
                "top_stores": top_stores,
                "now_dt": now,
            },
        )
    finally:
        db.close()


@router.get("/reports/store/{store_id}")
def admin_report_store(request: Request, store_id: int, months: int = 6):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        store = db.query(Store).filter(Store.id == store_id).first()
        if not store:
            return RedirectResponse("/admin/reports", status_code=302)

        now = _now()

        # ── Current subscription ───────────────────────────────────────
        active_sub = (
            db.query(StoreSubscription, SubscriptionPlan)
            .join(SubscriptionPlan, SubscriptionPlan.id == StoreSubscription.plan_id)
            .filter(StoreSubscription.store_id == store_id, StoreSubscription.status == "active")
            .order_by(StoreSubscription.started_at.desc())
            .first()
        )
        current_sub = active_sub[0] if active_sub else None
        current_plan = active_sub[1] if active_sub else None

        # ── Invoice summary ───────────────────────────────────────────
        inv_paid = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.store_id == store_id, SubscriptionInvoice.status == "paid")
            .scalar() or 0
        )
        inv_pending = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.store_id == store_id, SubscriptionInvoice.status == "pending")
            .scalar() or 0
        )
        inv_overdue = (
            db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
            .filter(SubscriptionInvoice.store_id == store_id, SubscriptionInvoice.status == "overdue")
            .scalar() or 0
        )
        invoices = (
            db.query(SubscriptionInvoice)
            .filter(SubscriptionInvoice.store_id == store_id)
            .order_by(SubscriptionInvoice.created_at.desc())
            .all()
        )

        # ── Member stats ──────────────────────────────────────────────
        month_start_cur, _ = _month_range(now.year, now.month)
        total_members = (
            db.query(func.count(Member.id)).filter(Member.store_id == store_id).scalar() or 0
        )
        new_members_this_month = (
            db.query(func.count(Member.id))
            .filter(Member.store_id == store_id, Member.created_at >= month_start_cur)
            .scalar() or 0
        )

        # ── Transaction stats ─────────────────────────────────────────
        total_tx = (
            db.query(func.count(Transaction.id))
            .join(Member, Member.id == Transaction.member_id)
            .filter(Member.store_id == store_id)
            .scalar() or 0
        )
        total_tx_amount = (
            db.query(func.coalesce(func.sum(Transaction.total), 0))
            .join(Member, Member.id == Transaction.member_id)
            .filter(Member.store_id == store_id)
            .scalar() or 0
        )

        # ── Monthly transaction breakdown (last N months) ─────────────
        monthly_tx = []
        clamp = min(max(months, 1), 24)
        for i in range(clamp - 1, -1, -1):
            target = now - timedelta(days=i * 30)
            m_start, m_end = _month_range(target.year, target.month)
            count = (
                db.query(func.count(Transaction.id))
                .join(Member, Member.id == Transaction.member_id)
                .filter(
                    Member.store_id == store_id,
                    Transaction.timestamp >= m_start,
                    Transaction.timestamp < m_end,
                )
                .scalar() or 0
            )
            total = (
                db.query(func.coalesce(func.sum(Transaction.total), 0))
                .join(Member, Member.id == Transaction.member_id)
                .filter(
                    Member.store_id == store_id,
                    Transaction.timestamp >= m_start,
                    Transaction.timestamp < m_end,
                )
                .scalar() or 0
            )
            monthly_tx.append({
                "label": f"{_TH_MONTHS[target.month]} {target.year}",
                "count": count,
                "total": total,
            })

        # ── Staff list ────────────────────────────────────────────────
        staff_users = (
            db.query(StaffUser)
            .filter(StaffUser.store_id == store_id)
            .order_by(StaffUser.name)
            .all()
        )

        # ── Payment method breakdown ──────────────────────────────────
        pm_rows = (
            db.query(
                Transaction.payment_method,
                func.count(Transaction.id).label("cnt"),
                func.coalesce(func.sum(Transaction.total), 0).label("total"),
            )
            .join(Member, Member.id == Transaction.member_id)
            .filter(Member.store_id == store_id)
            .group_by(Transaction.payment_method)
            .order_by(func.sum(Transaction.total).desc())
            .all()
        )
        payment_methods = [
            {"method": pm or "ไม่ระบุ", "count": cnt, "total": tot}
            for pm, cnt, tot in pm_rows
        ]

        usage = _usage_for_store(store, db)
        billing_summary = {
            "paid": inv_paid,
            "pending": inv_pending,
            "overdue": inv_overdue,
            "total": inv_paid + inv_pending + inv_overdue,
        }
        member_stats = {
            "total": total_members,
            "new_this_month": new_members_this_month,
        }
        tx_stats = {
            "total_count": total_tx,
            "total_amount": total_tx_amount,
        }
        return templates.TemplateResponse(
            request,
            "admin/report_store.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "reports",
                "store": store,
                "current_sub": current_sub,
                "current_plan": current_plan,
                "billing_summary": billing_summary,
                "invoices": invoices,
                "member_stats": member_stats,
                "tx_stats": tx_stats,
                "monthly_tx": monthly_tx,
                "staff_users": staff_users,
                "payment_methods": payment_methods,
                "usage": usage,
                "months": clamp,
            },
        )
    finally:
        db.close()


@router.get("/reports/billing")
def admin_report_billing(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
    status: Optional[str] = None,
):
    admin_ctx = require_admin(request)
    if isinstance(admin_ctx, RedirectResponse):
        return admin_ctx
    db = SessionLocal()
    try:
        now = _now()
        sel_year = year or now.year
        sel_month = month  # None means all months in the year

        query = db.query(SubscriptionInvoice, Store.name.label("store_name")).join(
            Store, Store.id == SubscriptionInvoice.store_id
        )
        query = query.filter(
            func.extract("year", SubscriptionInvoice.created_at) == sel_year
        )
        if sel_month:
            query = query.filter(
                func.extract("month", SubscriptionInvoice.created_at) == sel_month
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

        # ── Summary totals ─────────────────────────────────────────────
        total_all = sum(r["amount"] for r in invoices)
        total_paid = sum(r["amount"] for r in invoices if r["status"] == "paid")
        total_pending = sum(r["amount"] for r in invoices if r["status"] == "pending")
        total_overdue = sum(r["amount"] for r in invoices if r["status"] == "overdue")

        # ── Per-store rollup for this period ──────────────────────────
        store_rollup: dict[int, dict] = {}
        for r in invoices:
            sid = r["store_id"]
            if sid not in store_rollup:
                store_rollup[sid] = {
                    "store_id": sid,
                    "store_name": r["store_name"],
                    "total": 0, "paid": 0, "pending": 0, "overdue": 0, "count": 0,
                }
            store_rollup[sid]["total"] += r["amount"]
            store_rollup[sid][r["status"]] = store_rollup[sid].get(r["status"], 0) + r["amount"]
            store_rollup[sid]["count"] += 1
        store_summary = sorted(store_rollup.values(), key=lambda x: x["total"], reverse=True)

        # ── Monthly breakdown for selected year ───────────────────────
        monthly_breakdown = []
        for m in range(1, 13):
            m_start, m_end = _month_range(sel_year, m)
            paid = (
                db.query(func.coalesce(func.sum(SubscriptionInvoice.amount), 0))
                .filter(
                    SubscriptionInvoice.status == "paid",
                    SubscriptionInvoice.paid_at >= m_start,
                    SubscriptionInvoice.paid_at < m_end,
                )
                .scalar() or 0
            )
            inv_count = (
                db.query(func.count(SubscriptionInvoice.id))
                .filter(
                    func.extract("year", SubscriptionInvoice.created_at) == sel_year,
                    func.extract("month", SubscriptionInvoice.created_at) == m,
                )
                .scalar() or 0
            )
            monthly_breakdown.append({
                "month": m,
                "label": _TH_MONTHS[m],
                "paid": paid,
                "inv_count": inv_count,
                "is_current": (sel_year == now.year and m == now.month),
                "is_selected": (sel_month == m),
            })

        # Available years (range from first invoice to now)
        first_inv = db.query(func.min(SubscriptionInvoice.created_at)).scalar()
        first_year = first_inv.year if first_inv else now.year
        available_years = list(range(first_year, now.year + 1))

        billing_totals = {
            "total_all": total_all,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "total_overdue": total_overdue,
            "collection_rate": (total_paid / total_all * 100) if total_all > 0 else 0,
        }
        return templates.TemplateResponse(
            request,
            "admin/report_billing.html",
            {
                "admin_ctx": admin_ctx,
                "active_page": "reports",
                "invoices": invoices,
                "billing_totals": billing_totals,
                "store_summary": store_summary,
                "monthly_breakdown": monthly_breakdown,
                "sel_year": sel_year,
                "sel_month": sel_month or "",
                "status_filter": status or "",
                "available_years": available_years,
                "now_dt": now,
            },
        )
    finally:
        db.close()
