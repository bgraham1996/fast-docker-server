# syntax=docker/dockerfile:1
#
# Multi-stage build:
#   Stage 1 ("builder") installs dependencies into a virtualenv with uv.
#   Stage 2 ("runtime") copies only what's needed to run, producing a smaller,
#   cleaner final image with no build tooling (not even uv) left behind.

# ---- Stage 1: build dependencies ------------------------------------------
FROM python:3.13-slim AS builder

# Pull the standalone uv binary from its official image — no pip bootstrap needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Don't write .pyc files; flush stdout/stderr immediately (better logs).
# UV_COMPILE_BYTECODE precompiles deps for faster container startup; UV_LINK_MODE=copy
# avoids hardlink warnings across the cache mount; UV_PROJECT_ENVIRONMENT puts the
# venv at a fixed path we can copy wholesale into the runtime stage.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install dependencies in their own layer, keyed only on pyproject.toml + uv.lock.
# Docker caches this and only reinstalls when those files change — not on every code
# edit. --frozen uses the lockfile as-is (fails if stale); --no-dev skips test tooling;
# --no-install-project installs deps only, since the app source isn't here yet.
# --extra db bundles the SQLAlchemy/SQLite/Postgres drivers so the image can run
# with a database (set DATABASE_URL); without that env var it still runs in-memory.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra db

# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Create an unprivileged user. Running as root inside a container is a common
# security mistake; if the app is compromised, a non-root user limits damage.
RUN groupadd --system app && useradd --system --gid app --no-create-home appuser

WORKDIR /app

# Bring the prebuilt virtualenv over from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy application source. .dockerignore keeps junk (venvs, caches, .git) out.
COPY app/ ./app/

# Drop privileges for everything that follows.
USER appuser

EXPOSE 8000

# Container-level health check. Docker marks the container healthy/unhealthy
# based on this; orchestrators and `docker compose` can react to it.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"

# Start the ASGI server. The venv is on PATH, so uvicorn runs directly.
# Use --workers > 1 (or a process manager) for real load.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
