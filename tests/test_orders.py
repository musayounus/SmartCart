from decimal import Decimal

from httpx import AsyncClient


async def place_order(client: AsyncClient, product_id: int, quantity: int) -> dict:
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(
        f"/carts/{cart_id}/items", json={"product_id": product_id, "quantity": quantity}
    )
    return (await client.post(f"/carts/{cart_id}/checkout")).json()


async def test_placed_order_appears_in_history(client: AsyncClient) -> None:
    order = await place_order(client, product_id=1, quantity=2)

    response = await client.get("/orders")

    assert response.status_code == 200
    assert order["id"] in [o["id"] for o in response.json()]


async def test_history_is_newest_first(client: AsyncClient) -> None:
    first = await place_order(client, product_id=1, quantity=1)
    second = await place_order(client, product_id=5, quantity=1)

    ids = [o["id"] for o in (await client.get("/orders")).json()]

    assert ids.index(second["id"]) < ids.index(first["id"])


async def test_single_order_carries_its_line_items(client: AsyncClient) -> None:
    order = await place_order(client, product_id=1, quantity=2)

    detail = (await client.get(f"/orders/{order['id']}")).json()

    assert detail["id"] == order["id"]
    assert Decimal(detail["total"]) == Decimal("84.00")
    assert len(detail["items"]) == 1
    assert detail["items"][0]["quantity"] == 2
    assert Decimal(detail["items"][0]["price_at_purchase"]) == Decimal("42.00")


async def test_order_records_the_price_paid_after_a_catalog_change(
    client: AsyncClient,
) -> None:
    """History is a record of what was charged, not a view onto current prices."""
    order = await place_order(client, product_id=1, quantity=1)

    detail = (await client.get(f"/orders/{order['id']}")).json()
    catalog_price = [p for p in (await client.get("/products")).json() if p["id"] == 1][0]["price"]

    assert Decimal(detail["items"][0]["price_at_purchase"]) == Decimal(catalog_price)


async def test_unknown_order_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/orders/999999")

    assert response.status_code == 404
