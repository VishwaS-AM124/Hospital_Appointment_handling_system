"""Appointment payloads.

Import-order note: ``AppointmentSummaryOut`` is defined *before* this module imports
``SlotOut``, because schemas/slot.py imports AppointmentSummaryOut from here. That
mutual reference is resolved by defining the shared half first; app/schemas/__init__.py
imports this module before slot.py to keep the order deterministic.
"""

from pydantic import BaseModel, Field

from app.models import AppointmentStatus, CancelledBy
from app.schemas.common import ORM_CONFIG, UtcDatetime
from app.schemas.user import DoctorPublicOut, PatientPublicOut


class AppointmentCreate(BaseModel):
    slot_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class AppointmentCancelRequest(BaseModel):
    cancel_reason: str | None = Field(default=None, max_length=500)


class AppointmentCompleteRequest(BaseModel):
    doctor_notes: str | None = Field(default=None, max_length=1000)


class AppointmentSummaryOut(BaseModel):
    """Embedded inside SlotOut for the owning doctor's own schedule view."""

    model_config = ORM_CONFIG

    id: int
    status: AppointmentStatus
    reason: str | None = None
    created_at: UtcDatetime
    patient: PatientPublicOut | None = None


# Safe now that AppointmentSummaryOut exists — see the module docstring.
from app.schemas.slot import SlotOut  # noqa: E402


class AppointmentOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    slot_id: int
    patient_id: int
    doctor_id: int
    status: AppointmentStatus
    reason: str | None = None
    doctor_notes: str | None = None
    cancelled_by: CancelledBy | None = None
    cancel_reason: str | None = None
    created_at: UtcDatetime
    cancelled_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None

    slot: SlotOut | None = None
    doctor: DoctorPublicOut | None = None
    patient: PatientPublicOut | None = None
