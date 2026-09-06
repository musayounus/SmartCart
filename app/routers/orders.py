from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.db import SessionDep
from app.http_cache import no_store
from app.models import Order, OrderItem, Product
from app.schemas import OrderItemOut, OrderOut, OrderSummaryOut

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(no_store)])


@router.get("", response_model=list[OrderSummaryOut])
async def list_orders(session: SessionDep) -> list[Order]:
    result = await session.execute(select(Order).order_by(Order.id.desc()))
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, session: SessionDep) -> OrderOut:
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")

    rows = await session.execute(
        select(OrderItem, Product)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id == order_id)
        .order_by(Product.id)
    )

    return OrderOut(
        id=order.id,
        status=order.status,
        total=order.total,
        items=[
            OrderItemOut(
                product_id=product.id,
                name=product.name,
                quantity=item.quantity,
                # The price charged at the time, not the catalog price now.
                price_at_purchase=item.price_at_purchase,
            )
            for item, product in rows
        ],
    )
