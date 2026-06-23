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
| GET | `/banner` | Logs an ASCII banner to the **server logs**, returns a JSON ack |
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
- **docker-compose.yml** — one-command run; brings up the API with a `pg_cron`-enabled
  PostgreSQL service that schedules jobs inside the database.
- **Tests** — fast `TestClient`-based smoke tests (`pytest`), in-memory and SQLite-backed.
- **uv project** — dependencies in `pyproject.toml`, locked in `uv.lock` for reproducible builds.
- **.dockerignore / .env.example** — clean builds and 12-factor configuration.

## CLI client

`cli.py` is a tiny HTTP client that talks to a **running** server, demonstrating
the request → handler → log loop. Start the server first, then in another terminal:

```bash
uv run cli.py                 # against http://localhost:8000
uv run cli.py --url http://host:port
```

It checks `/health`, calls `/banner` (watch the ASCII art appear in the *server's*
logs), then walks the items API (create → list → get → delete). If the server
isn't up it prints a friendly hint instead of a stack trace.

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

## Scheduled jobs (pg_cron)

The Postgres service is built from `db/` (`postgres:16` + the [`pg_cron`](https://github.com/citusdata/pg_cron)
extension) so the **database can schedule its own jobs** on cron syntax — no extra process.
`db/init.sql` registers a demo job that appends a row to `cron_heartbeat` every minute.

```bash
docker compose up --build
# wait a minute, then watch it tick:
docker compose exec db psql -U app -d app -c \
  "SELECT * FROM cron_heartbeat ORDER BY ran_at DESC LIMIT 5;"
```

Inspect the schedule with `SELECT * FROM cron.job;` and run history with
`SELECT * FROM cron.job_run_details;`. Note: `db/init.sql` runs **only on a fresh data
volume** — if you'd already started the stack, re-bootstrap with `docker compose down -v &&
docker compose up --build` (this deletes DB data). See GUIDE.md §11 for the full walkthrough.
