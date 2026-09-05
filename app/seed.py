from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, Product

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


# Past orders, so "frequently bought together" has something to work with at
# demo time rather than starting empty. Each inner list is one order.
SEED_ORDER_BASKETS = [
    ["Basmati Rice 5kg", "Chicken Breast 1kg"],
    ["Basmati Rice 5kg", "Chicken Breast 1kg", "Cardamom 100g"],
    ["Basmati Rice 5kg", "Chicken Breast 1kg"],
    ["Basmati Rice 5kg", "Cardamom 100g"],
    ["Medjool Dates 500g", "Cardamom 100g"],
    ["Medjool Dates 500g", "Cardamom 100g"],
    ["Laban 1L", "Tomatoes 1kg"],
]


async def seed_products(session: AsyncSession) -> None:
    """Insert the demo catalog. Idempotent, so a restart never duplicates rows."""
    statement = (
        insert(Product).values(SEED_PRODUCTS).on_conflict_do_nothing(index_elements=["name"])
    )
    await session.execute(statement)
    await session.commit()


async def seed_order_history(session: AsyncSession) -> None:
    """Insert past orders for the recommendations endpoint.

    These are records of prior activity and deliberately do NOT decrement
    current stock: the seeded stock figures are the starting point for the
    concurrency demo, and quietly reducing them here would make those numbers
    confusing to reason about. A real system would have decremented at the
    time; this is demo scaffolding, not a simulation.

    Idempotent by count -- if any orders exist, assume seeding already ran.
    """
    if await session.scalar(select(func.count()).select_from(Order)):
        return

    products = {p.name: p for p in (await session.scalars(select(Product))).all()}

    for basket in SEED_ORDER_BASKETS:
        items = [products[name] for name in basket if name in products]
        if not items:
            continue

        order = Order(status="confirmed", total=sum((p.price for p in items), Decimal("0.00")))
        session.add(order)
        await session.flush()

        for product in items:
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=1,
                    price_at_purchase=product.price,
                )
            )

    await session.commit()
