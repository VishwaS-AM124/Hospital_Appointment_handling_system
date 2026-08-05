"""Slot / availability management.

Enforces:
  * rule 4 — a doctor cannot edit or delete a slot that is booked
  * rule 5 — a doctor only ever sees their own schedule
  * the half-open overlap rule, so a doctor cannot publish two slots that collide
"""

from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import app_error
from app.core.timeutil import to_utc_naive, utc_now_naive
from app.models import (
    Appointment,
    AppointmentStatus,
    Service,
    Slot,
    SlotStatus,
    User,
)
from app.schemas.slot import SlotBulkCreate, SlotCreate, SlotUpdate
from app.services import waitlist_service

# Statuses that mean "this slot is spoken for".
OCCUPIED_STATUSES = (SlotStatus.BOOKED, SlotStatus.COMPLETED)


# --------------------------------------------------------------------------- helpers


def _doctor_slot_query() -> Select:
    """Slots as the owning doctor sees them: with the occupying appointment attached."""
    return select(Slot).options(
        selectinload(Slot.service),
        selectinload(Slot.appointments).selectinload(Appointment.patient),
    )


def _open_slot_query() -> Select:
    """Slots as a browsing patient sees them: doctor + service, never appointments."""
    return select(Slot).options(
        selectinload(Slot.doctor),
        selectinload(Slot.service),
    )


def attach_occupying_appointment(slot: Slot) -> Slot:
    """Set the transient ``slot.appointment`` that SlotOut serializes.

    A slot accumulates one row per booking attempt over its life (cancelled ones stay
    for history), so we pick the single BOOKED/COMPLETED row — the one that actually
    holds the slot.
    """
    occupying = next(
        (
            appointment
            for appointment in slot.appointments
            if appointment.status
            in (AppointmentStatus.BOOKED, AppointmentStatus.COMPLETED)
        ),
        None,
    )
    slot.appointment = occupying
    return slot


def find_overlapping_slot(
    db: Session,
    doctor_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_slot_id: int | None = None,
) -> int | None:
    """Return the id of one of this doctor's slots that collides, else None.

    Half-open comparison: 09:00-09:30 and 09:30-10:00 are neighbours, not a collision.
    """
    stmt = (
        select(Slot.id)
        .where(
            Slot.doctor_id == doctor_id,
            Slot.start_at < end_at,
            Slot.end_at > start_at,
        )
        .limit(1)
    )
    if exclude_slot_id is not None:
        stmt = stmt.where(Slot.id != exclude_slot_id)
    return db.execute(stmt).scalar_one_or_none()


def _validate_service_owned(db: Session, doctor: User, service_id: int | None) -> None:
    if service_id is None:
        return
    owned = db.execute(
        select(Service.id).where(
            Service.id == service_id, Service.doctor_id == doctor.id
        )
    ).scalar_one_or_none()
    if owned is None:
        # Somebody else's service, or none at all — same answer either way.
        raise app_error("SERVICE_NOT_FOUND")


def _has_occupying_appointment(db: Session, slot_id: int) -> bool:
    found = db.execute(
        select(Appointment.id)
        .where(
            Appointment.slot_id == slot_id,
            Appointment.status.in_(
                (AppointmentStatus.BOOKED, AppointmentStatus.COMPLETED)
            ),
        )
        .limit(1)
    ).scalar_one_or_none()
    return found is not None


def _paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list, int]:
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars()
    )
    return rows, total


def attach_waitlist_counts(db: Session, slots: list[Slot]) -> list[Slot]:
    """Set the transient ``slot.waitlist_count`` SlotOut reads.

    One grouped query for the whole page rather than one per slot.
    """
    counts = waitlist_service.counts_for_slots(db, [slot.id for slot in slots])
    for slot in slots:
        slot.waitlist_count = counts.get(slot.id, 0)
    return slots


# ------------------------------------------------------------------------ read paths


