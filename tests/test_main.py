"""Smoke tests using FastAPI's TestClient (no running server needed).

Run with:  uv run pytest

The default tests run against the in-memory backend (a bare `TestClient(app)`
doesn't trigger lifespan, so the app keeps its default in-memory repository).
`test_sqlite_backend_persists` exercises the SQL backend end-to-end.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["docs"] == "/docs"


def test_banner():
    r = client.get("/banner")
    assert r.status_code == 200
    assert r.json()["logged"] is True


def test_item_crud_flow():
    # Create
    r = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert r.status_code == 201
    item = r.json()
    assert item["id"] >= 1
    item_id = item["id"]

    # Read
    r = client.get(f"/items/{item_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Widget"

    # Delete
    r = client.delete(f"/items/{item_id}")
    assert r.status_code == 204

    # Confirm gone
    r = client.get(f"/items/{item_id}")
    assert r.status_code == 404


def test_validation_rejects_negative_price():
    r = client.post("/items", json={"name": "Bad", "price": -1})
    assert r.status_code == 422  # FastAPI auto-validates via Pydantic


def _sqlite_app(database_url: str) -> FastAPI:
    """A minimal app wired to the SQL backend at `database_url`.

    Builds the engine inside lifespan so engine creation and request handling
    share the TestClient's event loop. Requires the `db` extra (sqlalchemy +
    aiosqlite), which the dev dependency group installs.
    """
    from app.db import create_sql_repository
    from app.routers import items

    @asynccontextmanager
    async def lifespan(sql_app: FastAPI):
        repo, engine = await create_sql_repository(database_url)
        sql_app.state.item_repository = repo
        sql_app.state.db_engine = engine
        yield
        await engine.dispose()

    sql_app = FastAPI(lifespan=lifespan)
    sql_app.include_router(items.router)
    return sql_app


def test_sqlite_backend_persists(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    sql_app = _sqlite_app(url)

    # First app instance: create an item, then shut down (engine disposed).
    with TestClient(sql_app) as c:
        r = c.post("/items", json={"name": "Persisted", "price": 5.0})
        assert r.status_code == 201
        item_id = r.json()["id"]

    # A fresh instance against the same file still sees it — real persistence,
    # unlike the in-memory store which would have reset.
    with TestClient(sql_app) as c:
        r = c.get(f"/items/{item_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "Persisted"

        assert c.delete(f"/items/{item_id}").status_code == 204
        assert c.get(f"/items/{item_id}").status_code == 404
