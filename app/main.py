"""Application entry point.

Creates the FastAPI app, wires in middleware, routers, and a health check.
Run locally with:    uvicorn app.main:app --reload
Run in container:    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.repository import InMemoryItemRepository
from app.routers import items

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook.

    On startup we pick the storage backend: if `DATABASE_URL` is set we spin up
    the SQL repository (creating tables and a connection pool); otherwise we keep
    the in-memory default assigned below. On shutdown we dispose the DB engine.

    `app.db` is imported lazily here so the in-memory path never needs SQLAlchemy.
    """
    logger.info("Starting %s in %s mode", settings.app_name, settings.environment)

    if settings.database_url:
        from app.db import create_sql_repository

        repo, engine = await create_sql_repository(settings.database_url)
        app.state.item_repository = repo
        app.state.db_engine = engine
        logger.info("Storage backend: SQL database")
    else:
        logger.info("Storage backend: in-memory (no DATABASE_URL set)")

    yield

    engine = getattr(app.state, "db_engine", None)
    if engine is not None:
        await engine.dispose()
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    debug=settings.debug,
    lifespan=lifespan,
)

# Default storage backend. Set before the app handles any request, and used as-is
# unless the lifespan above swaps in a SQL backend. Assigning it here (not only in
# the lifespan) means the app also works when started without running lifespan
# events — e.g. a bare `TestClient(app)` in the test suite.
app.state.item_repository = InMemoryItemRepository()
app.state.db_engine = None

# CORS lets browsers on other origins call this API. Lock this down in prod.
# Note: the CORS spec forbids combining a "*" wildcard origin with credentials,
# so we only enable credentials when specific origins are configured.
allow_wildcard = settings.cors_origin_list == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=not allow_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount feature routers. Keep main.py thin; put real logic in routers.
app.include_router(items.router)


@app.get("/", tags=["meta"])
def root():
    """Friendly landing endpoint."""
    return {
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    """Liveness/readiness probe.

    Docker, Kubernetes, and load balancers hit this to decide whether the
    container is healthy. Keep it cheap and dependency-light.
    """
    return {"status": "ok"}