def list_doctor_slots(
    db: Session,
    doctor: User,
    status: SlotStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Slot], int]:
    """The doctor's own schedule. Filtered by doctor_id, so rule 5 holds by construction."""
    stmt = _doctor_slot_query().where(Slot.doctor_id == doctor.id)
    if status is not None:
        stmt = stmt.where(Slot.status == status)
    if date_from is not None:
        stmt = stmt.where(Slot.start_at >= to_utc_naive(date_from))
    if date_to is not None:
        stmt = stmt.where(Slot.start_at < to_utc_naive(date_to))
    stmt = stmt.order_by(Slot.start_at.asc(), Slot.id.asc())

    slots, total = _paginate(db, stmt, page, page_size)
    for slot in slots:
        attach_occupying_appointment(slot)
    attach_waitlist_counts(db, slots)
    return slots, total


def list_open_slots(
    db: Session,
    doctor_id: int | None = None,
    service_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Slot], int]:
    """Bookable slots, for patients. Only OPEN and only in the future (rule 2)."""
    stmt = _open_slot_query().where(
        Slot.status == SlotStatus.OPEN,
        Slot.start_at > utc_now_naive(),
    )
    if doctor_id is not None:
        stmt = stmt.where(Slot.doctor_id == doctor_id)
    if service_id is not None:
        stmt = stmt.where(Slot.service_id == service_id)
    if date_from is not None:
        stmt = stmt.where(Slot.start_at >= to_utc_naive(date_from))
    if date_to is not None:
        stmt = stmt.where(Slot.start_at < to_utc_naive(date_to))
    stmt = stmt.order_by(Slot.start_at.asc(), Slot.id.asc())
    slots, total = _paginate(db, stmt, page, page_size)
    # Patients see how many people are already queued, so they can judge whether
    # joining a queue is worth it.
    attach_waitlist_counts(db, slots)
    return slots, total


def get_owned_slot(db: Session, doctor: User, slot_id: int) -> Slot:
    """A slot the doctor owns, with the occupying appointment attached."""
    slot = db.execute(
        _doctor_slot_query().where(Slot.id == slot_id, Slot.doctor_id == doctor.id)
    ).scalar_one_or_none()
    if slot is None:
        raise app_error("SLOT_NOT_FOUND")
    attach_occupying_appointment(slot)
    attach_waitlist_counts(db, [slot])
    return slot


def get_slot_for_patient(db: Session, patient: User, slot_id: int) -> Slot:
    """A patient may inspect a slot only if it is currently bookable, or if they
    already hold an appointment on it. Anything else is not theirs to see."""
    slot = db.execute(
        _open_slot_query().where(Slot.id == slot_id)
    ).scalar_one_or_none()
    if slot is None:
        raise app_error("SLOT_NOT_FOUND")

    attach_waitlist_counts(db, [slot])

    if slot.status is SlotStatus.OPEN and slot.start_at > utc_now_naive():
        return slot

    theirs = db.execute(
        select(Appointment.id)
        .where(Appointment.slot_id == slot.id, Appointment.patient_id == patient.id)
        .limit(1)
    ).scalar_one_or_none()
    if theirs is not None:
        return slot

    # Also visible if they are queued for it — otherwise "you are #2 in line for slot 7"
    # would point at a slot they cannot load.
    queued = waitlist_service.active_entry(db, slot.id, patient.id)
    if queued is None:
        raise app_error("SLOT_NOT_FOUND")
    return slot


# ----------------------------------------------------------------------- write paths


def create_slot(db: Session, doctor: User, payload: SlotCreate) -> Slot:
    start_at = to_utc_naive(payload.start_at)
    end_at = to_utc_naive(payload.end_at)

    if start_at <= utc_now_naive():
        raise app_error("SLOT_IN_PAST", "A slot must start in the future.")
    _validate_service_owned(db, doctor, payload.service_id)

    if find_overlapping_slot(db, doctor.id, start_at, end_at) is not None:
        raise app_error("SLOT_OVERLAP")

    slot = Slot(
        doctor_id=doctor.id,
        service_id=payload.service_id,
        start_at=start_at,
        end_at=end_at,
        status=SlotStatus.OPEN,
        notes=payload.notes,
    )
    db.add(slot)
    db.commit()
    return get_owned_slot(db, doctor, slot.id)


