from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db import SessionDep
from app.models import Product
from app.schemas import ProductOut, RecommendationOut
from app.services.recommendations import frequently_bought_with

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(session: SessionDep) -> list[Product]:
    result = await session.execute(select(Product).order_by(Product.id))
    return list(result.scalars().all())


@router.get("/{product_id}/recommendations", response_model=list[RecommendationOut])
async def recommendations(product_id: int, session: SessionDep) -> list[RecommendationOut]:
    """Products frequently bought alongside this one, by order co-occurrence."""
    if await session.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    return await frequently_bought_with(session, product_id)
