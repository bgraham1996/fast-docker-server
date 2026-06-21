# fastapi-docker-server

A production-grade boilerplate for running a Python HTTP server (FastAPI + uvicorn) in a
Docker container. See **[GUIDE.md](./GUIDE.md)** for a full walkthrough from Docker basics
to deployment.

## Quick start

```bash
# With Docker (recommended)
docker compose up --build
# → http://localhost:8000/docs

# Without Docker (uses uv: https://docs.astral.sh/uv/)
uv sync
uv run uvicorn app.main:app --reload
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service metadata |
| GET | `/health` | Health check (`{"status":"ok"}`) |
| GET | `/docs` | Interactive API docs (Swagger UI) |
| GET | `/items` | List items |
| POST | `/items` | Create an item |
| GET | `/items/{id}` | Get one item |
| DELETE | `/items/{id}` | Delete an item |

## What's included

- **FastAPI app** with health check, CORS, env-based config, and an example CRUD router.
- **Multi-stage Dockerfile** — small final image, runs as a non-root user, with a built-in
  `HEALTHCHECK`.
- **Swappable storage** — runs on an in-memory store by default, or SQLite / PostgreSQL when
  `DATABASE_URL` is set, behind one `ItemRepository` interface.
- **docker-compose.yml** — one-command run; brings up the API with a PostgreSQL service.
- **Tests** — fast `TestClient`-based smoke tests (`pytest`), in-memory and SQLite-backed.
- **uv project** — dependencies in `pyproject.toml`, locked in `uv.lock` for reproducible builds.
- **.dockerignore / .env.example** — clean builds and 12-factor configuration.

## Tests

```bash
uv run pytest
```

## Configuration

Copy `.env.example` to `.env` and edit. Variables map to `app/config.py` and can also be
passed with `-e KEY=value` on `docker run` or via the orchestrator. Never commit real
secrets.

## Storage backends

The app picks its backend at startup from `DATABASE_URL` — same code, three modes:

| `DATABASE_URL` | Backend | Notes |
|----------------|---------|-------|
| _(unset)_ | In-memory dict | Default. Zero setup, resets on restart. |
| `sqlite+aiosqlite:///./app.db` | SQLite | Persists to a local file. |
| `postgresql+asyncpg://app:pw@db:5432/app` | PostgreSQL | What `docker compose` wires up. |

The SQLite/Postgres backends need the optional `db` dependencies:

```bash
uv sync --extra db                          # add SQLAlchemy + drivers
DATABASE_URL=sqlite+aiosqlite:///./app.db uv run uvicorn app.main:app --reload
```

`docker compose up --build` runs the API against PostgreSQL out of the box (the image bundles
the `db` extra). To run container-side with no database, comment out the `environment:` and
`depends_on:` blocks (and the `db` service) in `docker-compose.yml`.
