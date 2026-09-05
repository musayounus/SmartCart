from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db import Base, SessionDep, SessionLocal, engine
from app.routers import assistant, carts, orders, products
from app.seed import seed_order_history, seed_products


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Build the schema and seed the catalog.

    No Alembic: the schema is fixed for the life of this demo, so migrations
    would add a moving part without demonstrating anything. See the README.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_products(session)
        await seed_order_history(session)
    yield


app = FastAPI(title="SmartCart", version="0.1.0", lifespan=lifespan)
app.include_router(products.router)
app.include_router(carts.router)
app.include_router(orders.router)
app.include_router(assistant.router)


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    """Liveness probe that also proves the database link is wired up."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
