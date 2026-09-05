from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product
from app.schemas import ShoppingListItemOut, ShoppingListOut

# Dish -> ingredients, and ingredient -> the catalog words that identify it.
#
# This is a lookup table, not a model. It is deterministic, works offline, and
# cannot fail mid-demo, which is the right trade for a walkthrough. The natural
# upgrade is an LLM resolving arbitrary dishes with the catalog passed as
# grounding, falling back to this table when the call fails -- the matching and
# response shape below would not change, only where `ingredients` comes from.
DISH_INGREDIENTS: dict[str, list[str]] = {
    "kabsa": ["rice", "chicken", "cardamom", "tomatoes", "onion"],
    "biryani": ["rice", "chicken", "cardamom", "yoghurt"],
    "shakshuka": ["tomatoes", "eggs", "olive oil"],
    "mandi": ["rice", "chicken", "cardamom"],
    "salad": ["tomatoes", "olive oil"],
    "dates and coffee": ["dates", "cardamom"],
}

# Ingredient -> substrings to look for in product names. Kept separate from the
# dish table so an ingredient's matching rules are defined once.
INGREDIENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "rice": ("rice",),
    "chicken": ("chicken",),
    "cardamom": ("cardamom",),
    "tomatoes": ("tomato",),
    "dates": ("dates",),
    "olive oil": ("olive oil",),
    "yoghurt": ("laban", "yoghurt"),
}


def known_dishes() -> list[str]:
    return sorted(DISH_INGREDIENTS)


def _match(ingredient: str, products: list[Product]) -> Product | None:
    """First catalog product whose name contains one of the ingredient's keywords."""
    for keyword in INGREDIENT_KEYWORDS.get(ingredient, (ingredient,)):
        for product in products:
            if keyword in product.name.lower():
                return product
    return None


async def shopping_list_for(session: AsyncSession, dish: str) -> ShoppingListOut | None:
    """Resolve a dish into catalog products, and say what it could not supply.

    Returning the unmatched ingredients matters: a shopping list that silently
    drops the eggs is worse than one that admits the shop has no eggs.
    """
    ingredients = DISH_INGREDIENTS.get(dish.strip().lower())
    if ingredients is None:
        return None

    products = list(await session.scalars(select(Product).order_by(Product.id)))

    items: list[ShoppingListItemOut] = []
    unavailable: list[str] = []

    for ingredient in ingredients:
        product = _match(ingredient, products)
        if product is None:
            unavailable.append(ingredient)
        else:
            items.append(
                ShoppingListItemOut(
                    ingredient=ingredient,
                    product_id=product.id,
                    name=product.name,
                    price=product.price,
                    in_stock=product.stock_quantity > 0,
                )
            )

    return ShoppingListOut(
        dish=dish.strip().lower(),
        items=items,
        unavailable=unavailable,
        estimated_total=sum((i.price for i in items), Decimal("0.00")),
    )
