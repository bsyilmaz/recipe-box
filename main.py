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
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
def list_recipes(tag: str | None = None):
    """List recipes, optionally only those carrying `tag`.

    Tag matching is exact per tag (no substring matches), case-insensitive and
    ignores surrounding whitespace. A missing, empty or whitespace-only `tag`
    means "no filter" and returns every recipe, as before.
    """
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    recipes = [_row_to_recipe(r) for r in rows]
    wanted = (tag or "").strip().casefold()
    if not wanted:
        return recipes
    return [
        rec for rec in recipes
        if any(t.strip().casefold() == wanted for t in rec["tags"])
    ]


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


@app.get("/shopping-list")
def shopping_list(ids: str | None = None):
    """Merge the ingredients of the given recipes into a de-duplicated list.

    `ids` is a comma-separated list of positive recipe ids, e.g. `?ids=1,2,3`.
    Ingredients are compared case-insensitively after trimming and collapsing
    whitespace; the first spelling seen is kept. Order follows the requested
    recipe order, then each recipe's ingredient order. Blank ingredients are
    dropped. Repeated ids are counted once.
    """
    if ids is None or not ids.strip():
        raise HTTPException(status_code=400, detail="query parameter 'ids' is required, e.g. ?ids=1,2,3")
    recipe_ids: list[int] = []
    for part in ids.split(","):
        token = part.strip()
        if not (token.isascii() and token.isdigit()) or int(token) <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"invalid recipe id {token!r}: ids must be positive integers separated by commas",
            )
        rid = int(token)
        if rid not in recipe_ids:
            recipe_ids.append(rid)

    with closing(get_db()) as conn:
        placeholders = ",".join("?" * len(recipe_ids))
        rows = conn.execute(
            f"SELECT * FROM recipes WHERE id IN ({placeholders})", recipe_ids
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    missing = [rid for rid in recipe_ids if rid not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"unknown recipe id(s): {', '.join(str(m) for m in missing)}",
        )

    seen: set[str] = set()
    ingredients: list[str] = []
    for rid in recipe_ids:
        for item in json.loads(by_id[rid]["ingredients"]):
            display = " ".join(str(item).split())
            key = display.casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            ingredients.append(display)
    return {"recipe_ids": recipe_ids, "ingredients": ingredients, "count": len(ingredients)}
