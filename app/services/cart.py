import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cart, CartItem, Product
from app.schemas import CartItemOut, CartOut

ZERO = Decimal("0.00")


async def load_cart(session: AsyncSession, cart_id: uuid.UUID) -> CartOut:
    """Read a cart with its totals computed from the catalog.

    Line and cart totals are derived from products.price on every read, so a
    price the client sent could not influence them even if one were accepted.
    """
    if await session.get(Cart, cart_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")

    rows = await session.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_id == cart_id)
        .order_by(Product.id)
    )

    items = [
        CartItemOut(
            product_id=product.id,
            name=product.name,
            unit_price=product.price,
            quantity=item.quantity,
            line_total=product.price * item.quantity,
        )
        for item, product in rows
    ]

    return CartOut(id=cart_id, items=items, total=sum((i.line_total for i in items), ZERO))


async def create_cart(session: AsyncSession) -> CartOut:
    cart = Cart()
    session.add(cart)
    await session.commit()
    return CartOut(id=cart.id, items=[], total=ZERO)


async def add_item(
    session: AsyncSession, cart_id: uuid.UUID, product_id: int, quantity: int
) -> CartOut:
    if await session.get(Cart, cart_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")
    if await session.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")

    existing = await session.scalar(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )
    if existing is None:
        session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity))
    else:
        existing.quantity += quantity

    await session.commit()
    return await load_cart(session, cart_id)
