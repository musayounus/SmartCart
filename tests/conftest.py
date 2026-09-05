from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client speaking to the app in-process.

    ASGITransport (not TestClient) so concurrent requests issued with
    asyncio.gather genuinely overlap -- the concurrency test depends on this.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
