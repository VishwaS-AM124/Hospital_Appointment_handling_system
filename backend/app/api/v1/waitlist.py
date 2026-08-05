"""Waiting-queue endpoints (patients only).

Joining is usually automatic — a booking attempt that loses to another patient enrols the
caller and reports their position in the 409 body. These endpoints cover the explicit
cases: queue up for a slot you can see is taken, check your place, or give it up.
"""

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession, PatientUser
from app.core.errors import app_error
from app.models import Slot, SlotStatus
from app.schemas.waitlist import WaitlistEntryOut
from app.services import waitlist_service

router = APIRouter()


@router.get(
    "/mine",
    response_model=list[WaitlistEntryOut],
    summary="Slots I am queued for",
)
def list_my_waitlist(
    db: DbSession, patient: PatientUser, active_only: bool = True
) -> list[WaitlistEntryOut]:
    entries = waitlist_service.list_patient_entries(db, patient, active_only=active_only)
    return [WaitlistEntryOut.model_validate(entry) for entry in entries]


@router.post(
    "/slots/{slot_id}",
    response_model=WaitlistEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Join the queue for a taken slot",
)
def join_waitlist(
    slot_id: int, db: DbSession, patient: PatientUser
) -> WaitlistEntryOut:
    try:
        # Same locking contract as every other queue mutation: slot row first.
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("SLOT_NOT_FOUND")

        from app.core.timeutil import utc_now_naive

        if slot.start_at <= utc_now_naive():
            raise app_error("SLOT_IN_PAST", "That appointment time has already passed.")
        if slot.status is SlotStatus.COMPLETED:
            raise app_error("SLOT_NOT_OPEN")
        # No point queueing for something you could simply book — unless it is being
        # held for somebody else's claim window.
        if slot.status is SlotStatus.OPEN:
            offer = waitlist_service.current_offer(db, slot.id)
            if offer is None or offer.patient_id == patient.id:
                raise app_error("SLOT_ALREADY_OPEN")

        entry, created = waitlist_service.join_queue(db, slot, patient)
        if not created:
            raise app_error("ALREADY_ON_WAITLIST")
        db.commit()
    except Exception:
        db.rollback()
        raise

    entry = waitlist_service.list_patient_entries(db, patient)
    match = next((item for item in entry if item.slot_id == slot_id), None)
    if match is None:
        raise app_error("WAITLIST_ENTRY_NOT_FOUND")
    return WaitlistEntryOut.model_validate(match)


@router.delete(
    "/slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave the queue for a slot",
)
def leave_waitlist(slot_id: int, db: DbSession, patient: PatientUser) -> None:
    try:
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("SLOT_NOT_FOUND")

        entry = waitlist_service.leave_queue(db, patient, slot_id)

        # If they were the one holding the claim window, pass it straight on rather than
        # leaving the slot reserved for nobody until the sweep notices.
        if entry.offered_at is not None:
            waitlist_service.offer_to_next(db, slot)

        db.commit()
    except Exception:
        db.rollback()
        raise
