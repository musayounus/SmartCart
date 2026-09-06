import uuid

from fastapi import APIRouter, Depends, status

from app.db import SessionDep
from app.http_cache import no_store
from app.schemas import CartItemIn, CartItemQuantity, CartOut, OrderOut
from app.services import cart as cart_service
from app.services import checkout as checkout_service
from app.services.rate_limit import enforce_checkout_rate_limit

router = APIRouter(prefix="/carts", tags=["carts"], dependencies=[Depends(no_store)])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CartOut)
async def create_cart(session: SessionDep) -> CartOut:
    return await cart_service.create_cart(session)


@router.post("/{cart_id}/items", response_model=CartOut)
async def add_item(cart_id: uuid.UUID, payload: CartItemIn, session: SessionDep) -> CartOut:
    return await cart_service.add_item(session, cart_id, payload.product_id, payload.quantity)


@router.patch("/{cart_id}/items/{product_id}", response_model=CartOut)
async def set_item_quantity(
    cart_id: uuid.UUID, product_id: int, payload: CartItemQuantity, session: SessionDep
) -> CartOut:
    return await cart_service.set_item_quantity(session, cart_id, product_id, payload.quantity)


@router.delete("/{cart_id}/items/{product_id}", response_model=CartOut)
async def remove_item(cart_id: uuid.UUID, product_id: int, session: SessionDep) -> CartOut:
    return await cart_service.remove_item(session, cart_id, product_id)


@router.get("/{cart_id}", response_model=CartOut)
async def get_cart(cart_id: uuid.UUID, session: SessionDep) -> CartOut:
    return await cart_service.load_cart(session, cart_id)


@router.post(
    "/{cart_id}/checkout",
    status_code=status.HTTP_201_CREATED,
    response_model=OrderOut,
    # The limiter sits in front of checkout as a dependency; the checkout
    # transaction itself is untouched by it.
    dependencies=[Depends(enforce_checkout_rate_limit)],
)
async def checkout(cart_id: uuid.UUID, session: SessionDep) -> OrderOut:
    return await checkout_service.checkout(session, cart_id)
