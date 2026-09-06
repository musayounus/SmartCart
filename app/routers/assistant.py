from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.db import SessionDep
from app.http_cache import SHORT_CACHE, cached
from app.schemas import ShoppingListOut
from app.services.assistant import known_dishes, shopping_list_for

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/dishes", response_model=list[str])
async def dishes(request: Request) -> Response:
    """The dishes the assistant knows, so a client can offer them rather than
    making someone guess and hit a 404."""
    return cached(request, known_dishes(), SHORT_CACHE)


@router.get("/shopping-list", response_model=ShoppingListOut)
async def shopping_list(
    request: Request,
    session: SessionDep,
    dish: str = Query(description="Dish to shop for, e.g. kabsa", examples=["kabsa"]),
) -> Response:
    """Turn a dish into a shopping list matched against the catalog."""
    result = await shopping_list_for(session, dish)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            # Title-cased for reading; the lookup itself stays lowercase.
            f"No recipe known for {dish!r}. "
            f"Known dishes: {', '.join(d.capitalize() for d in known_dishes())}",
        )
    # The dish mapping is static and prices move slowly.
    return cached(request, result, SHORT_CACHE)
