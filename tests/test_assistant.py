from decimal import Decimal

from httpx import AsyncClient


async def test_kabsa_returns_matching_catalog_products(client: AsyncClient) -> None:
    response = await client.get("/assistant/shopping-list", params={"dish": "kabsa"})

    assert response.status_code == 200
    names = [i["name"] for i in response.json()["items"]]
    assert "Basmati Rice 5kg" in names
    assert "Chicken Breast 1kg" in names
    assert "Cardamom 100g" in names


async def test_reports_ingredients_the_catalog_cannot_supply(client: AsyncClient) -> None:
    """A list that silently drops the onion is worse than one that admits it."""
    body = (await client.get("/assistant/shopping-list", params={"dish": "kabsa"})).json()

    assert "onion" in body["unavailable"]
    assert "rice" not in body["unavailable"]


async def test_estimated_total_is_the_sum_of_matched_products(client: AsyncClient) -> None:
    body = (await client.get("/assistant/shopping-list", params={"dish": "kabsa"})).json()

    expected = sum(Decimal(i["price"]) for i in body["items"])
    assert Decimal(body["estimated_total"]) == expected


async def test_each_item_reports_stock_availability(client: AsyncClient) -> None:
    body = (await client.get("/assistant/shopping-list", params={"dish": "kabsa"})).json()

    assert all(item["in_stock"] is True for item in body["items"])


async def test_dish_lookup_ignores_case_and_padding(client: AsyncClient) -> None:
    response = await client.get("/assistant/shopping-list", params={"dish": "  KaBsA  "})

    assert response.status_code == 200
    assert response.json()["dish"] == "kabsa"


async def test_yoghurt_matches_laban(client: AsyncClient) -> None:
    """Ingredient keywords map local names onto catalog names."""
    body = (await client.get("/assistant/shopping-list", params={"dish": "biryani"})).json()

    matched = {i["ingredient"]: i["name"] for i in body["items"]}
    assert matched["yoghurt"] == "Laban 1L"


async def test_unknown_dish_lists_what_it_does_know(client: AsyncClient) -> None:
    response = await client.get("/assistant/shopping-list", params={"dish": "lasagne"})

    assert response.status_code == 404
    # Title case: the message is for a person, the lowercase key is for lookup.
    assert "Kabsa" in response.json()["detail"]


async def test_dish_is_required(client: AsyncClient) -> None:
    response = await client.get("/assistant/shopping-list")

    assert response.status_code == 422


async def test_known_dishes_are_listed(client: AsyncClient) -> None:
    """So a client can offer the dishes instead of making someone guess."""
    response = await client.get("/assistant/dishes")

    assert response.status_code == 200
    assert "kabsa" in response.json()


async def test_unknown_dish_message_reads_in_title_case(client: AsyncClient) -> None:
    """Lowercase is the lookup key, not what a person should be shown."""
    detail = (await client.get("/assistant/shopping-list", params={"dish": "lasagne"})).json()[
        "detail"
    ]

    assert "Kabsa" in detail
