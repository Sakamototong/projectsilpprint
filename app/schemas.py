from pydantic import BaseModel, ConfigDict
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


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: Optional[str] = None
    points: int
    member_code: Optional[str] = None
    tier: Optional[str] = None


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
