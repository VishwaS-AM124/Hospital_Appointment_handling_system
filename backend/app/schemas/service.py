"""Doctor service (offering) payloads."""

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORM_CONFIG, UtcDatetime


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    duration_minutes: int = Field(ge=5, le=480)
    price: float = Field(default=0.0, ge=0, le=99_999_999.99)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Service name must be at least 2 characters.")
        return cleaned


class ServiceUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    price: float | None = Field(default=None, ge=0, le=99_999_999.99)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Service name must be at least 2 characters.")
        return cleaned


class ServiceOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    doctor_id: int
    name: str
    description: str | None = None
    duration_minutes: int
    price: float
    is_active: bool
    created_at: UtcDatetime
