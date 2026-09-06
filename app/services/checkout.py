import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cart, CartItem, Order, OrderItem, Product
from app.schemas import OrderItemOut, OrderOut

ZERO = Decimal("0.00")


async def checkout(session: AsyncSession, cart_id: uuid.UUID) -> OrderOut:
    """Turn a cart into an order, and never let stock go negative doing it.

    The race this defends against: two checkouts both read the same stock,
    both decide there is enough, and both decrement. Stock lands at 0 having
    sold one unit twice -- corruption that is invisible in the final number.

    The defence is one transaction containing a locking read. FOR UPDATE holds
    the product rows until commit, so a competing checkout blocks on the SELECT
    rather than proceeding from a stale value, and re-reads the true stock when
    it wakes. ORDER BY id is not cosmetic: it forces every transaction to take
    locks in the same order, so two multi-line orders touching the same
    products in opposite order cannot deadlock against each other.
    """
    # Columns only, never `session.get(Cart, ...)`. Loading the Cart entity
    # follows selectin from Cart to CartItem to Product, putting every Product
    # in the identity map at its *pre-lock* stock value.
    if await session.scalar(select(Cart.id).where(Cart.id == cart_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cart {cart_id} not found")

    # Columns again, for the same reason.
    rows = await session.execute(
        select(CartItem.product_id, CartItem.quantity).where(CartItem.cart_id == cart_id)
    )
    wanted = {product_id: quantity for product_id, quantity in rows}
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cart is empty")

    locked = (
        await session.scalars(
            select(Product)
            .where(Product.id.in_(wanted))
            .order_by(Product.id)
            .with_for_update()
            # Not optional, and not belt-and-braces. Without it, a Product
            # already in the identity map keeps the attributes it was first
            # loaded with and the freshly locked values are discarded -- the
            # lock is held correctly and the arithmetic runs on a stale number.
            #
            # This was removed once on the reasoning that reading columns above
            # meant nothing could preload Product. That reasoning was wrong,
            # and the tests did not catch it: the identity map holds weak
            # references, so the cart was usually collected before the locking
            # read and the bug only appeared when it happened to survive.
            # Correctness that depends on garbage collection timing is not
            # correctness. See test_locked_read_ignores_anything_cached_before.
            .execution_options(populate_existing=True)
        )
    ).all()

    # All-or-nothing: one short line rejects the whole order, and nothing is
    # decremented -- including the lines that would have succeeded.
    for product in locked:
        if product.stock_quantity < wanted[product.id]:
            # Read what we need before rolling back; rollback expires these
            # attributes and touching them afterwards triggers lazy IO.
            name, available, requested = product.name, product.stock_quantity, wanted[product.id]
            await session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Insufficient stock for {name}: requested {requested}, {available} available",
            )

    order = Order(status="confirmed", total=ZERO)
    session.add(order)
    await session.flush()

    total = ZERO
    lines: list[OrderItemOut] = []
    for product in locked:
        quantity = wanted[product.id]
        product.stock_quantity -= quantity
        # Price captured from the locked read, so the order records what was
        # actually charged even if the catalog price changes later.
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                price_at_purchase=product.price,
            )
        )
        total += product.price * quantity
        lines.append(
            OrderItemOut(
                product_id=product.id,
                name=product.name,
                quantity=quantity,
                price_at_purchase=product.price,
            )
        )

    order.total = total
    await session.execute(CartItem.__table__.delete().where(CartItem.cart_id == cart_id))
    await session.commit()

    return OrderOut(id=order.id, status="confirmed", total=total, items=lines)
