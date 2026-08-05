"""Notification payloads."""

from pydantic import BaseModel

from app.models import NotificationType
from app.schemas.common import ORM_CONFIG, UtcDatetime


class NotificationOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    type: NotificationType
    title: str
    body: str | None = None
    slot_id: int | None = None
    appointment_id: int | None = None
    read_at: UtcDatetime | None = None
    created_at: UtcDatetime


class UnreadCountOut(BaseModel):
    unread: int