def bulk_create_slots(db: Session, doctor: User, payload: SlotBulkCreate) -> dict:
    """Generate a run of consecutive slots for one working day.

    Candidates that fall in the past or collide with an existing slot are *skipped and
    reported*, not treated as fatal — a doctor extending an existing day should not have
    the whole request rejected because two slots already exist.
    """
    _validate_service_owned(db, doctor, payload.service_id)

    offset = timedelta(minutes=payload.tz_offset_minutes)
    step = timedelta(minutes=payload.slot_minutes)
    gap = timedelta(minutes=payload.gap_minutes)
    now = utc_now_naive()

    cursor_local = datetime.combine(payload.date, payload.start_time)
    window_end_local = datetime.combine(payload.date, payload.end_time)

    created: list[Slot] = []
    skipped: list[dict] = []

    while cursor_local + step <= window_end_local:
        # Local wall clock -> UTC. tz_offset_minutes is positive east of UTC.
        start_at = cursor_local - offset
        end_at = start_at + step

        if start_at <= now:
            skipped.append(
                {"start_at": start_at, "end_at": end_at, "reason": "Starts in the past."}
            )
        elif find_overlapping_slot(db, doctor.id, start_at, end_at) is not None:
            skipped.append(
                {
                    "start_at": start_at,
                    "end_at": end_at,
                    "reason": "Overlaps a slot already in your schedule.",
                }
            )
        else:
            slot = Slot(
                doctor_id=doctor.id,
                service_id=payload.service_id,
                start_at=start_at,
                end_at=end_at,
                status=SlotStatus.OPEN,
            )
            db.add(slot)
            # Flush so the next iteration's overlap query sees this slot too.
            db.flush()
            created.append(slot)

        cursor_local = cursor_local + step + gap

    db.commit()

    fresh = [get_owned_slot(db, doctor, slot.id) for slot in created]
    return {"created": fresh, "skipped": skipped}


def update_slot(db: Session, doctor: User, slot_id: int, payload: SlotUpdate) -> Slot:
    """Rule 4: a slot that is booked cannot be edited.

    The row is locked FOR UPDATE first, so a patient cannot slip a booking in between
    our status check and our write.
    """
    try:
        slot = db.execute(
            select(Slot)
            .where(Slot.id == slot_id, Slot.doctor_id == doctor.id)
            .with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("SLOT_NOT_FOUND")

        if slot.status is not SlotStatus.OPEN or _has_occupying_appointment(db, slot.id):
            raise app_error("SLOT_HAS_APPOINTMENT")

        updates = payload.model_dump(exclude_unset=True)

        if payload.clear_service:
            slot.service_id = None
        elif "service_id" in updates and updates["service_id"] is not None:
            _validate_service_owned(db, doctor, updates["service_id"])
            slot.service_id = updates["service_id"]

        if payload.start_at is not None and payload.end_at is not None:
            start_at = to_utc_naive(payload.start_at)
            end_at = to_utc_naive(payload.end_at)
            if start_at <= utc_now_naive():
                raise app_error("SLOT_IN_PAST", "A slot must start in the future.")
            if (
                find_overlapping_slot(
                    db, doctor.id, start_at, end_at, exclude_slot_id=slot.id
                )
                is not None
            ):
                raise app_error("SLOT_OVERLAP")

            moved = start_at != slot.start_at or end_at != slot.end_at
            slot.start_at = start_at
            slot.end_at = end_at

            if moved:
                # People queued for a *specific* time; silently moving them to a
                # different one would be worse than releasing them and telling them.
                waitlist_service.withdraw_all(
                    db,
                    slot,
                    "The doctor moved that appointment time. Please check their "
                    "availability again.",
                    keep_slot_link=True,
                )

        if "notes" in updates:
            slot.notes = updates["notes"]

        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_owned_slot(db, doctor, slot_id)


def delete_slot(db: Session, doctor: User, slot_id: int) -> None:
    """Rule 4: a slot that is booked cannot be deleted.

    Cancelled appointments on the slot are removed with it. That is deliberate: the FK
    is ON DELETE CASCADE, and a cancelled booking on a withdrawn availability window
    has no independent meaning.
    """
    try:
        slot = db.execute(
            select(Slot)
            .where(Slot.id == slot_id, Slot.doctor_id == doctor.id)
            .with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("SLOT_NOT_FOUND")

        if slot.status is not SlotStatus.OPEN or _has_occupying_appointment(db, slot.id):
            raise app_error("SLOT_HAS_APPOINTMENT")

        # Tell anyone queued for it before the row (and its queue) cascades away.
        waitlist_service.withdraw_all(db, slot)

        db.delete(slot)
        db.commit()
    except Exception:
        db.rollback()
        raise
