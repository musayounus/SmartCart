from fastapi import APIRouter
from sqlalchemy import select

from app.db import SessionDep
from app.models import Product
from app.schemas import ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(session: SessionDep) -> list[Product]:
    result = await session.execute(select(Product).order_by(Product.id))
    return list(result.scalars().all())
