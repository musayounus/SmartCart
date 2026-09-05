from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    await client.post(f"/carts/{cart_id}/checkout")

    product = await session.get(Product, 1)
    product.price = Decimal("99.00")
    await session.commit()

    recorded = await session.scalar(select(OrderItem.price_at_purchase))
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


async def test_insufficient_stock_is_rejected(client: AsyncClient) -> None:
    cart_id = await cart_with(client, product_id=6, quantity=9)  # only 8 in stock

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 409
    assert "Cardamom 100g" in response.json()["detail"]


async def test_one_short_line_decrements_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    """All-or-nothing: the line that could have succeeded must not be touched."""
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 99})

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 409
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 1)) == 25
    assert await session.scalar(select(Product.stock_quantity).where(Product.id == 6)) == 8


async def test_empty_cart_cannot_be_checked_out(client: AsyncClient) -> None:
    cart_id = (await client.post("/carts")).json()["id"]

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 400


async def test_unknown_cart_cannot_be_checked_out(client: AsyncClient) -> None:
    response = await client.post("/carts/00000000-0000-0000-0000-000000000000/checkout")

    assert response.status_code == 404
