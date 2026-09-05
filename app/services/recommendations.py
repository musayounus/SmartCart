from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import OrderItem, Product
from app.schemas import RecommendationOut


async def frequently_bought_with(
    session: AsyncSession, product_id: int, limit: int = 3
) -> list[RecommendationOut]:
    """Products that have appeared in the same orders as this one.

    A self-join on order_items: find every order containing the target
    product, then count what else those orders contained. No model, no
    training, and the ranking is a number you can point at and verify by
    reading the order history.

    It inherits the usual co-occurrence weakness -- popular products look
    related to everything, because they co-occur with everything. With real
    traffic the fix is to normalise by how often each product is bought at
    all (lift rather than raw count).
    """
    target = aliased(OrderItem)
    other = aliased(OrderItem)

    rows = await session.execute(
        select(Product, func.count().label("times"))
        .select_from(target)
        .join(other, target.order_id == other.order_id)
        .join(Product, Product.id == other.product_id)
        .where(target.product_id == product_id, other.product_id != product_id)
        .group_by(Product.id)
        .order_by(func.count().desc(), Product.id)
        .limit(limit)
    )

    return [
        RecommendationOut(
            product_id=product.id,
            name=product.name,
            price=product.price,
            bought_together_count=times,
        )
        for product, times in rows
    ]
