"""SQLAlchemy (async) backend for the item repository.

This module is imported **only** when a `DATABASE_URL` is configured, so the
in-memory path never pays for SQLAlchemy. The same code serves both SQLite and
PostgreSQL — the driver is chosen by the URL scheme:

    sqlite+aiosqlite:///./app.db
    postgresql+asyncpg://user:pass@host:5432/dbname

Requires the optional `db` dependencies (`uv sync --extra db`):
sqlalchemy[asyncio], aiosqlite, asyncpg.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.schemas import ItemIn, ItemOut


class Base(DeclarativeBase):
    pass


class ItemModel(Base):
    """ORM mapping for the `items` table."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    price: Mapped[float]
    in_stock: Mapped[bool] = mapped_column(default=True)


class SqlItemRepository:
    """ItemRepository backed by a SQL database via SQLAlchemy async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self) -> list[ItemOut]:
        async with self._session_factory() as session:
            rows = await session.scalars(select(ItemModel).order_by(ItemModel.id))
            return [ItemOut.model_validate(row) for row in rows]

    async def create(self, data: ItemIn) -> ItemOut:
        async with self._session_factory() as session:
            row = ItemModel(**data.model_dump())
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return ItemOut.model_validate(row)

    async def get(self, item_id: int) -> ItemOut | None:
        async with self._session_factory() as session:
            row = await session.get(ItemModel, item_id)
            return ItemOut.model_validate(row) if row is not None else None

    async def delete(self, item_id: int) -> bool:
        async with self._session_factory() as session:
            row = await session.get(ItemModel, item_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True


async def create_sql_repository(
    database_url: str,
) -> tuple[SqlItemRepository, AsyncEngine]:
    """Build the engine, create tables if needed, and return the repository.

    The engine is returned too so the caller (the app's lifespan) can dispose of
    it cleanly on shutdown. Table creation here is fine for a boilerplate; a real
    project would manage schema with migrations (e.g. Alembic) instead.
    """
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return SqlItemRepository(session_factory), engine
