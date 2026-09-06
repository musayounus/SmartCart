from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base, SessionLocal, engine
from app.main import app
from app.seed import seed_order_history, seed_products
from app.services.rate_limit import limiter


@pytest.fixture(autouse=True)
async def schema() -> AsyncIterator[None]:
    """Rebuild the schema and reseed before every test.

    ASGITransport does not run the app's lifespan, so table creation happens
    here. Dropping between tests keeps them independent -- which the
    concurrency test depends on, since it asserts exact stock counts.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_products(session)
        await seed_order_history(session)
    # The rate limiter is process-global. Without this, checkouts accumulate
    # across tests and the concurrency tests start seeing 429s -- which would
    # look like a concurrency failure rather than a test-isolation problem.
    await limiter.reset()
    yield
    # pytest-asyncio gives each test its own event loop, but the engine's pool
    # caches connections bound to the loop that opened them. Disposing here
    # stops the next test inheriting a connection from a dead loop.
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client speaking to the app in-process.

    ASGITransport (not TestClient) so concurrent requests issued with
    asyncio.gather genuinely overlap -- the concurrency test depends on this.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Direct database access for arranging state and asserting on it."""
    async with SessionLocal() as s:
        yield s
