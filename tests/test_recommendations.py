from httpx import AsyncClient

RICE, CHICKEN, CARDAMOM, DATES = 1, 2, 6, 3


async def test_recommends_products_bought_in_the_same_orders(client: AsyncClient) -> None:
    """Rice and chicken appear together in three seeded baskets."""
    response = await client.get(f"/products/{RICE}/recommendations")

    assert response.status_code == 200
    names = [r["name"] for r in response.json()]
    assert "Chicken Breast 1kg" in names


async def test_ranked_by_how_often_they_co_occur(client: AsyncClient) -> None:
    results = await client.get(f"/products/{RICE}/recommendations")
    counts = [r["bought_together_count"] for r in results.json()]

    assert counts == sorted(counts, reverse=True)
    # Chicken shares three baskets with rice, cardamom only two.
    assert results.json()[0]["name"] == "Chicken Breast 1kg"


async def test_never_recommends_the_product_itself(client: AsyncClient) -> None:
    results = (await client.get(f"/products/{RICE}/recommendations")).json()

    assert RICE not in [r["product_id"] for r in results]


async def test_returns_at_most_three(client: AsyncClient) -> None:
    results = (await client.get(f"/products/{RICE}/recommendations")).json()

    assert len(results) <= 3


async def test_product_with_no_shared_orders_returns_empty(client: AsyncClient) -> None:
    """Olive oil is seeded into no basket, so it has no co-occurrences."""
    results = (await client.get("/products/4/recommendations")).json()

    assert results == []


async def test_unknown_product_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/products/999/recommendations")

    assert response.status_code == 404


async def test_a_new_order_feeds_the_recommendations(client: AsyncClient) -> None:
    """The ranking is derived from order data, not a static table."""
    before = (await client.get("/products/4/recommendations")).json()
    assert before == []

    cart_id = (await client.post("/carts")).json()["id"]
    for product_id in (4, 5):
        await client.post(f"/carts/{cart_id}/items", json={"product_id": product_id, "quantity": 1})
    await client.post(f"/carts/{cart_id}/checkout")

    after = (await client.get("/products/4/recommendations")).json()
    assert [r["name"] for r in after] == ["Laban 1L"]
