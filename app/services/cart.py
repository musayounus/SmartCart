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


def _refuse_beyond_stock(product: Product, wanted: int) -> None:
    """Stop a basket asking for more than the shelf holds.

    This is a courtesy, not a guarantee, and the distinction matters. It reads
    stock without a lock and acts on what it read -- precisely the
    check-then-act this project exists to show is not enough. Two shoppers can
    each fill a basket with the last eight units and both will pass this check.

    Checkout is the only thing that decides who actually gets them. Do not
    grow this into a reservation without taking the same lock checkout takes.
    """
    if wanted > product.stock_quantity:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only {product.stock_quantity} of {product.name} in stock, asked for {wanted}",
        )


async def add_item(
    session: AsyncSession, cart_id: uuid.UUID, product_id: int, quantity: int
) -> CartOut:
    if await session.get(Cart, cart_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")

    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")

    existing = await session.scalar(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )
    _refuse_beyond_stock(product, (existing.quantity if existing else 0) + quantity)

    if existing is None:
        session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=quantity))
    else:
        existing.quantity += quantity

    await session.commit()
    return await load_cart(session, cart_id)


async def set_item_quantity(
    session: AsyncSession, cart_id: uuid.UUID, product_id: int, quantity: int
) -> CartOut:
    """Set a line to an exact quantity. Used to reduce a line without losing it."""
    if await session.get(Cart, cart_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")

    line = await session.scalar(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )
    if line is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Product {product_id} is not in cart {cart_id}"
        )

    product = await session.get(Product, product_id)
    if product is not None:
        _refuse_beyond_stock(product, quantity)

    line.quantity = quantity
    await session.commit()
    return await load_cart(session, cart_id)


async def remove_item(session: AsyncSession, cart_id: uuid.UUID, product_id: int) -> CartOut:
    """Drop a line from the cart entirely, whatever its quantity.

    Reducing a line is `set_item_quantity`; this is the whole-line removal.
    """
    if await session.get(Cart, cart_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")

    line = await session.scalar(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )
    if line is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Product {product_id} is not in cart {cart_id}"
        )

    await session.delete(line)
    await session.commit()
    # The cart itself survives an empty basket, so the shopper can keep using it.
    return await load_cart(session, cart_id)
