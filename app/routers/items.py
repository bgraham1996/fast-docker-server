"""Example CRUD router.

Demonstrates the typical FastAPI patterns you'll reuse: Pydantic request/
response models, path parameters, status codes, error handling, and dependency
injection. The actual storage is supplied by an `ItemRepository` (in-memory by
default, SQLite or PostgreSQL when `DATABASE_URL` is set) — this router doesn't
care which, it just calls the interface.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.repository import ItemRepository
from app.schemas import ItemIn, ItemOut

# prefix => every route here starts with /items
# tags   => groups these endpoints together in the /docs UI
router = APIRouter(prefix="/items", tags=["items"])


def get_repository(request: Request) -> ItemRepository:
    """Hand the request the repository the app wired up at startup.

    Stored on `app.state` in main.py's lifespan, so a test can swap in a
    different backend without touching this router.
    """
    return request.app.state.item_repository


@router.get("", response_model=list[ItemOut])
async def list_items(repo: ItemRepository = Depends(get_repository)):
    return await repo.list()


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemIn, repo: ItemRepository = Depends(get_repository)):
    return await repo.create(payload)


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, repo: ItemRepository = Depends(get_repository)):
    item = await repo.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, repo: ItemRepository = Depends(get_repository)):
    if not await repo.delete(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
