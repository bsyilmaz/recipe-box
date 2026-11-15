import pytest
from fastapi.testclient import TestClient

from main import app, format_quantity, scale_ingredient

client = TestClient(app)


def make_recipe(ingredients):
    r = client.post(
        "/recipes",
        json={"title": "Scaling test", "ingredients": ingredients, "tags": ["test"]},
    )
    assert r.status_code == 200
    return r.json()["id"]


# --- endpoint ---------------------------------------------------------------


def test_scales_every_quantity_by_factor_2():
    rid = make_recipe(["200 g flour", "2 eggs", "300 ml milk"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.status_code == 200
    assert r.json()["ingredients"] == ["400 g flour", "4 eggs", "600 ml milk"]


def test_response_shape_matches_get_recipe():
    rid = make_recipe(["200 g flour"])
    plain = client.get(f"/recipes/{rid}").json()
    scaled = client.get(f"/recipes/{rid}/scaled", params={"factor": 2}).json()
    assert scaled.keys() == plain.keys()
    assert scaled["id"] == plain["id"]
    assert scaled["title"] == plain["title"]
    assert scaled["tags"] == plain["tags"]


def test_ingredients_without_quantity_are_unchanged():
    rid = make_recipe(["salt to taste", "200 g flour", "a pinch of pepper"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 3})
    assert r.json()["ingredients"] == ["salt to taste", "600 g flour", "a pinch of pepper"]


def test_fractional_factor_and_decimal_quantity():
    rid = make_recipe(["1.5 kg potatoes", "3 eggs"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 0.5})
    assert r.status_code == 200
    assert r.json()["ingredients"] == ["0.75 kg potatoes", "1.5 eggs"]


def test_fractions_and_ranges_left_unchanged_on_purpose():
    unchanged = ["1/2 cup milk", "2-3 eggs", "1,5 l water"]
    rid = make_recipe(unchanged)
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.json()["ingredients"] == unchanged


def test_recipe_with_no_ingredients():
    rid = make_recipe([])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.status_code == 200
    assert r.json()["ingredients"] == []


def test_stored_recipe_is_not_modified():
    rid = make_recipe(["200 g flour"])
    client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert client.get(f"/recipes/{rid}").json()["ingredients"] == ["200 g flour"]


def test_unknown_recipe_returns_404():
    r = client.get("/recipes/99999999/scaled", params={"factor": 2})
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown recipe"


@pytest.mark.parametrize("factor", ["0", "-2", "abc", "", "nan", "inf"])
def test_bad_factor_returns_422(factor):
    rid = make_recipe(["200 g flour"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": factor})
    assert r.status_code == 422


def test_missing_factor_returns_422():
    rid = make_recipe(["200 g flour"])
    r = client.get(f"/recipes/{rid}/scaled")
    assert r.status_code == 422


# --- parsing rule and formatting -------------------------------------------


@pytest.mark.parametrize(
    "ingredient, factor, expected",
    [
        ("200 g flour", 2, "400 g flour"),
        ("1.5kg rice", 2, "3kg rice"),
        ("2 eggs", 1.5, "3 eggs"),
        ("1 cup sugar", 1 / 3, "0.33 cup sugar"),
        ("salt", 2, "salt"),
        ("1/2 cup milk", 2, "1/2 cup milk"),
        ("2-3 eggs", 2, "2-3 eggs"),
        ("100", 2, "200"),
    ],
)
def test_scale_ingredient(ingredient, factor, expected):
    assert scale_ingredient(ingredient, factor) == expected


@pytest.mark.parametrize(
    "value, expected",
    [(400.0, "400"), (0.5, "0.5"), (0.75, "0.75"), (1 / 3, "0.33"), (10.0, "10")],
)
def test_format_quantity(value, expected):
    assert format_quantity(value) == expected
