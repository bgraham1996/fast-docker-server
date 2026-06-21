"""Request/response models shared by the router and the repositories.

Kept in their own module so both `app.routers.items` and the repository layer
can import them without creating a circular import.
"""

from pydantic import BaseModel, ConfigDict, Field


class ItemIn(BaseModel):
    """Shape of an incoming create request (validated automatically)."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Widget"])
    price: float = Field(..., ge=0, examples=[9.99])
    in_stock: bool = True


class ItemOut(ItemIn):
    """Shape of an outgoing response — same as input plus a server-set id."""

    # from_attributes lets FastAPI build this straight from a SQLAlchemy row object.
    model_config = ConfigDict(from_attributes=True)

    id: int
