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


async def test_removing_a_line_leaves_the_others(client: AsyncClient) -> None:
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 5, "quantity": 4})

    response = await client.delete(f"/carts/{cart_id}/items/1")

    assert response.status_code == 200
    assert [i["product_id"] for i in response.json()["items"]] == [5]
    assert Decimal(response.json()["total"]) == Decimal("29.00")


async def test_removing_everything_empties_the_cart_without_destroying_it(
    client: AsyncClient,
) -> None:
    """The shopper keeps their cart; only the contents go."""
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})

    await client.delete(f"/carts/{cart_id}/items/1")
    cart = (await client.get(f"/carts/{cart_id}")).json()

    assert cart["items"] == []
    assert Decimal(cart["total"]) == Decimal("0.00")

    # Still usable afterwards.
    again = await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})
    assert again.status_code == 200


async def test_removing_a_line_that_is_not_there_is_rejected(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    response = await client.delete(f"/carts/{cart_id}/items/1")

    assert response.status_code == 404


async def test_removing_from_an_unknown_cart_is_rejected(client: AsyncClient) -> None:
    response = await client.delete("/carts/00000000-0000-0000-0000-000000000000/items/1")

    assert response.status_code == 404


async def test_reducing_a_line_keeps_it(client: AsyncClient) -> None:
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 3})

    response = await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": 1})

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 1
    assert Decimal(response.json()["total"]) == Decimal("42.00")


async def test_reducing_one_line_leaves_the_others_alone(client: AsyncClient) -> None:
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 3})
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 5, "quantity": 2})

    cart = (await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": 1})).json()

    quantities = {i["product_id"]: i["quantity"] for i in cart["items"]}
    assert quantities == {1: 1, 5: 2}
    # 1 * 42.00 + 2 * 7.25
    assert Decimal(cart["total"]) == Decimal("56.50")


async def test_reducing_is_idempotent(client: AsyncClient) -> None:
    """Absolute quantity, not a delta: a retried request must not reduce twice."""
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 3})

    await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": 2})
    cart = (await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": 2})).json()

    assert cart["items"][0]["quantity"] == 2


async def test_reducing_to_zero_is_rejected(client: AsyncClient) -> None:
    """Emptying a line is what DELETE is for."""
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 2})

    for quantity in (0, -1):
        response = await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": quantity})
        assert response.status_code == 422


async def test_reducing_a_line_that_is_not_there_is_rejected(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    response = await client.patch(f"/carts/{cart_id}/items/1", json={"quantity": 1})

    assert response.status_code == 404


async def test_cannot_add_more_than_the_shelf_holds(client: AsyncClient) -> None:
    """Cardamom is seeded at 8."""
    cart_id = await create_cart(client)

    response = await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 9})

    assert response.status_code == 409
    assert "8" in response.json()["detail"]


async def test_can_take_exactly_all_of_it(client: AsyncClient) -> None:
    cart_id = await create_cart(client)

    response = await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 8})

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 8


async def test_repeated_adds_are_capped_on_the_running_total(client: AsyncClient) -> None:
    """The check is against the resulting line, not the increment."""
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 6})

    response = await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 3})

    assert response.status_code == 409


async def test_cannot_raise_a_line_beyond_stock(client: AsyncClient) -> None:
    cart_id = await create_cart(client)
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 6, "quantity": 2})

    response = await client.patch(f"/carts/{cart_id}/items/6", json={"quantity": 9})

    assert response.status_code == 409


async def test_the_cart_cap_does_not_prevent_two_shoppers_holding_the_last_units(
    client: AsyncClient,
) -> None:
    """The cap is a courtesy, not a concurrency guarantee.

    Both baskets can hold every last unit at once, because the check reads
    stock without a lock. Checkout is the only thing that decides who gets
    them -- which is why removing FOR UPDATE still breaks the concurrency
    tests, and why this cap must never be mistaken for protection.

    If someone later turns this into a reservation without taking the lock
    checkout takes, this test fails and says why.
    """
    first = await create_cart(client)
    second = await create_cart(client)

    a = await client.post(f"/carts/{first}/items", json={"product_id": 6, "quantity": 8})
    b = await client.post(f"/carts/{second}/items", json={"product_id": 6, "quantity": 8})

    assert a.status_code == 200
    assert b.status_code == 200

    # Both hold all 8. Checkout, not the cap, resolves it.
    assert (await client.post(f"/carts/{first}/checkout")).status_code == 201
    assert (await client.post(f"/carts/{second}/checkout")).status_code == 409
