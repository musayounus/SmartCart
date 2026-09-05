import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    stock_quantity: int


class CartItemIn(BaseModel):
    """Deliberately has no price field: the client never gets to name a price."""

    product_id: int
    quantity: int = Field(gt=0)


class CartItemOut(BaseModel):
    product_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    total: Decimal


class OrderItemOut(BaseModel):
    product_id: int
    name: str
    quantity: int
    price_at_purchase: Decimal


class OrderOut(BaseModel):
    id: int
    status: str
    total: Decimal
    items: list[OrderItemOut]


class OrderSummaryOut(BaseModel):
    """History listing: no line items, so the list stays cheap to read."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    total: Decimal
    created_at: datetime


class RecommendationOut(BaseModel):
    product_id: int
    name: str
    price: Decimal
    bought_together_count: int
