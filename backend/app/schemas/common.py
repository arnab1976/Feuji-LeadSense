from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = 0
    limit: int = 50
    offset: int = 0


class Message(BaseModel):
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
