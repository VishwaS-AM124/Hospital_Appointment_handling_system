"""Slot / availability endpoints.

Two disjoint read paths, which is how "a doctor cannot see other doctors' schedules"
(rule 5) is enforced structurally rather than by a filter someone might forget:

  GET /slots/mine  — DOCTOR only, always filtered to the caller's own id
  GET /slots/open  — PATIENT only, only OPEN and future slots

There is deliberately no endpoint that returns an arbitrary doctor's full calendar.
"""

from datetime import datetime

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, DoctorUser, PatientUser
from app.models import SlotStatus, UserRole
from app.schemas.common import Page
from app.schemas.slot import (
    SlotBulkCreate,
    SlotBulkResult,
    SlotCreate,
    SlotOut,
    SlotUpdate,
)
from app.services import slot_service

router = APIRouter()

PageParam = Query(default=1, ge=1)
PageSizeParam = Query(default=50, ge=1, le=200)


# --- literal paths first: /mine, /open, /bulk must not be eaten by /{slot_id} -------


@router.get("/mine", response_model=Page[SlotOut], summary="My schedule (doctor)")
def list_my_slots(
    db: DbSession,
    doctor: DoctorUser,
    slot_status: SlotStatus | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = PageParam,
    page_size: int = PageSizeParam,
) -> Page[SlotOut]:
    slots, total = slot_service.list_doctor_slots(
        db,
        doctor,
        status=slot_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [SlotOut.model_validate(slot) for slot in slots], total, page, page_size
    )


@router.get(
    "/open",
    response_model=Page[SlotOut],
    summary="Browse bookable slots (patient)",
)
def list_open_slots(
    db: DbSession,
    patient: PatientUser,
    doctor_id: int | None = Query(default=None, gt=0),
    service_id: int | None = Query(default=None, gt=0),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = PageParam,
    page_size: int = PageSizeParam,
) -> Page[SlotOut]:
    slots, total = slot_service.list_open_slots(
        db,
        doctor_id=doctor_id,
        service_id=service_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [SlotOut.model_validate(slot) for slot in slots], total, page, page_size
    )


@router.post(
    "",
    response_model=SlotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a slot",
)
def create_slot(payload: SlotCreate, db: DbSession, doctor: DoctorUser) -> SlotOut:
    slot = slot_service.create_slot(db, doctor, payload)
    return SlotOut.model_validate(slot)


@router.post(
    "/bulk",
    response_model=SlotBulkResult,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a day of slots",
)
def bulk_create_slots(
    payload: SlotBulkCreate, db: DbSession, doctor: DoctorUser
) -> SlotBulkResult:
    result = slot_service.bulk_create_slots(db, doctor, payload)
    return SlotBulkResult(
        created=[SlotOut.model_validate(slot) for slot in result["created"]],
        skipped=result["skipped"],
    )


# --- parameterised paths ------------------------------------------------------------


@router.get("/{slot_id}", response_model=SlotOut, summary="Slot detail")
def get_slot(slot_id: int, db: DbSession, user: CurrentUser) -> SlotOut:
    """Doctors get their own slots in full; patients only see a slot that is bookable
    or that they already hold an appointment on."""
    if user.role is UserRole.DOCTOR:
        slot = slot_service.get_owned_slot(db, user, slot_id)
    else:
        slot = slot_service.get_slot_for_patient(db, user, slot_id)
    return SlotOut.model_validate(slot)


@router.patch(
    "/{slot_id}",
    response_model=SlotOut,
    summary="Edit a slot (only while it is still open)",
)
def update_slot(
    slot_id: int, payload: SlotUpdate, db: DbSession, doctor: DoctorUser
) -> SlotOut:
    slot = slot_service.update_slot(db, doctor, slot_id, payload)
    return SlotOut.model_validate(slot)


@router.delete(
    "/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a slot (only while it is still open)",
)
def delete_slot(slot_id: int, db: DbSession, doctor: DoctorUser) -> None:
    slot_service.delete_slot(db, doctor, slot_id)
