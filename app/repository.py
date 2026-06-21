"""Persistence abstraction for items.

The router depends on the `ItemRepository` interface, not on any specific
storage. That's what lets the same app run three ways, chosen at runtime by the
`DATABASE_URL` setting:

    (unset)                          -> InMemoryItemRepository  (this module)
    sqlite+aiosqlite:///./app.db     -> SqlItemRepository       (app.db)
    postgresql+asyncpg://user@host/db-> SqlItemRepository       (app.db)

The in-memory backend lives here and pulls in no third-party packages, so the
default install (and the default container) stays dependency-light. The SQL
backend lives in `app.db` and is imported lazily, only when a DATABASE_URL is set.
"""

from typing import Protocol

from app.schemas import ItemIn, ItemOut


class ItemRepository(Protocol):
    """Storage interface the router programs against.

    Methods are async because the SQL backend does real I/O; the in-memory
    backend just satisfies the same signatures.
    """

    async def list(self) -> list[ItemOut]: ...
    async def create(self, data: ItemIn) -> ItemOut: ...
    async def get(self, item_id: int) -> ItemOut | None: ...
    async def delete(self, item_id: int) -> bool: ...


class InMemoryItemRepository:
    """Process-local dict store. Resets on restart; for demos and tests.

    Operations don't `await`, so they run atomically under a single-process
    event loop — fine for this purpose. Swap in the SQL backend for real use.
    """

    def __init__(self) -> None:
        self._items: dict[int, ItemOut] = {}
        self._next_id = 1

    async def list(self) -> list[ItemOut]:
        return list(self._items.values())

    async def create(self, data: ItemIn) -> ItemOut:
        item = ItemOut(id=self._next_id, **data.model_dump())
        self._items[self._next_id] = item
        self._next_id += 1
        return item

    async def get(self, item_id: int) -> ItemOut | None:
        return self._items.get(item_id)

    async def delete(self, item_id: int) -> bool:
        return self._items.pop(item_id, None) is not None
