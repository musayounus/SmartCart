import uuid

from fastapi import APIRouter, status

from app.db import SessionDep
from app.schemas import CartItemIn, CartOut, OrderOut
from app.services import cart as cart_service
from app.services import checkout as checkout_service

router = APIRouter(prefix="/carts", tags=["carts"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CartOut)
async def create_cart(session: SessionDep) -> CartOut:
    return await cart_service.create_cart(session)


@router.post("/{cart_id}/items", response_model=CartOut)
async def add_item(cart_id: uuid.UUID, payload: CartItemIn, session: SessionDep) -> CartOut:
    return await cart_service.add_item(session, cart_id, payload.product_id, payload.quantity)


@router.get("/{cart_id}", response_model=CartOut)
async def get_cart(cart_id: uuid.UUID, session: SessionDep) -> CartOut:
    return await cart_service.load_cart(session, cart_id)


@router.post("/{cart_id}/checkout", status_code=status.HTTP_201_CREATED, response_model=OrderOut)
async def checkout(cart_id: uuid.UUID, session: SessionDep) -> OrderOut:
    return await checkout_service.checkout(session, cart_id)
