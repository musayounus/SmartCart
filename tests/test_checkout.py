from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import OrderItem, Product


async def cart_with(client: AsyncClient, product_id: int, quantity: int) -> str:
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(
        f"/carts/{cart_id}/items", json={"product_id": product_id, "quantity": quantity}
    )
    return cart_id


async def test_checkout_creates_an_order_and_decrements_stock(
    client: AsyncClient, session: AsyncSession
) -> None:
    cart_id = await cart_with(client, product_id=1, quantity=3)

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 201
    assert Decimal(response.json()["total"]) == Decimal("126.00")

    stock = await session.scalar(select(Product.stock_quantity).where(Product.id == 1))
    assert stock == 22


async def test_checkout_records_the_price_paid_not_the_current_price(
    client: AsyncClient, session: AsyncSession
) -> None:
    """An order is a record of what was charged; a later price change must not rewrite it."""
    cart_id = await cart_with(client, product_id=1, quantity=1)
    order_id = (await client.post(f"/carts/{cart_id}/checkout")).json()["id"]

    product = await session.get(Product, 1)
    product.price = Decimal("99.00")
    await session.commit()

    # Scoped to this order specifically. Unfiltered, this would read whichever
    # order_items row came back first -- including a seeded one.
    recorded = await session.scalar(
        select(OrderItem.price_at_purchase).where(
            OrderItem.order_id == order_id, OrderItem.product_id == 1
        )
    )
    assert recorded == Decimal("42.00")


async def test_checkout_empties_the_cart(client: AsyncClient) -> None:
    cart_id = await cart_with(client, product_id=1, quantity=1)

    await client.post(f"/carts/{cart_id}/checkout")
    cart = (await client.get(f"/carts/{cart_id}")).json()

    assert cart["items"] == []


async def test_multi_line_checkout_decrements_every_product(
    client: AsyncClient, session: AsyncSession
) -> None:
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 3})

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 201
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 1)) == 23
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 6)) == 5


async def test_insufficient_stock_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    """Stock drops after the cart was filled -- the realistic way this happens.

    The cart can no longer be over-filled directly, because add-time refuses
    more than the shelf holds. That cap is unlocked and advisory though, so a
    legitimately built cart can still go stale the moment someone else buys.
    Checkout is what catches it.
    """
    cart_id = await cart_with(client, product_id=6, quantity=8)

    product = await session.get(Product, 6)
    product.stock_quantity = 3
    await session.commit()

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 409
    assert "Cardamom 100g" in response.json()["detail"]


async def test_one_short_line_decrements_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    """All-or-nothing: the line that could have succeeded must not be touched."""
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 8})

    # Someone else buys the cardamom out from under this cart.
    product = await session.get(Product, 6)
    product.stock_quantity = 3
    await session.commit()

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 409
    # Rice was fine and still must not move.
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 1)) == 25
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 6)) == 3


async def test_empty_cart_cannot_be_checked_out(client: AsyncClient) -> None:
    cart_id = (await client.post("/carts")).json()["id"]

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 400


async def test_unknown_cart_cannot_be_checked_out(client: AsyncClient) -> None:
    response = await client.post("/carts/00000000-0000-0000-0000-000000000000/checkout")

    assert response.status_code == 404


async def test_locked_read_ignores_anything_cached_before(session: AsyncSession) -> None:
    """A locking read must report the row as it is now, not as it was cached.

    This is the shape of the bug that made an early version oversell while
    holding the lock correctly: something loads Product into the session's
    identity map, and SQLAlchemy then hands back that instance rather than the
    values just read under the lock. The arithmetic runs on a stale number and
    writes an absolute quantity, so stock lands on a plausible value and the
    CHECK constraint never fires.

    The regression is pinned with a live reference on purpose. The identity map
    holds weak references, so without one the cached Product is usually
    collected before the locking read and the bug hides -- it passed twelve
    consecutive suite runs while present.
    """
    await session.execute(update(Product).where(Product.id == 6).values(stock_quantity=1))
    await session.commit()

    # Load Product into the map the way loading a Cart entity would, and hold it.
    cached = await session.get(Product, 6)
    assert cached.stock_quantity == 1

    async with SessionLocal() as other:
        await other.execute(update(Product).where(Product.id == 6).values(stock_quantity=0))
        await other.commit()

    locked = (
        await session.scalars(
            select(Product)
            .where(Product.id.in_([6]))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()

    assert locked[0].stock_quantity == 0, (
        "the locking read returned a value cached before the lock -- "
        "checkout would decrement from a stale number and oversell"
    )
    assert cached.stock_quantity == 0
