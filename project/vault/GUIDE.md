# Running a Python HTTP Server in Docker — A Complete Guide

This guide takes you from "what is a container?" to a production-grade, containerized
FastAPI HTTP server you can run anywhere Docker runs. It assumes you're comfortable with
Python but new to Docker, so the Docker concepts are explained from the ground up.

By the end you'll understand every file in this project and be able to build, run, debug,
and deploy the server with confidence.

---

## Table of contents

1. [What problem does Docker solve?](#1-what-problem-does-docker-solve)
2. [Core Docker concepts](#2-core-docker-concepts)
3. [Install Docker](#3-install-docker)
4. [The application: FastAPI in 5 minutes](#4-the-application-fastapi-in-5-minutes)
5. [Run the app without Docker first](#5-run-the-app-without-docker-first)
6. [Anatomy of the Dockerfile](#6-anatomy-of-the-dockerfile)
7. [Build and run the image](#7-build-and-run-the-image)
8. [docker compose: one command to rule them all](#8-docker-compose-one-command-to-rule-them-all)
9. [A CLI client: watch the request → log loop](#9-a-cli-client-watch-the-request--log-loop)
10. [Configuration & secrets](#10-configuration--secrets)
11. [Scheduling jobs inside Postgres with pg_cron](#11-scheduling-jobs-inside-postgres-with-pg_cron)
12. [Production concerns](#12-production-concerns)
13. [Debugging & common errors](#13-debugging--common-errors)
14. [Command cheat sheet](#14-command-cheat-sheet)
15. [Project file reference](#15-project-file-reference)

---

## 1. What problem does Docker solve?

You've probably hit "it works on my machine" — code that runs locally but breaks on a
colleague's laptop or a server, because of a different Python version, a missing system
library, or an environment variable that only exists on your machine.

A **container** packages your application *together with* everything it needs to run — the
Python interpreter, your dependencies, system libraries, and config — into a single,
portable unit. That unit runs identically on your laptop, a teammate's machine, a CI
runner, and a production server.

A container is **not** a virtual machine. A VM boots a whole guest operating system
(gigabytes, slow to start). A container shares the host's kernel and isolates just your
application's processes and filesystem. The result starts in milliseconds and is far
lighter. Think of a container as "a process with its own private filesystem and network,"
not "a computer inside your computer."

---

## 2. Core Docker concepts

Four terms cover almost everything:

**Image** — a read-only template: a snapshot of a filesystem plus instructions for what to
run. Think of it like a class in OOP, or a `.iso`. You build an image once and reuse it.

**Container** — a running (or stopped) instance of an image. Like an object instantiated
from a class. You can start many containers from one image. Containers are disposable: the
right mental model is "cattle, not pets" — if one misbehaves, you delete it and start a new
one from the same image.

**Dockerfile** — a plain-text recipe listing the steps to build an image (start from this
base, copy these files, install these packages, run this command). Docker reads it
top-to-bottom and produces an image.

**Registry** — a place to store and share images. Docker Hub is the public default; cloud
providers (AWS ECR, Google Artifact Registry, GitHub Container Registry) host private ones.
`docker pull` downloads an image; `docker push` uploads one.

Two more you'll meet quickly:

**Layer** — each instruction in a Dockerfile creates a cached layer. If a layer's inputs
haven't changed, Docker reuses the cache instead of rebuilding — which is why instruction
*order* matters for build speed (more on this below).

**Volume / bind mount** — containers are ephemeral; anything written inside a container is
lost when it's removed. Volumes and bind mounts persist data (or share host files into the
container) past the container's lifetime.

---

## 3. Install Docker

Install **Docker Desktop** (Mac/Windows) or **Docker Engine** (Linux) from
<https://docs.docker.com/get-docker/>. Docker Desktop bundles the engine, the CLI, and
`docker compose`.

Verify it's working:

```bash
docker --version
docker run hello-world
```

The second command pulls a tiny test image from Docker Hub and runs it. If you see a
"Hello from Docker!" message, you're ready. On Linux you may need to either prefix commands
with `sudo` or add your user to the `docker` group.

---

## 4. The application: FastAPI in 5 minutes

The HTTP server in this project is built with **FastAPI**, a modern Python web framework.
You write plain functions, annotate them with types, and FastAPI handles request parsing,
validation, JSON serialization, and even generates interactive API documentation for free.

FastAPI is an **ASGI** application — the async successor to WSGI. It doesn't serve HTTP by
itself; it needs an ASGI **server** to handle the actual network sockets. We use
**uvicorn** for that. So the runtime chain is:

```
client (browser/curl) ──HTTP──▶ uvicorn (ASGI server) ──▶ FastAPI app (your code)
```

The project layout:

```
fastapi-docker-server/
├── app/
│   ├── __init__.py        # marks "app" as a Python package; holds __version__
│   ├── config.py          # settings read from environment variables
│   ├── main.py            # creates the FastAPI app, health check, wires routers
│   ├── schemas.py         # Pydantic request/response models (ItemIn, ItemOut)
│   ├── repository.py      # storage interface + in-memory backend
│   ├── db.py              # SQLAlchemy (async) backend — SQLite / PostgreSQL
│   └── routers/
│       ├── __init__.py
│       └── items.py       # example CRUD endpoints (/items)
├── tests/
│   └── test_main.py       # fast tests using FastAPI's TestClient
├── cli.py                 # tiny HTTP client that drives a running server (§9)
├── db/
│   ├── Dockerfile         # Postgres + pg_cron extension (§11)
│   └── init.sql           # bootstraps pg_cron + the heartbeat job
├── pyproject.toml         # project metadata + pinned dependencies (uv)
├── uv.lock                # fully resolved, locked dependency tree
├── .python-version        # Python version uv should use (3.13)
├── Dockerfile             # recipe to build the image
├── docker-compose.yml     # run the container (and friends) with one command
├── .dockerignore          # keeps junk out of the image
├── .env.example           # template for environment configuration
└── GUIDE.md               # this file
```

The key endpoints, all defined in `app/`:

- `GET /` — service metadata.
- `GET /health` — health check; returns `{"status": "ok"}`. Used by Docker and load
  balancers to decide if the container is alive.
- `GET /banner` — logs an ASCII banner to the *server's* logs and returns a small JSON
  ack. A teaching endpoint that makes the request → handler → log loop visible (see §9).
- `GET /docs` — auto-generated interactive API documentation (Swagger UI). Open it in a
  browser once the server is running.
- `GET/POST/DELETE /items` — a small CRUD example showing the patterns you'll reuse.

---

## 5. Run the app without Docker first

Before containerizing, confirm the app runs natively. This separates "is my code working?"
from "is my Docker setup working?" — debug one variable at a time.

This project is managed with [**uv**](https://docs.astral.sh/uv/), a fast Python package and
project manager. `uv sync` reads `pyproject.toml` + `uv.lock`, creates a `.venv`, and installs
the exact locked dependencies — no manual `venv`/`pip` steps. `uv run` then executes a command
inside that environment.

```bash
# From the project root
uv sync                          # create .venv and install locked dependencies

# Start the dev server with auto-reload
uv run uvicorn app.main:app --reload
```

`app.main:app` means "in the module `app/main.py`, use the object named `app`." Visit:

- <http://localhost:8000/> — JSON metadata
- <http://localhost:8000/health> — `{"status":"ok"}`
- <http://localhost:8000/docs> — interactive docs; try the `POST /items` endpoint there.

`--reload` watches your files and restarts on changes. **Never use `--reload` in
production** — it's slow and meant only for development.

Run the tests to be sure:

```bash
uv run pytest
```

---

## 6. Anatomy of the Dockerfile

Now the Docker part. This project uses a **multi-stage build**, which is the standard
professional pattern. Let's read it section by section (the full file is in `Dockerfile`).

### The base image

```dockerfile
FROM python:3.13-slim AS builder
```

`FROM` chooses the starting point — here, an official Python 3.13 image. The `-slim`
variant strips out rarely needed OS packages, giving a much smaller image than the default.
(There's also `-alpine`, even smaller, but Alpine uses a different C library that
occasionally breaks Python packages with compiled components, so `-slim` is the safer
default.) `AS builder` names this stage so a later stage can copy from it.

### Why two stages?

A **multi-stage build** uses one stage to *build* (where compilers and dev tools live) and a
second, clean stage to *run* (containing only what's needed at runtime). The final image
inherits nothing from the builder except the specific files you copy over — so build tools,
caches, and intermediate junk never ship to production. Smaller images pull faster, start
faster, and have a smaller attack surface.

```dockerfile
# Stage 1: install dependencies into a virtualenv with uv
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv   # the uv binary
ENV UV_PROJECT_ENVIRONMENT=/opt/venv      # put the venv at a fixed, copyable path
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project   # locked deps only, no test tooling

# Stage 2: the lean runtime image
FROM python:3.13-slim AS runtime
COPY --from=builder /opt/venv /opt/venv   # bring over only the installed deps
```

We grab the standalone `uv` binary straight from its official image (`COPY --from=...`),
so there's no `pip` bootstrap. `uv sync --frozen` installs the **exact** versions from
`uv.lock` (failing if the lock is stale), giving byte-for-byte reproducible builds.
`--no-dev` leaves test tooling out of the image, and `--no-install-project` installs only
the dependencies (the app source is copied separately in the runtime stage).

### Layer caching: why we copy the lockfile first

Notice we `COPY pyproject.toml uv.lock` and install dependencies **before** copying the
application source. Docker caches each instruction as a layer and reuses the cache when the
instruction's inputs are unchanged. Dependencies change rarely; your code changes
constantly. By installing dependencies in their own layer first, editing a Python file
doesn't invalidate the (slow) dependency-install layer — rebuilds drop from minutes to
seconds.

The rule: **order Dockerfile instructions from least-frequently-changing to
most-frequently-changing.**

### The environment variables

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
```

`PYTHONDONTWRITEBYTECODE=1` skips writing `.pyc` files (pointless in a disposable
container). `PYTHONUNBUFFERED=1` forces Python to flush logs immediately instead of
buffering them — essential so `docker logs` shows output in real time.

### Running as a non-root user

```dockerfile
RUN groupadd --system app && useradd --system --gid app --no-create-home appuser
USER appuser
```

By default, processes inside a container run as **root**. If your app is ever compromised,
a root process makes it easier for an attacker to escalate. Creating an unprivileged user
and switching to it with `USER` is a fundamental security best practice. Everything after
`USER appuser` runs without root privileges.

### The health check

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"
```

This tells Docker how to check the container is actually serving traffic, not just that the
process is running. Docker runs the command on the schedule given; after `--retries`
consecutive failures the container is marked `unhealthy`, which orchestrators and
`docker compose` can act on. We use a `python -c` one-liner instead of `curl` because the
slim image doesn't include curl — using the interpreter that's already there keeps the
image lean.

### The start command

```dockerfile
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`EXPOSE 8000` documents which port the app listens on (it doesn't actually publish it —
that's done at `run` time with `-p`). `CMD` is the default command run when the container
starts.

The single most common containerization mistake for beginners: binding to `127.0.0.1`
instead of `0.0.0.0`. Inside a container, `127.0.0.1` means "only this container can reach
me" — the outside world can't connect. **`--host 0.0.0.0` is required** so traffic from
outside the container reaches uvicorn.

`CMD` uses the JSON-array ("exec") form, not a plain string. The exec form runs the process
directly as PID 1, so it receives signals (like the `SIGTERM` Docker sends on `docker stop`)
and can shut down gracefully. The string form wraps the command in a shell that often
swallows those signals.

---

## 7. Build and run the image

Build the image from the project root (the `.` means "use the current directory as the
build context"):

```bash
docker build -t fastapi-docker-server:latest .
```

`-t` tags (names) the image. The first build downloads the base image and installs
dependencies; later builds reuse cached layers and are much faster.

Run a container from the image:

```bash
docker run --rm -p 8000:8000 fastapi-docker-server:latest
```

- `-p 8000:8000` maps **host port : container port**. Left side is the port on your
  machine; right side is what the app listens on inside. To serve on host port 9000
  instead, use `-p 9000:8000`.
- `--rm` deletes the container when it stops, so you don't accumulate dead containers.

Visit <http://localhost:8000/docs>. To run it in the background ("detached") and tail logs:

```bash
docker run -d --name myserver -p 8000:8000 fastapi-docker-server:latest
docker logs -f myserver        # follow logs
docker ps                      # see running containers (note STATUS shows health)
docker stop myserver           # stop it
docker rm myserver             # remove the stopped container
```

Pass configuration via environment variables at run time:

```bash
docker run --rm -p 8000:8000 -e ENVIRONMENT=production -e CORS_ORIGINS=https://app.example.com \
  fastapi-docker-server:latest
```

---

## 8. docker compose: one command to rule them all

Typing long `docker run` commands gets old, and real apps often need several containers
(an API plus a database, say). **docker compose** describes all of that declaratively in
`docker-compose.yml`, so you start everything with one command.

```bash
docker compose up --build      # build images if needed, then start everything
docker compose up -d           # same, but detached (in the background)
docker compose logs -f         # follow logs from all services
docker compose ps              # status
docker compose down            # stop and remove containers, networks
```

Our `docker-compose.yml` defines two services: `api` (built from the Dockerfile) and `db`
(a Postgres database). Compose puts them on a shared network where each reaches the other by
service name — that's why the API's `DATABASE_URL` uses the host `db`. `depends_on` with a
`service_healthy` condition makes the API wait until Postgres passes its `pg_isready`
health check before starting, so the first connection doesn't race the database coming up.
To run the API with no database, comment out its `environment:` and `depends_on:` blocks and
the `db` service — it falls back to the in-memory store (see §10).

For most local development and small deployments, `docker compose up` is all you need.

---

## 9. A CLI client: watch the request → log loop

So far you've talked to the server through a browser (`/docs`) or `curl`. Real systems are
usually driven by *other programs*. `cli.py` (at the project root) is a tiny example: a
**separate process** that talks to the running server over HTTP — exactly like a real
client, instead of importing the app in-process. It's a hands-on way to *see* the full loop:
a request leaves the client, the server's handler runs, and the server writes a log line you
can watch appear in real time.

It leans on a server endpoint built for exactly this lesson, `GET /banner`, defined in
`app/main.py`:

```python
BANNER = r"""
  ______        _      _    ____ ___
 |  ____|      | |    /\   |  _ \_ _|
 ...
"""

@app.get("/banner", tags=["meta"])
def banner():
    # logger.info writes to stdout — which is exactly where Docker collects logs.
    logger.info("Banner requested:\n%s", BANNER)
    return {"logged": True, "service": settings.app_name, "version": __version__}
```

The endpoint does nothing useful on purpose: it just logs ASCII art to the server's stdout
and returns a small JSON acknowledgement. The art shows up in the *server's* logs (the
`uvicorn` terminal, or the `docker compose` window) — **not** in the client's output. That
split is the whole point.

### Run it

You need the server running first — the CLI connects over the network, so something has to
be listening. Open **two terminals**.

Terminal 1 — start the server (either path works):

```bash
uv run uvicorn app.main:app --reload     # local
# ...or watch the container logs instead:
docker compose up --build                # containerized
```

Terminal 2 — run the client:

```bash
uv run cli.py                 # talks to http://localhost:8000 by default
uv run cli.py --url http://localhost:8000
```

The client prints its own progress and walks the items API end to end:

```
[+] /health        -> {'status': 'ok'}
[+] /banner        -> {'logged': True, ...}  (check the server logs for art!)
--- items API walkthrough ---
[+] POST   /items          -> created #1: {...}
[+] GET    /items          -> 1 item(s)
[+] GET    /items/1        -> {...}
[+] DELETE /items/1        -> 204 No Content
[+] GET    /items/1        -> 404 (expected 404)
```

Now glance back at **Terminal 1**: the ASCII banner has appeared in the server's logs, the
moment the `/banner` request arrived. Under Docker, the same line shows up in
`docker compose logs -f` — a concrete demonstration of §12's rule that containers log to
stdout and the platform collects it.

### Things worth noticing

- **The CLI needs the server up.** If nothing's listening it prints a friendly hint
  (`is the server running?`) and exits with a non-zero status instead of dumping a stack
  trace — the same convention a script in CI would want.
- **`httpx` is a runtime dependency.** Because `cli.py` ships as part of the project (not
  just tests), `httpx` lives under `[project.dependencies]` in `pyproject.toml`, so a plain
  `uv sync` makes `uv run cli.py` work. (FastAPI's `TestClient` is built on `httpx` too, so
  it's a single shared pin.)
- **It's a client, not a test.** It's named `cli.py`, not `tests.py`, to keep it distinct
  from the real `pytest` suite in `tests/`. The CLI proves the *running* server works over
  the network; the tests prove the app logic works in isolation (see §5).

---

## 10. Configuration & secrets

The **12-factor app** principle says config that varies between environments (dev, staging,
prod) belongs in the **environment**, not in your code. That's exactly what `app/config.py`
does: it reads settings from environment variables (with sensible defaults) using
`pydantic-settings`.

The workflow:

```bash
cp .env.example .env           # create your local config
# edit .env to taste
```

`.env` is listed in both `.dockerignore` and `.gitignore` so it never gets baked into an
image or committed to version control. At runtime you provide values one of three ways:
`-e KEY=value` flags on `docker run`, the `env_file: .env` entry in compose, or your
orchestrator's secret management.

**Never** put real secrets (database passwords, API keys) in the Dockerfile, in the image,
or in git. Anyone who can pull the image can read baked-in secrets. For production, use your
platform's secret manager (Docker secrets, Kubernetes Secrets, AWS Secrets Manager, etc.)
and inject them as environment variables at run time.

### Storage backends: with or without a database

One setting, `DATABASE_URL`, chooses where items are stored — and the app runs identically
either way because the router programs against an `ItemRepository` interface, not a specific
database:

| `DATABASE_URL` | Backend | Where it lives |
|----------------|---------|----------------|
| _(unset)_ | In-memory dict | `app/repository.py` — no dependencies, resets on restart |
| `sqlite+aiosqlite:///./app.db` | SQLite (a local file) | `app/db.py` |
| `postgresql+asyncpg://app:pw@db:5432/app` | PostgreSQL | `app/db.py` |

The split is deliberate. **`app/repository.py`** holds the interface and the in-memory backend
and imports nothing third-party, so the default install and the default container stay light.
**`app/db.py`** holds the SQLAlchemy (async) backend and is imported *lazily* — only when a
`DATABASE_URL` is set — so the in-memory path never pays for SQLAlchemy. The same `app/db.py`
serves both SQLite and Postgres; only the URL scheme (and driver) differs.

`app/main.py`'s `lifespan` reads the setting on startup, builds the SQL backend if a URL is
present (creating tables and a connection pool), and disposes the engine on shutdown. The
SQLite/Postgres backends need the optional `db` dependencies:

```bash
uv sync --extra db                          # SQLAlchemy + aiosqlite + asyncpg
DATABASE_URL=sqlite+aiosqlite:///./app.db uv run uvicorn app.main:app --reload
```

The container image already bundles the `db` extra, so `docker compose up` runs against
Postgres with no extra steps. Table creation here is a convenience for a boilerplate; a real
project would manage schema changes with migrations (e.g. **Alembic**) instead.

---

## 11. Scheduling jobs inside Postgres with pg_cron

Plenty of work is recurring: purge expired rows nightly, refresh a summary table every
hour, roll up yesterday's numbers at midnight. You *could* run a separate cron daemon, or a
scheduler inside the app — but when the work is pure SQL, the tidiest home for it is the
database itself. **[pg_cron](https://github.com/citusdata/pg_cron)** is a Postgres extension
that does exactly that: it runs jobs on standard cron syntax from *inside* Postgres. The
schedule lives in a regular table (`cron.job`), so it's queryable and survives restarts, and
there's no extra container to babysit.

This project ships a tiny demo: a job that appends a timestamped row to a `cron_heartbeat`
table every minute — a visible "the scheduler is alive" signal you can watch tick.

### Why the database needs its own image

pg_cron can't simply be switched on. It has to be **loaded at server start** via
`shared_preload_libraries`, and it ships only as a Debian apt package
(`postgresql-16-cron`) — there's no Alpine build. So the `db` service is no longer the stock
`postgres:16-alpine`; it's built from **`db/Dockerfile`**, which starts from the Debian-based
`postgres:16` and installs the extension:

```dockerfile
FROM postgres:16
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-cron \
    && rm -rf /var/lib/apt/lists/*
COPY init.sql /docker-entrypoint-initdb.d/10-pg_cron.sql
```

### Two pieces that have to agree

**1. Preload the library (compose `command:`).** pg_cron's background worker also needs to
know which database to run jobs in — we point it at `app`:

```yaml
db:
  build: { context: ./db }
  command:
    - "postgres"
    - "-c"
    - "shared_preload_libraries=pg_cron"
    - "-c"
    - "cron.database_name=app"
```

These flags apply to the temporary server the entrypoint spins up for init scripts too,
which is why the `CREATE EXTENSION` in the next step doesn't fail.

**2. Bootstrap the extension and the job (`db/init.sql`).** Anything in
`/docker-entrypoint-initdb.d/` runs **once**, the first time the cluster is initialised,
against the `app` database:

```sql
CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE TABLE IF NOT EXISTS cron_heartbeat (
    id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ran_at timestamptz NOT NULL DEFAULT now()
);

-- every minute: append a row. cron.schedule upserts by name, so it's safe to re-run.
SELECT cron.schedule(
    'heartbeat-minute',
    '* * * * *',
    $$INSERT INTO cron_heartbeat (ran_at) VALUES (now())$$
);
```

`'* * * * *'` is ordinary 5-field cron (minute hour day month weekday) — here, every minute.
pg_cron also understands interval syntax like `'30 seconds'` for sub-minute jobs.

### See it work

```bash
docker compose up --build
# wait a minute or two, then:
docker compose exec db psql -U app -d app -c \
  "SELECT * FROM cron_heartbeat ORDER BY ran_at DESC LIMIT 5;"
```

You'll see a new row roughly every minute. Two more tables are worth knowing — the schedule
itself and the run history, which is where you debug a job that isn't firing:

```sql
SELECT jobid, jobname, schedule, command FROM cron.job;
SELECT jobid, status, return_message, start_time
  FROM cron.job_run_details ORDER BY start_time DESC LIMIT 5;
```

A healthy run shows `status = succeeded` and a `return_message` like `INSERT 0 1`.

### The one gotcha: init scripts run only once

`docker-entrypoint-initdb.d` scripts fire **only when the data directory is empty**. If
you'd already run `docker compose up` before adding pg_cron, the `pgdata` volume already
exists, so `init.sql` is skipped and you'll see no extension and no heartbeat. Wipe the
volume and start fresh:

```bash
docker compose down -v      # -v removes the named volume (deletes all DB data!)
docker compose up --build
```

For an existing database you don't want to wipe, you'd instead run the `CREATE EXTENSION` and
`cron.schedule(...)` statements by hand (e.g. via `docker compose exec db psql ...`) — the
extension still has to be preloaded via the `command:` flags either way.

### Changing jobs on a live server

`db/init.sql` only seeds a **fresh** database (§ above). Once the cluster exists, you manage
jobs as live SQL — the schedule is just rows in `cron.job`, so you change it with normal
queries and the change takes effect immediately, no restart. All of these run via
`docker compose exec db psql -U app -d app -c "..."` (or any psql session):

```sql
-- Add a job (or update one: cron.schedule UPSERTS by name, so re-running with the
-- same name changes its schedule/command in place rather than duplicating it).
SELECT cron.schedule(
    'nightly-cleanup',
    '30 2 * * *',                         -- 02:30 every day
    $$DELETE FROM cron_heartbeat WHERE ran_at < now() - interval '7 days'$$
);

-- Pause a job without deleting it, then re-enable it later.
SELECT cron.alter_job(job_id := (SELECT jobid FROM cron.job WHERE jobname='nightly-cleanup'),
                      active := false);
SELECT cron.alter_job(job_id := (SELECT jobid FROM cron.job WHERE jobname='nightly-cleanup'),
                      active := true);

-- Remove a job entirely (by name or by jobid).
SELECT cron.unschedule('nightly-cleanup');
```

**The mental model that bites people:** `init.sql` and the live `cron.job` table are two
separate sources of truth. Editing `init.sql` does **nothing** to a database that's already
been initialised, and changes you make with live SQL are **not** written back to `init.sql` —
they live only in the data volume, so a `docker compose down -v` throws them away. For
anything you want to be permanent and reproducible, **make the change in both places**: run it
live *and* update `init.sql` so the next fresh build comes up the same way. Treat `init.sql`
as the desired-state seed and keep it in sync, the same discipline you'd apply to a migration.

### Reusing this for a new project

Lifting the `db/` setup into another project comes down to keeping **three things in
agreement** — most "pg_cron isn't loading" problems are one of these being out of sync:

1. **Postgres major version** — `FROM postgres:16` and `postgresql-16-cron` in `db/Dockerfile`
   must use the *same* number. Bumping Postgres means bumping both.
2. **Database name** — `cron.database_name=app` in the compose `command:` must match
   `POSTGRES_DB` *and* the database you run `CREATE EXTENSION pg_cron` in. Rename the project's
   database and all three move together.
3. **Job names** — the names you pass to `cron.schedule(...)` are the upsert key. Use stable,
   descriptive names (`nightly-cleanup`, not `job1`) so re-running `init.sql` updates jobs
   rather than the schedule silently drifting.

Then swap the demo for your own: replace the `cron_heartbeat` table and the `heartbeat-minute`
job in `init.sql` with your real table(s) and job(s), keeping the statements **idempotent**
(`CREATE TABLE IF NOT EXISTS`, and `cron.schedule`'s upsert) so a re-bootstrap is always safe.
Everything else — the `command:` flags, the Dockerfile, the once-only-init behaviour — carries
over unchanged.

### When pg_cron is *not* the right tool

pg_cron runs **SQL**. If a scheduled task needs application logic — calling an external API,
sending email, anything Python — it doesn't belong here. Options then are an app-side
scheduler (e.g. APScheduler in the FastAPI `lifespan`), a dedicated worker (Celery + beat),
or having pg_cron call back into the app over HTTP via the `pg_net`/`http` extension. Reach
for those only when the job genuinely needs to leave the database.

---

## 12. Production concerns

The setup in this repo is production-shaped, but a few things deserve attention before you
put it under real traffic.

**Run multiple workers.** A single uvicorn process uses one CPU core. To use all cores, run
several worker processes. The simplest option is uvicorn's `--workers` flag; a common
production choice is to run uvicorn workers under **gunicorn**:

```dockerfile
# Alternative CMD for multi-core production
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", "-b", "0.0.0.0:8000"]
```

A rule of thumb is `(2 × cores) + 1` workers, but measure under realistic load rather than
guessing. Add gunicorn with `uv add gunicorn` if you use this.

**Put a reverse proxy in front.** In production, terminate TLS (HTTPS) and handle the public
internet with nginx, Caddy, Traefik, or a cloud load balancer in front of the container,
rather than exposing uvicorn directly. The proxy handles TLS, compression, rate limiting,
and buffering.

**Pin and scan.** Dependencies are pinned in `pyproject.toml` and fully locked in `uv.lock`
for reproducible builds; refresh them deliberately with `uv lock --upgrade`. Periodically
scan your image for known vulnerabilities with `docker scout cves` or Trivy, and rebuild on a
schedule to pick up base-image security patches.

**Resource limits.** Cap memory and CPU so one container can't starve its neighbors:
`docker run --memory=512m --cpus=1 ...`, or the `deploy.resources` section in compose.

**Logging.** The app logs to stdout/stderr (the container convention). Your platform
collects those streams — don't write logs to files inside the container, since the
container's filesystem is ephemeral.

**Tag images meaningfully.** `latest` is fine for local work but ambiguous in production.
Tag with a version or git commit (`fastapi-docker-server:1.4.2`,
`fastapi-docker-server:$(git rev-parse --short HEAD)`) so you always know exactly what's
deployed and can roll back.

---

## 13. Debugging & common errors

**`docker build` fails on `uv sync`** — Usually a stale lockfile (run `uv lock` and rebuild),
an unavailable version pinned in `pyproject.toml`, or no network access during build. Read the
error; rerun `uv sync --frozen` locally to reproduce it quickly.

**Container starts then immediately exits** — The main process crashed. Check `docker logs
<container>`. A frequent cause is an import error or a bad `CMD`. Remember the container
lives only as long as its PID 1 process; if uvicorn exits, the container stops.

**"Connection refused" when you open localhost:8000** — Two usual suspects: (1) you forgot
`-p 8000:8000`, so the port isn't published; or (2) the app is bound to `127.0.0.1` inside
the container instead of `0.0.0.0`. Our `CMD` already uses `0.0.0.0`; make sure you don't
override it.

**"Port is already allocated"** — Something else (often a previous container) is using host
port 8000. Find it with `docker ps`, stop it, or map a different host port: `-p 8001:8000`.

**Code changes don't show up** — Images are immutable snapshots. After editing code you must
rebuild (`docker build` / `docker compose up --build`). For a fast inner dev loop, bind-mount
your source into the container and run uvicorn with `--reload`, but keep that out of the
production image.

**Container marked `unhealthy`** — The health check command is failing. Test it by hand:
`docker exec <container> python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"`.

**Inspect a running container from the inside:**

```bash
docker exec -it <container> /bin/bash    # open a shell (or /bin/sh on minimal images)
docker exec -it <container> env          # see its environment variables
```

**Image is too big** — Check what's bloating it with `docker history <image>`. Make sure
`.dockerignore` excludes virtualenvs, caches, and `.git`, and confirm you're using the
multi-stage build.

---

## 14. Command cheat sheet

```bash
# Build
docker build -t fastapi-docker-server:latest .

# Run (foreground, auto-remove)
docker run --rm -p 8000:8000 fastapi-docker-server:latest

# Run (background) + logs
docker run -d --name srv -p 8000:8000 fastapi-docker-server:latest
docker logs -f srv

# Lifecycle
docker ps                 # running containers (+ health status)
docker ps -a              # include stopped
docker stop srv           # graceful stop
docker rm srv             # remove a stopped container
docker images             # list images
docker rmi <image>        # remove an image

# Shell into a container
docker exec -it srv /bin/bash

# Compose
docker compose up --build      # build + start
docker compose up -d           # start detached
docker compose logs -f         # follow logs
docker compose down            # stop + clean up

# CLI client (needs the server running — see §9)
uv run cli.py                  # drive the server; watch /banner art in its logs
uv run cli.py --url http://host:port

# pg_cron: inspect the scheduler inside Postgres (see §11)
docker compose exec db psql -U app -d app -c "SELECT * FROM cron_heartbeat ORDER BY ran_at DESC LIMIT 5;"
docker compose exec db psql -U app -d app -c "SELECT jobid, jobname, schedule FROM cron.job;"
docker compose down -v         # wipe the DB volume so db/init.sql re-runs (deletes data!)

# Housekeeping (reclaim disk)
docker system df               # show space used
docker system prune            # remove stopped containers, unused networks/images
```

---

## 15. Project file reference

| File | Purpose |
|------|---------|
| `app/main.py` | Creates the FastAPI app, CORS, `/`, `/health`, `/banner`, mounts routers, picks the storage backend in `lifespan`. |
| `app/config.py` | Settings from environment variables via `pydantic-settings` (incl. `DATABASE_URL`). |
| `app/schemas.py` | Pydantic request/response models (`ItemIn`, `ItemOut`), shared by router and repositories. |
| `app/repository.py` | `ItemRepository` interface + dependency-free in-memory backend. |
| `app/db.py` | SQLAlchemy async backend (SQLite/PostgreSQL); imported only when `DATABASE_URL` is set. |
| `app/routers/items.py` | Example CRUD endpoints; depends on `ItemRepository` via `Depends`. |
| `cli.py` | Tiny `httpx` client that drives a running server over HTTP (health → banner → items walkthrough). |
| `tests/test_main.py` | Fast tests with FastAPI's `TestClient` — in-memory plus a SQLite-backed persistence test. |
| `pyproject.toml` | Project metadata, pinned dependencies, and pytest config (uv). |
| `uv.lock` | Fully resolved, locked dependency tree for reproducible builds. |
| `.python-version` | Python version uv uses for the project (3.13). |
| `Dockerfile` | Multi-stage, non-root, health-checked image recipe (the API). |
| `db/Dockerfile` | Postgres 16 + the `pg_cron` extension, for database-side scheduling (§11). |
| `db/init.sql` | First-init bootstrap: creates `pg_cron`, the `cron_heartbeat` table, and the demo job. |
| `docker-compose.yml` | One-command run; wires the API to a pg_cron-enabled Postgres. |
| `.dockerignore` | Keeps caches, venvs, and secrets out of the build context. |
| `.env.example` | Template for local configuration (copy to `.env`). |

---

### Quick start (TL;DR)

```bash
# With Docker
docker compose up --build
# open http://localhost:8000/docs

# Without Docker (uses uv)
uv sync
uv run uvicorn app.main:app --reload
```
