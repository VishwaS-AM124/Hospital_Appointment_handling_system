"""Pydantic request/response schemas.

``appointment`` is imported first on purpose: slot.py depends on
AppointmentSummaryOut, and appointment.py depends on SlotOut. Importing appointment
first makes that cycle resolve deterministically (see app/schemas/appointment.py).
"""

from app.schemas.appointment import (  # isort: skip
    AppointmentCancelRequest,
    AppointmentCompleteRequest,
    AppointmentCreate,
    AppointmentOut,
    AppointmentSummaryOut,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.common import (
    ErrorBody,
    ErrorResponse,
    MessageResponse,
    Page,
    UtcDatetime,
)
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate
from app.schemas.slot import (
    SlotBulkCreate,
    SlotBulkResult,
    SlotBulkSkipped,
    SlotCreate,
    SlotOut,
    SlotUpdate,
)
from app.schemas.user import DoctorPublicOut, PatientPublicOut, UserOut
from app.schemas.waitlist import (
    WaitlistEntryOut,
    WaitlistJoinRequest,
    WaitlistSummaryOut,
)

__all__ = [
    "AppointmentCancelRequest",
    "AppointmentCompleteRequest",
    "AppointmentCreate",
    "AppointmentOut",
    "AppointmentSummaryOut",
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "ErrorBody",
    "ErrorResponse",
    "MessageResponse",
    "Page",
    "UtcDatetime",
    "ServiceCreate",
    "ServiceOut",
    "ServiceUpdate",
    "SlotBulkCreate",
    "SlotBulkResult",
    "SlotBulkSkipped",
    "SlotCreate",
    "SlotOut",
    "SlotUpdate",
    "DoctorPublicOut",
    "PatientPublicOut",
    "UserOut",
    "NotificationOut",
    "UnreadCountOut",
    "WaitlistEntryOut",
    "WaitlistJoinRequest",
    "WaitlistSummaryOut",
]
