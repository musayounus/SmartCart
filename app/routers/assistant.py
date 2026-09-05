from fastapi import APIRouter, HTTPException, Query, status

from app.db import SessionDep
from app.schemas import ShoppingListOut
from app.services.assistant import known_dishes, shopping_list_for

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/shopping-list", response_model=ShoppingListOut)
async def shopping_list(
    session: SessionDep,
    dish: str = Query(description="Dish to shop for, e.g. kabsa", examples=["kabsa"]),
) -> ShoppingListOut:
    """Turn a dish into a shopping list matched against the catalog."""
    result = await shopping_list_for(session, dish)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No recipe known for {dish!r}. Known dishes: {', '.join(known_dishes())}",
        )
    return result
