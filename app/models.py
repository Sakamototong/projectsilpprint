import os
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, func
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
    members = relationship("Member", back_populates="store")
    staff = relationship("StaffUser", back_populates="store")
    products = relationship("Product", back_populates="store")


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
    store = relationship("Store", back_populates="members")
    transactions = relationship("Transaction", back_populates="member", order_by="Transaction.timestamp.desc()")
    billing_profiles = relationship("BillingProfile", back_populates="member", order_by="BillingProfile.id")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
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
