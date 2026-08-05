"""Shared schema building blocks: UTC datetime serialization and pagination."""

from datetime import datetime
from math import ceil
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.core.timeutil import as_utc_aware


def _serialize_utc(value: datetime) -> str:
    """Render a naive-UTC DB value as '...Z' so clients never have to guess."""
    aware = as_utc_aware(value)
    return aware.isoformat().replace("+00:00", "Z")


# Use for every datetime we *return*. Input datetimes use pydantic's AwareDatetime,
# which rejects offset-less strings outright.
UtcDatetime = Annotated[
    datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")
]

ORM_CONFIG = ConfigDict(from_attributes=True)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope for every paginated list endpoint."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if page_size else 0,
        )


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    """Documents the single error envelope in the OpenAPI schema."""

    error: ErrorBody


class MessageResponse(BaseModel):
    message: str
