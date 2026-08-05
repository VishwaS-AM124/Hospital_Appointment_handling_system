"""Slot payloads.

Input datetimes are ``AwareDatetime``: a string without a UTC offset is rejected rather
than guessed. See app/core/timeutil.py for why.
"""

from datetime import date, time

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.models import SlotStatus
from app.schemas.appointment import AppointmentSummaryOut
from app.schemas.common import ORM_CONFIG, UtcDatetime
from app.schemas.service import ServiceOut
from app.schemas.user import DoctorPublicOut

MIN_SLOT_MINUTES = 5
MAX_SLOT_MINUTES = 480


class SlotCreate(BaseModel):
    service_id: int | None = Field(default=None, gt=0)
    start_at: AwareDatetime
    end_at: AwareDatetime
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_interval(self) -> "SlotCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at.")
        minutes = (self.end_at - self.start_at).total_seconds() / 60
        if minutes < MIN_SLOT_MINUTES:
            raise ValueError(f"A slot must be at least {MIN_SLOT_MINUTES} minutes long.")
        if minutes > MAX_SLOT_MINUTES:
            raise ValueError(f"A slot cannot be longer than {MAX_SLOT_MINUTES} minutes.")
        return self


class SlotUpdate(BaseModel):
    """PATCH. start_at and end_at must be supplied together or not at all — moving one
    edge alone is ambiguous and easy to get wrong."""

    service_id: int | None = Field(default=None, gt=0)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=500)
    clear_service: bool = False

    @model_validator(mode="after")
    def _check_interval(self) -> "SlotUpdate":
        if (self.start_at is None) != (self.end_at is None):
            raise ValueError("Provide both start_at and end_at, or neither.")
        if self.start_at is not None and self.end_at is not None:
            if self.end_at <= self.start_at:
                raise ValueError("end_at must be after start_at.")
            minutes = (self.end_at - self.start_at).total_seconds() / 60
            if minutes < MIN_SLOT_MINUTES:
                raise ValueError(f"A slot must be at least {MIN_SLOT_MINUTES} minutes long.")
            if minutes > MAX_SLOT_MINUTES:
                raise ValueError(f"A slot cannot be longer than {MAX_SLOT_MINUTES} minutes.")
        return self


class SlotBulkCreate(BaseModel):
    """Generate a run of consecutive slots for one working day.

    The doctor thinks in local wall-clock time ("9am to 1pm"), so the client sends its
    UTC offset and the server converts. tz_offset_minutes follows the JavaScript
    convention inverted: the value to ADD to local time to get UTC is -offset, so we
    take the offset EAST of UTC as positive (IST = +330).
    """

    service_id: int | None = Field(default=None, gt=0)
    date: date
    start_time: time
    end_time: time
    slot_minutes: int = Field(ge=MIN_SLOT_MINUTES, le=MAX_SLOT_MINUTES)
    gap_minutes: int = Field(default=0, ge=0, le=240)
    tz_offset_minutes: int = Field(ge=-840, le=840)

    @model_validator(mode="after")
    def _check_window(self) -> "SlotBulkCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")
        return self


class SlotOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    doctor_id: int
    service_id: int | None = None
    start_at: UtcDatetime
    end_at: UtcDatetime
    status: SlotStatus
    notes: str | None = None
    duration_minutes: int

    doctor: DoctorPublicOut | None = None
    service: ServiceOut | None = None
    # Populated only for the owning doctor. Patients never see who booked a slot.
    appointment: AppointmentSummaryOut | None = None
    # How many patients are queued for this slot. Shown to the owning doctor so they can
    # see demand, and to a patient deciding whether joining the queue is worthwhile.
    waitlist_count: int = 0


class SlotBulkSkipped(BaseModel):
    start_at: UtcDatetime
    end_at: UtcDatetime
    reason: str


class SlotBulkResult(BaseModel):
    created: list[SlotOut]
    skipped: list[SlotBulkSkipped]
