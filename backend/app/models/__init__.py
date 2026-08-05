"""ORM models. Importing this package registers every table on Base.metadata."""

from app.db.base import Base
from app.models.appointment import (
    OCCUPYING_STATUSES,
    Appointment,
    AppointmentStatus,
    CancelledBy,
)
from app.models.notification import Notification, NotificationType
from app.models.service import Service
from app.models.slot import Slot, SlotStatus
from app.models.user import User, UserRole
from app.models.waitlist import (
    ACTIVE_WAITLIST_STATUSES,
    WaitlistEntry,
    WaitlistStatus,
)

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Service",
    "Slot",
    "SlotStatus",
    "Appointment",
    "AppointmentStatus",
    "CancelledBy",
    "OCCUPYING_STATUSES",
    "WaitlistEntry",
    "WaitlistStatus",
    "ACTIVE_WAITLIST_STATUSES",
    "Notification",
    "NotificationType",
]
