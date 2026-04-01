from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List


class Item(BaseModel):
    sku: Optional[str] = None
    name: str
    qty: int = 1
    price: float = 0.0


class TransactionCreate(BaseModel):
    terminal_id: Optional[str] = None
    items: List[Item]
    subtotal: float
    tax: float = 0.0
    total: float
    payment_method: str = "cash"
    member_id: Optional[int] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: float


class MemberCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    store_id: Optional[int] = None


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    member_code: Optional[str] = None
    tier: Optional[str] = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: Optional[str] = None
    points: int
    member_code: Optional[str] = None
    tier: Optional[str] = None


class PaginatedMembers(BaseModel):
    items: List[MemberOut]
    total: int
    page: int
    page_size: int


class StoreCreate(BaseModel):
    name: str
    username: str
    password: str


class StoreLogin(BaseModel):
    username: str
    password: str


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str


class StaffCreate(BaseModel):
    name: str
    username: str
    password: str
    role: str = "user"  # "admin" | "user"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("admin", "user"):
            raise ValueError("role must be 'admin' or 'user'")
        return v


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("admin", "user"):
            raise ValueError("role must be 'admin' or 'user'")
        return v


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    username: str
    role: str
    is_active: bool
