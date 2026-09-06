"""HTTP caching policy.

The interesting half of caching is what must *not* be cached. Serving a stale
cart leaks one shopper's basket to another; serving stale stock makes the
concurrency demo report numbers that are no longer true. Those are asserted
here as firmly as the positive cases.
"""

from httpx import AsyncClient


async def test_catalog_carries_an_etag(client: AsyncClient) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    assert response.headers["ETag"]


async def test_catalog_must_always_revalidate(client: AsyncClient) -> None:
    """no-cache, not max-age: stock must never be served stale."""
    response = await client.get("/products")

    assert response.headers["Cache-Control"] == "no-cache"


async def test_unchanged_catalog_returns_304(client: AsyncClient) -> None:
    first = await client.get("/products")

    second = await client.get("/products", headers={"If-None-Match": first.headers["ETag"]})

    assert second.status_code == 304
    assert second.content == b""


async def test_etag_changes_when_stock_changes(client: AsyncClient) -> None:
    """The validator has to track stock, or a 304 would hide a sold-out product."""
    before = (await client.get("/products")).headers["ETag"]

    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})
    await client.post(f"/carts/{cart_id}/checkout")

    after = (await client.get("/products")).headers["ETag"]
    assert before != after


async def test_stale_etag_gets_fresh_data_not_304(client: AsyncClient) -> None:
    stale = (await client.get("/products")).headers["ETag"]

    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})
    await client.post(f"/carts/{cart_id}/checkout")

    response = await client.get("/products", headers={"If-None-Match": stale})
    assert response.status_code == 200


async def test_recommendations_may_be_held_briefly(client: AsyncClient) -> None:
    response = await client.get("/products/1/recommendations")

    assert "max-age" in response.headers["Cache-Control"]


async def test_assistant_may_be_held_briefly(client: AsyncClient) -> None:
    response = await client.get("/assistant/shopping-list", params={"dish": "kabsa"})

    assert "max-age" in response.headers["Cache-Control"]


async def test_carts_are_never_cached(client: AsyncClient) -> None:
    """A shared cache holding a cart would serve it to a different shopper."""
    cart_id = (await client.post("/carts")).json()["id"]

    response = await client.get(f"/carts/{cart_id}")

    assert response.headers["Cache-Control"] == "no-store"


async def test_orders_are_never_cached(client: AsyncClient) -> None:
    response = await client.get("/orders")

    assert response.headers["Cache-Control"] == "no-store"


async def test_checkout_is_never_cached(client: AsyncClient) -> None:
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})

    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.headers["Cache-Control"] == "no-store"
