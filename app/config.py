"""Application configuration.

Settings are read from environment variables (and an optional .env file),
so the same image can run in dev, staging, and prod without code changes.
This is the "config in the environment" principle from the 12-factor app.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App metadata
    app_name: str = "FastAPI Docker Server"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # Network. 0.0.0.0 means "listen on all interfaces" — required inside a
    # container so traffic from outside the container can reach the app.
    host: str = "0.0.0.0"
    port: int = 8000

    # Comma-separated list of allowed CORS origins, e.g. "https://app.example.com"
    cors_origins: str = "*"

    # Storage backend selector. Unset/empty => in-memory store (no DB needed).
    # Set a SQLAlchemy async URL to use a real database instead, e.g.
    #   sqlite+aiosqlite:///./app.db
    #   postgresql+asyncpg://user:pass@db:5432/app
    # The SQL backend requires the optional `db` dependencies (uv sync --extra db).
    database_url: str | None = None

    # Pydantic-settings configuration: read a .env file if present, ignore
    # unknown env vars, and treat names case-insensitively (APP_NAME == app_name).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    lru_cache means the environment is parsed once per process, and the same
    object is reused everywhere (including as a FastAPI dependency).
    """
    return Settings()
