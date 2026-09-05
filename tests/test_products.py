from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product
from app.seed import SEED_PRODUCTS, seed_products


async def test_lists_every_seeded_product(client: AsyncClient) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    assert len(response.json()) == len(SEED_PRODUCTS)


async def test_product_carries_the_fields_the_spec_asks_for(client: AsyncClient) -> None:
    product = (await client.get("/products")).json()[0]

    assert set(product) == {"id", "name", "price", "stock_quantity"}


async def test_price_is_not_serialised_as_a_float(client: AsyncClient) -> None:
    """Money must survive the round trip exactly, so it is never a JSON float."""
    product = (await client.get("/products")).json()[0]

    assert isinstance(product["price"], str)
    assert Decimal(product["price"]) == SEED_PRODUCTS[0]["price"]


async def test_seeding_twice_does_not_duplicate_rows(session: AsyncSession) -> None:
    await seed_products(session)

    count = len((await session.execute(select(Product))).scalars().all())
    assert count == len(SEED_PRODUCTS)


async def test_database_rejects_negative_stock(session: AsyncSession) -> None:
    """The core invariant, enforced independently of application logic."""
    session.add(Product(name="Oversold Item", price=Decimal("1.00"), stock_quantity=-1))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_database_rejects_negative_price(session: AsyncSession) -> None:
    session.add(Product(name="Free Money", price=Decimal("-1.00"), stock_quantity=1))

    with pytest.raises(IntegrityError):
        await session.commit()
