from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product

# Prices in SAR. Stock is deliberately small so the concurrency behaviour is
# easy to demonstrate live.
SEED_PRODUCTS = [
    {"name": "Basmati Rice 5kg", "price": Decimal("42.00"), "stock_quantity": 25},
    {"name": "Chicken Breast 1kg", "price": Decimal("28.50"), "stock_quantity": 15},
    {"name": "Medjool Dates 500g", "price": Decimal("35.75"), "stock_quantity": 12},
    {"name": "Olive Oil 1L", "price": Decimal("48.00"), "stock_quantity": 20},
    {"name": "Laban 1L", "price": Decimal("7.25"), "stock_quantity": 40},
    {"name": "Cardamom 100g", "price": Decimal("19.90"), "stock_quantity": 8},
    {"name": "Tomatoes 1kg", "price": Decimal("6.50"), "stock_quantity": 30},
]


async def seed_products(session: AsyncSession) -> None:
    """Insert the demo catalog. Idempotent, so a restart never duplicates rows."""
    statement = (
        insert(Product).values(SEED_PRODUCTS).on_conflict_do_nothing(index_elements=["name"])
    )
    await session.execute(statement)
    await session.commit()
