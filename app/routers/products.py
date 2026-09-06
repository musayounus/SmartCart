from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.db import SessionDep
from app.http_cache import REVALIDATE, SHORT_CACHE, cached
from app.models import Product
from app.schemas import ProductOut, RecommendationOut
from app.services.recommendations import frequently_bought_with

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(request: Request, session: SessionDep) -> Response:
    result = await session.execute(select(Product).order_by(Product.id))
    products = [ProductOut.model_validate(p) for p in result.scalars().all()]

    # no-cache rather than max-age: stock changes on every checkout, and a
    # stale count would make the concurrency demo lie. The ETag still avoids
    # re-sending an unchanged catalog.
    return cached(request, products, REVALIDATE)


@router.get("/{product_id}/recommendations", response_model=list[RecommendationOut])
async def recommendations(product_id: int, request: Request, session: SessionDep) -> Response:
    """Products frequently bought alongside this one, by order co-occurrence."""
    if await session.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")

    # Co-occurrence shifts only as orders accumulate, so a minute of staleness
    # is harmless here in a way it would not be for stock.
    return cached(request, await frequently_bought_with(session, product_id), SHORT_CACHE)
