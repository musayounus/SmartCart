from decimal import Decimal

from httpx import AsyncClient


async def create_cart(client: AsyncClient) -> str:
    response = await client.post("/carts")
    return response.json()["id"]


async def test_creating_a_cart_returns_an_id(client: AsyncClient) -> None:
    response = await client.post("/carts")

    assert response.status_code == 201
    assert response.json()["items"] == []
    assert response.json()["total"] == "0.00"


async def test_added_item_appears_with_a_line_total(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    cart = (await client.get(f"/carts/{cart_id}")).json()

    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2
    assert Decimal(cart["items"][0]["line_total"]) == Decimal("84.00")


async def test_total_is_the_sum_of_line_totals(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 5, "quantity": 4})
    cart = (await client.get(f"/carts/{cart_id}")).json()

    # 2 * 42.00 + 4 * 7.25
    assert Decimal(cart["total"]) == Decimal("113.00")


async def test_adding_the_same_product_twice_increments_one_line(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 3})
    cart = (await client.get(f"/carts/{cart_id}")).json()

    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 5


async def test_client_supplied_price_is_ignored(client: AsyncClient) -> None:
    """Totals come from the catalog. The input schema has no price field at all."""
    cart_id = await create_cart(client)

    await client.post(
        f"/carts/{cart_id}/items",
        json={"product_id": 1, "quantity": 1, "price": "0.01"},
    )
    cart = (await client.get(f"/carts/{cart_id}")).json()

    assert Decimal(cart["total"]) == Decimal("42.00")


async def test_adding_an_unknown_product_is_rejected(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    response = await client.post(f"/carts/{cart_id}/items", json={"product_id": 999, "quantity": 1})

    assert response.status_code == 404


async def test_adding_to_an_unknown_cart_is_rejected(client: AsyncClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"

    response = await client.post(f"/carts/{unknown}/items", json={"product_id": 1, "quantity": 1})

    assert response.status_code == 404


async def test_fetching_an_unknown_cart_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/carts/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_non_positive_quantity_is_rejected(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    for quantity in (0, -1):
        response = await client.post(
            f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": quantity}
        )
        assert response.status_code == 422
