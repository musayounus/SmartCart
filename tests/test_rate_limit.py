"""Rate limiting on checkout.

These tests set a deliberately tight limit rather than relying on the shipped
default. The default (60/minute) is set well above what the concurrency tests
burst, on purpose: a limit tight enough to interfere there would mask the
oversell proof rather than fail visibly. Testing the two concerns separately
keeps either from quietly degrading the other.
"""

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.rate_limit import limiter


@pytest.fixture
def tight_limit() -> object:
    original = settings.checkout_rate_limit
    settings.checkout_rate_limit = 2
    limiter.reset()
    yield
    settings.checkout_rate_limit = original
    limiter.reset()


async def checkout_once(client: AsyncClient) -> int:
    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})
    return (await client.post(f"/carts/{cart_id}/checkout")).status_code


async def test_checkouts_within_the_limit_succeed(client: AsyncClient, tight_limit) -> None:
    assert [await checkout_once(client) for _ in range(2)] == [201, 201]


async def test_exceeding_the_limit_returns_429(client: AsyncClient, tight_limit) -> None:
    for _ in range(2):
        await checkout_once(client)

    assert await checkout_once(client) == 429


async def test_rejection_tells_the_client_when_to_retry(client: AsyncClient, tight_limit) -> None:
    for _ in range(2):
        await checkout_once(client)

    cart_id = (await client.post("/carts")).json()["id"]
    await client.post(f"/carts/{cart_id}/items", json={"product_id": 1, "quantity": 1})
    response = await client.post(f"/carts/{cart_id}/checkout")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


async def test_a_rejected_checkout_does_not_consume_stock(client: AsyncClient, tight_limit) -> None:
    """The limiter runs before the transaction, so nothing is decremented."""
    for _ in range(2):
        await checkout_once(client)

    before = [p for p in (await client.get("/products")).json() if p["id"] == 1][0]
    assert await checkout_once(client) == 429
    after = [p for p in (await client.get("/products")).json() if p["id"] == 1][0]

    assert after["stock_quantity"] == before["stock_quantity"]


async def test_limit_of_zero_disables_the_limiter(client: AsyncClient) -> None:
    original = settings.checkout_rate_limit
    settings.checkout_rate_limit = 0
    limiter.reset()
    try:
        assert [await checkout_once(client) for _ in range(5)] == [201] * 5
    finally:
        settings.checkout_rate_limit = original
        limiter.reset()


async def test_browsing_is_not_rate_limited(client: AsyncClient, tight_limit) -> None:
    """Only checkout carries the limit; the catalog stays freely readable."""
    for _ in range(2):
        await checkout_once(client)

    assert (await client.get("/products")).status_code == 200
    assert (await client.post("/carts")).status_code == 201
