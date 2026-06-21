# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **teaching-oriented, production-grade boilerplate** for running a FastAPI + uvicorn HTTP
server in Docker. The point of the repo is to be exemplary and well-explained, not to grow
features: `project/vault/GUIDE.md` is a from-scratch walkthrough (Docker basics → deploy) and
every source file is heavily commented for a reader new to Docker. **Preserve that pedagogical
tone** — when you change code, keep the explanatory comments accurate rather than stripping them.

## Tooling: uv + Python 3.13

Follows the `~/dev` house style: dependencies are managed with [`uv`](https://docs.astral.sh/uv/)
via `pyproject.toml` + `uv.lock`, Python pinned to **3.13** (`.python-version`). Runtime deps are
under `[project.dependencies]`; test tooling (`pytest`, `httpx`) under `[dependency-groups.dev]`.
Dependencies are pinned exactly (`==`) for reproducibility — bump deliberately with `uv add` /
`uv lock --upgrade`, not by accident. The Docker image targets `python:3.13-slim`.

Note: this directory is **not its own git repo** (and `~/dev` isn't either). Don't assume git.

## Commands

```bash
# Run with Docker (the primary path)
docker compose up --build        # → http://localhost:8000/docs ; /health for liveness

# Run locally without Docker
uv sync                          # create .venv + install locked deps
uv run uvicorn app.main:app --reload    # --reload = auto-restart on code change

# Tests (TestClient-based, no running server needed)
uv run pytest                                          # all tests
uv run pytest tests/test_main.py::test_item_crud_flow  # a single test
```

## Architecture

Standard "thin entrypoint + feature routers + env config" FastAPI layout:

- **`app/main.py`** — builds the `FastAPI` app: CORS middleware, the `lifespan` context manager,
  and the `/` + `/health` meta endpoints. `lifespan` also **selects the storage backend** (see
  below) and stores it on `app.state.item_repository`. Keep this file thin; real logic goes in
  routers. `app.include_router(...)` mounts features.
- **`app/routers/`** — one module per feature. `items.py` is the reference CRUD router: async
  handlers, `APIRouter(prefix=..., tags=...)`, status codes, `HTTPException`, and a
  `Depends(get_repository)` that pulls the repo off `app.state`. **Add a feature by creating a
  router here and including it in `main.py`.**
- **`app/schemas.py`** — Pydantic `ItemIn`/`ItemOut`, shared by the router and the repositories
  (separate module to avoid a router↔repository import cycle).
- **`app/repository.py`** — the `ItemRepository` Protocol and the dependency-free
  `InMemoryItemRepository`. Imports nothing third-party.
- **`app/db.py`** — the SQLAlchemy (async) `SqlItemRepository` + `create_sql_repository()`. Serves
  both SQLite and Postgres. **Imported lazily** from `main.py` only when `DATABASE_URL` is set.
- **`app/config.py`** — `Settings` (pydantic-settings `BaseSettings`) reads env vars + an optional
  `.env`. Access via the `@lru_cache`d `get_settings()`. Add config as typed fields; they map 1:1
  onto `.env.example`. `database_url` selects the backend.
- **`app/__init__.py`** — holds `__version__`, surfaced at `/` and as the OpenAPI version.

### Things to know

- **Three storage backends behind one `ItemRepository` interface, chosen at startup by
  `DATABASE_URL`:** unset → in-memory (default, no deps, resets on restart); `sqlite+aiosqlite://…`
  → SQLite; `postgresql+asyncpg://…` → Postgres. The SQL backends need the optional `db` extra
  (`uv sync --extra db`); the image bundles it, `docker compose` runs against Postgres. **Don't add
  SQLAlchemy imports at module top-level in the in-memory/router path** — `app/db.py` is imported
  lazily on purpose so the default install stays light.
- **A default in-memory repo is assigned to `app.state` at import time** (not only in `lifespan`),
  so a bare `TestClient(app)` works without running lifespan events. Tests that need a real backend
  build their own app with a lifespan (see `test_sqlite_backend_persists`).
- **CORS + credentials interplay:** `main.py` deliberately disables `allow_credentials` when
  `cors_origins` is the `*` wildcard, because the CORS spec forbids combining them. Preserve that
  guard if you touch the middleware.
- **Health check is wired in three places** — `/health` in `main.py`, plus a `HEALTHCHECK` in the
  `Dockerfile` and `docker-compose.yml` that curl `/health` via `urllib`. Keep `/health` cheap and
  dependency-free, and keep the three in sync.
- **Dockerfile is multi-stage** (builder installs deps into `/opt/venv`, runtime copies only that +
  `app/`) and runs as a **non-root `appuser`**. Only `app/` is copied into the image — tests and
  config files are not.
