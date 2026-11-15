"""Recipe Box — starter app for Week 7.

A tiny FastAPI service for recipes and tags, with a static frontend. Use it as the
playground for concurrent multi-agent work and a generator-critic loop.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload
    # open http://localhost:8000/
Test:
    pytest
"""
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
DB_PATH = BASE / "recipes.db"

app = FastAPI(title="Recipe Box")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                ingredients TEXT NOT NULL,  -- JSON list of strings
                tags        TEXT NOT NULL   -- JSON list of strings
            )"""
        )
        conn.commit()


init_db()


class RecipeIn(BaseModel):
    title: str
    ingredients: list[str] = []
    tags: list[str] = []


def _row_to_recipe(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "ingredients": json.loads(row["ingredients"]),
        "tags": json.loads(row["tags"]),
    }


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.post("/recipes")
def create_recipe(recipe: RecipeIn):
    with closing(get_db()) as conn:
        cur = conn.execute(
            "INSERT INTO recipes (title, ingredients, tags) VALUES (?, ?, ?)",
            (recipe.title, json.dumps(recipe.ingredients), json.dumps(recipe.tags)),
        )
        conn.commit()
        rid = cur.lastrowid
    return {"id": rid, **recipe.model_dump()}


@app.get("/recipes")
def list_recipes():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    return [_row_to_recipe(r) for r in rows]


def _load_recipe(recipe_id: int) -> dict:
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    return _load_recipe(recipe_id)


# Parsing rule: an ingredient is scaled only when it STARTS with a plain number,
# an integer ("200") or a dot decimal ("1.5"), followed by a space, a letter or the
# end of the text ("200 g flour", "1.5kg rice", "3"). Anything else is returned
# unchanged on purpose: no leading number ("salt to taste"), fractions
# ("1/2 cup milk"), ranges ("2-3 eggs"), comma decimals ("1,5 l water").
# Results are rounded to 2 decimals.
LEADING_QUANTITY = re.compile(r"^(\d+(?:\.\d+)?)(?=\s|[^\W\d_]|$)")


def format_quantity(value: float) -> str:
    """Round to 2 decimals and drop trailing zeros: 400.0 -> "400", 0.50 -> "0.5"."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def scale_ingredient(ingredient: str, factor: float) -> str:
    match = LEADING_QUANTITY.match(ingredient)
    if match is None:
        return ingredient
    return format_quantity(float(match.group(1)) * factor) + ingredient[match.end():]


@app.get("/recipes/{recipe_id}/scaled")
def get_scaled_recipe(
    recipe_id: int,
    factor: float = Query(..., gt=0, allow_inf_nan=False, description="multiplier, must be > 0"),
):
    """Same shape as GET /recipes/{id}, ingredients scaled. The stored recipe is not changed."""
    recipe = _load_recipe(recipe_id)
    recipe["ingredients"] = [scale_ingredient(i, factor) for i in recipe["ingredients"]]
    return recipe
