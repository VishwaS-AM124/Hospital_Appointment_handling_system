"""Appointment endpoints.

Thin by design — the transaction logic that prevents double-booking lives in
app/services/appointment_service.py, never here.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, DoctorUser, PatientUser
from app.models import AppointmentStatus
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCompleteRequest,
    AppointmentCreate,
    AppointmentOut,
)
from app.schemas.common import Page
from app.services import appointment_service

router = APIRouter()

PageParam = Query(default=1, ge=1)
PageSizeParam = Query(default=50, ge=1, le=200)
Scope = Literal["upcoming", "past", "all"]


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book an open slot (patient)",
    responses={
        409: {
            "description": (
                "SLOT_ALREADY_BOOKED — lost a booking race; SLOT_NOT_OPEN — already "
                "taken; PATIENT_TIME_CONFLICT — clashes with your own appointment"
            )
        }
    },
)
def book_appointment(
    payload: AppointmentCreate, db: DbSession, patient: PatientUser
) -> AppointmentOut:
    appointment = appointment_service.book_appointment(db, patient, payload)
    return AppointmentOut.model_validate(appointment)


# --- literal paths before /{appointment_id} -----------------------------------------


@router.get("/mine", response_model=Page[AppointmentOut], summary="My appointments")
def list_my_appointments(
    db: DbSession,
    patient: PatientUser,
    appointment_status: AppointmentStatus | None = Query(default=None, alias="status"),
    scope: Scope = "all",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = PageParam,
    page_size: int = PageSizeParam,
) -> Page[AppointmentOut]:
    appointments, total = appointment_service.list_patient_appointments(
        db,
        patient,
        status=appointment_status,
        scope=scope,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [AppointmentOut.model_validate(item) for item in appointments],
        total,
        page,
        page_size,
    )


@router.get(
    "/doctor",
    response_model=Page[AppointmentOut],
    summary="My schedule's appointments (doctor)",
)
def list_doctor_appointments(
    db: DbSession,
    doctor: DoctorUser,
    appointment_status: AppointmentStatus | None = Query(default=None, alias="status"),
    scope: Scope = "all",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = PageParam,
    page_size: int = PageSizeParam,
) -> Page[AppointmentOut]:
    appointments, total = appointment_service.list_doctor_appointments(
        db,
        doctor,
        status=appointment_status,
        scope=scope,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [AppointmentOut.model_validate(item) for item in appointments],
        total,
        page,
        page_size,
    )


@router.get("/{appointment_id}", response_model=AppointmentOut, summary="Appointment detail")
def get_appointment(
    appointment_id: int, db: DbSession, user: CurrentUser
) -> AppointmentOut:
    appointment = appointment_service.get_appointment(db, user, appointment_id)
    return AppointmentOut.model_validate(appointment)


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentOut,
    summary="Cancel an appointment — reopens the slot",
)
def cancel_appointment(
    appointment_id: int,
    payload: AppointmentCancelRequest,
    db: DbSession,
    user: CurrentUser,
) -> AppointmentOut:
    """Either the booking patient or the owning doctor may cancel."""
    appointment = appointment_service.cancel_appointment(
        db, user, appointment_id, payload
    )
    return AppointmentOut.model_validate(appointment)


@router.post(
    "/{appointment_id}/complete",
    response_model=AppointmentOut,
    summary="Mark an appointment completed (doctor)",
)
def complete_appointment(
    appointment_id: int,
    payload: AppointmentCompleteRequest,
    db: DbSession,
    doctor: DoctorUser,
) -> AppointmentOut:
    appointment = appointment_service.complete_appointment(
        db, doctor, appointment_id, payload
    )
    return AppointmentOut.model_validate(appointment)
