"""The test the project exists to pass.

Concurrency here is real: httpx's ASGITransport dispatches every request into
the same event loop, and each one opens its own database session, so N
overlapping Postgres transactions genuinely compete for the same rows. A
synchronous TestClient would serialise them and pass whether or not any
locking existed.

Single-process is sufficient because the invariant is enforced by Postgres row
locks and a CHECK constraint, not by in-process coordination -- so it holds
identically across multiple workers or hosts.
"""

import asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Product

CONTESTED_PRODUCT = 1


async def set_stock(session: AsyncSession, quantity: int) -> None:
    await session.execute(
        update(Product).where(Product.id == CONTESTED_PRODUCT).values(stock_quantity=quantity)
    )
    await session.commit()


async def checkout_one_unit() -> int:
    """One shopper, start to finish, on their own connection."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cart_id = (await client.post("/carts")).json()["id"]
        await client.post(
            f"/carts/{cart_id}/items", json={"product_id": CONTESTED_PRODUCT, "quantity": 1}
        )
        response = await client.post(f"/carts/{cart_id}/checkout")
        return response.status_code


async def test_concurrent_checkouts_cannot_oversell(session: AsyncSession) -> None:
    stock, shoppers = 3, 10
    await set_stock(session, stock)

    results = await asyncio.gather(*(checkout_one_unit() for _ in range(shoppers)))

    assert results.count(201) == stock, f"expected {stock} winners, got {results.count(201)}"
    assert results.count(409) == shoppers - stock

    remaining = await session.scalar(
        select(Product.stock_quantity).where(Product.id == CONTESTED_PRODUCT)
    )
    assert remaining == 0


async def test_stock_never_goes_negative_when_demand_far_exceeds_supply(
    session: AsyncSession,
) -> None:
    await set_stock(session, 1)

    results = await asyncio.gather(*(checkout_one_unit() for _ in range(20)))

    assert results.count(201) == 1
    remaining = await session.scalar(
        select(Product.stock_quantity).where(Product.id == CONTESTED_PRODUCT)
    )
    assert remaining == 0


async def checkout_two_products(first: int, second: int) -> int:
    """A multi-line order, with the lines added in a caller-chosen order."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cart_id = (await client.post("/carts")).json()["id"]
        for product_id in (first, second):
            await client.post(
                f"/carts/{cart_id}/items", json={"product_id": product_id, "quantity": 1}
            )
        response = await client.post(f"/carts/{cart_id}/checkout")
        return response.status_code


async def test_multi_line_orders_in_opposing_order_do_not_deadlock(
    session: AsyncSession,
) -> None:
    """Two orders grabbing the same two products in opposite order would
    deadlock if each locked them in the order the client happened to add them:
    one holds A and waits for B while the other holds B and waits for A, and
    Postgres kills one of them. The locking read sorts by product id, so every
    transaction takes locks in the same order and the cycle cannot form.

    A deadlock would surface as a 500, so the assertion is that all of these
    succeed rather than that some specific one does.
    """
    results = await asyncio.gather(
        *(checkout_two_products(1, 7) for _ in range(6)),
        *(checkout_two_products(7, 1) for _ in range(6)),
    )

    assert results.count(201) == 12, f"expected 12 clean checkouts, got {results}"

    for product_id, seeded in ((1, 25), (7, 30)):
        remaining = await session.scalar(
            select(Product.stock_quantity).where(Product.id == product_id)
        )
        assert remaining == seeded - 12


async def test_everyone_succeeds_when_stock_is_sufficient(session: AsyncSession) -> None:
    """The lock must not reject orders that should have been fine."""
    await set_stock(session, 10)

    results = await asyncio.gather(*(checkout_one_unit() for _ in range(5)))

    assert results.count(201) == 5
    remaining = await session.scalar(
        select(Product.stock_quantity).where(Product.id == CONTESTED_PRODUCT)
    )
    assert remaining == 5
