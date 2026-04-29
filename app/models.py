import os
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, func, Text
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # ข้อมูลที่อยู่/ออกใบเสร็จของร้าน
    address = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    vat_rate = Column(Float, default=7.0)       # % VAT (0 = ไม่มี VAT)
    include_vat = Column(Boolean, default=True) # แสดง VAT ในใบเสร็จ
    # ปรับแต่งใบเสร็จ
    logo_base64 = Column(Text, nullable=True)            # รูป logo (data URI)
    receipt_color = Column(String(7), nullable=True)     # สีหลัก hex เช่น #1a3a6e
    cash_receipt_color = Column(String(7), nullable=True) # สีบิลเงินสด hex เช่น #166534
    receipt_header_text = Column(Text, nullable=True)    # ข้อความใต้ชื่อร้าน
    receipt_footer_text = Column(Text, nullable=True)    # ข้อความหมายเหตุท้ายใบเสร็จ
    # SaaS / approval fields
    business_type = Column(String, nullable=True)          # "fuel_station"/"retail"/"other"
    requested_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    store_status = Column(String, default="active")        # "active"/"rejected"/"suspended"
    rejection_reason = Column(Text, nullable=True)
    subscription_status = Column(String, default="free")   # "free"/"active"/"grace"/"expired"
    members = relationship("Member", back_populates="store")
    staff = relationship("StaffUser", back_populates="store")
    products = relationship("Product", back_populates="store")
    companies = relationship("Company", back_populates="store", order_by="Company.company_name")


class StaffUser(Base):
    """ผู้ใช้งานเพิ่มเติมในร้านค้า (ไม่ใช่เจ้าของ)"""
    __tablename__ = "staff_users"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # admin / user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    store = relationship("Store", back_populates="staff")


class Product(Base):
    """รายการสินค้า / น้ำมัน ที่ร้านค้ากำหนด"""
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    name = Column(String, nullable=False)
    unit = Column(String, default="ลิตร")
    price = Column(Float, default=0.0)
    category = Column(String, default="fuel")  # fuel / service / other
    is_active = Column(Boolean, default=True)
    store = relationship("Store", back_populates="products")


class BillingProfile(Base):
    """ที่อยู่ออกบิล/ใบเสร็จในนามบริษัท — สมาชิกหนึ่งคนมีได้หลายชุด"""
    __tablename__ = "billing_profiles"
    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    label = Column(String, nullable=False)          # ชื่อแสดง เช่น "สำนักงานใหญ่"
    company_name = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    member = relationship("Member", back_populates="billing_profiles")


class Company(Base):
    """บริษัท / ผู้รับใบกำกับภาษีในร้านค้า (ไม่ผูกกับสมาชิก)"""
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    company_name = Column(String, nullable=False)
    tax_id = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    store = relationship("Store", back_populates="companies")


class Member(Base):
    __tablename__ = "members"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, index=True, nullable=True)
    email = Column(String, nullable=True)
    member_code = Column(String, unique=True, index=True, nullable=True)
    birthdate = Column(String, nullable=True)
    tier = Column(String, default="general")
    points = Column(Integer, default=0)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # ข้อมูลบริษัท / ยานพาหนะ
    member_type = Column(String, default="person")   # "person" | "company"
    company_name = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    driver_name = Column(String, nullable=True)
    license_plate = Column(String, nullable=True)
    address = Column(String, nullable=True)
    store = relationship("Store", back_populates="members")
    transactions = relationship("Transaction", back_populates="member", order_by="Transaction.timestamp.desc()")
    billing_profiles = relationship("BillingProfile", back_populates="member", order_by="BillingProfile.id")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    terminal_id = Column(String, nullable=True)
    total = Column(Float, nullable=False)
    payment_method = Column(String, nullable=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    raw = Column(JSON, nullable=True)

    member = relationship("Member", back_populates="transactions")
    receipts = relationship("Receipt", back_populates="transaction")


class Receipt(Base):
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"))
    printed_at = Column(DateTime(timezone=True), server_default=func.now())
    content_path = Column(String, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    # Audit trail
    created_by_name = Column(String, nullable=True)   # ชื่อผู้ออกบิล
    created_by_id = Column(Integer, nullable=True)    # store.id หรือ staff.id
    edit_log = Column(JSON, nullable=True)            # [{at, by_name, by_id, changes}]
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_name = Column(String, nullable=True)
    deleted_by_id = Column(Integer, nullable=True)

    transaction = relationship("Transaction", back_populates="receipts")


# ─── SaaS / Billing Models ───────────────────────────────────────────────────

class PlatformAdmin(Base):
    """Superadmin users for the /admin/* dashboard (separate from store staff)."""
    __tablename__ = "platform_admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SubscriptionPlan(Base):
    """Admin-defined plans that stores can subscribe to."""
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price_monthly = Column(Float, default=0.0)
    price_yearly = Column(Float, default=0.0)
    # Limits (0 = unlimited)
    max_members = Column(Integer, default=0)
    max_staff = Column(Integer, default=0)
    max_receipts_per_month = Column(Integer, default=0)
    max_products = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    subscriptions = relationship("StoreSubscription", back_populates="plan")


class StoreSubscription(Base):
    """Active/historical subscription record per store."""
    __tablename__ = "store_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    billing_cycle = Column(String, default="monthly")   # "monthly" / "yearly"
    status = Column(String, default="active")           # "active"/"grace"/"expired"/"cancelled"
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    grace_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    invoices = relationship("SubscriptionInvoice", back_populates="subscription")


class SubscriptionInvoice(Base):
    """Invoice issued per billing period per store subscription."""
    __tablename__ = "subscription_invoices"
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("store_subscriptions.id"), nullable=False)
    amount = Column(Float, nullable=False)
    billing_cycle = Column(String, nullable=False)      # "monthly" / "yearly"
    period_label = Column(String, nullable=True)        # e.g. "มี.ค. 2026"
    status = Column(String, default="pending")          # "pending"/"paid"/"overdue"
    due_date = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    payment_ref = Column(String, nullable=True)         # for future gateway reference
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    subscription = relationship("StoreSubscription", back_populates="invoices")
