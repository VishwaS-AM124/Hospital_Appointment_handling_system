"""Appointment booking, cancellation and completion.

This module carries the assessment's core logic. Rule 1 — "a slot can hold at most one
booked appointment at a time" — is defended three separate times, deliberately:

  Layer 1  SELECT ... FOR UPDATE on the slot row.
           Serializes concurrent bookings of the same slot. The second transaction
           blocks until the first commits or rolls back.

  Layer 2  Re-check slot.status *after* acquiring the lock.
           InnoDB locking reads always see the latest committed row rather than the
           transaction's snapshot, so the loser of the race observes status='BOOKED'
           and is rejected with SLOT_NOT_OPEN.

  Layer 3  UNIQUE index on appointments.occupies_slot_id (a generated column that
           equals slot_id while BOOKED/COMPLETED and NULL once CANCELLED).
           The database itself refuses a second live appointment. This is the layer
           that still holds if the application logic is ever wrong, if a row is
           inserted by another process, or if someone bypasses the service layer.

Layer 3 is not redundant defensive padding: FOR UPDATE takes no lock on a row that does
not exist yet, and application-level checks cannot span processes. Do not remove it.

Lock ordering is always slots -> appointments (see app/services/__init__.py). The slot
row lock also covers that slot's waiting queue — see app/services/waitlist_service.py.

Losing the race is not a dead end: the loser is placed in the slot's FIFO waiting queue
and notified, and if the slot is later released the patient at the head of that queue is
offered it exclusively.
"""

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, app_error
from app.core.timeutil import utc_now_naive
from app.models import (
    Appointment,
    AppointmentStatus,
    CancelledBy,
    NotificationType,
    Slot,
    SlotStatus,
    User,
    UserRole,
)
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCompleteRequest,
    AppointmentCreate,
)
from app.services import waitlist_service
from app.services.notification_service import notify

# The MySQL unique index behind rule 1. Matched against the driver error text to tell a
# lost booking race apart from any other integrity failure.
OCCUPIED_SLOT_CONSTRAINT = "uq_appointments_occupied_slot"

# Refusals that mean "somebody else has this slot" — the patient is queued for it.
QUEUEABLE_REFUSALS = {"SLOT_NOT_OPEN", "SLOT_ALREADY_BOOKED", "SLOT_RESERVED"}


# --------------------------------------------------------------------------- helpers


def _appointment_query() -> Select:
    return select(Appointment).options(
        selectinload(Appointment.slot).selectinload(Slot.service),
        selectinload(Appointment.slot).selectinload(Slot.doctor),
        selectinload(Appointment.doctor),
        selectinload(Appointment.patient),
    )


def _load(db: Session, appointment_id: int) -> Appointment:
    appointment = db.execute(
        _appointment_query().where(Appointment.id == appointment_id)
    ).scalar_one_or_none()
    if appointment is None:
        raise app_error("APPOINTMENT_NOT_FOUND")
    return appointment


def _assert_visible_to(appointment: Appointment, actor: User) -> None:
    """Rule 5. A patient sees only their own appointments; a doctor only their own
    schedule. Somebody else's appointment reads as 404, never 403 — a 403 would confirm
    the id exists."""
    if actor.role is UserRole.PATIENT:
        if appointment.patient_id != actor.id:
            raise app_error("APPOINTMENT_NOT_FOUND")
    elif appointment.doctor_id != actor.id:
        raise app_error("APPOINTMENT_NOT_FOUND")


def _paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list, int]:
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars()
    )
    return rows, total


def _when(slot: Slot) -> str:
    """Human-readable slot time for notification text.

    Labelled UTC on purpose: notification bodies are plain strings, so there is no way to
    re-render them in the reader's timezone later. Being explicit beats being ambiguous.
    """
    return (
        f"{slot.start_at.strftime('%a %d %b %Y, %H:%M')}"
        f"–{slot.end_at.strftime('%H:%M')} UTC"
    )


def _service_label(slot: Slot) -> str:
    return slot.service.name if slot.service else "General appointment"


# --------------------------------------------------------------- queue-aware plumbing


def _settle_slot_queue(db: Session, slot_id: int) -> None:
    """Bring a slot's waiting queue up to date, in its own committed transaction.

    Deliberately separate from the booking attempt below. If it ran inside that
    transaction, a booking that is then refused would roll back the queue advancement —
    and the SLOT_AVAILABLE notification with it, leaving the next patient in line waiting
    for a message that never arrives.
    """
    try:
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            db.rollback()
            return
        waitlist_service.settle_offers(db, slot)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _refuse_and_queue(
    db: Session, patient: User, slot_id: int, code: str, message: str | None = None
) -> AppError:
    """Build the 409 for a slot somebody else holds, adding the patient to its queue.

    Called only after the failed booking transaction has been rolled back. Enrolment
    happens in a fresh transaction so the refusal and the queue entry cannot interfere.
    """
    details = None
    try:
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()

        worth_queueing = (
            slot is not None
            and slot.start_at > utc_now_naive()
            and slot.status is not SlotStatus.COMPLETED
        )
        if worth_queueing:
            # Don't queue someone for a slot they already hold.
            already_theirs = db.execute(
                select(Appointment.id)
                .where(
                    Appointment.slot_id == slot.id,
                    Appointment.patient_id == patient.id,
                    Appointment.status.in_(
                        (AppointmentStatus.BOOKED, AppointmentStatus.COMPLETED)
                    ),
                )
                .limit(1)
            ).scalar_one_or_none()

            if already_theirs is None:
                entry, _created = waitlist_service.join_queue(db, slot, patient)
                db.commit()
                details = {
                    "waitlist_id": entry.id,
                    "slot_id": slot_id,
                    "position": waitlist_service.queue_position(db, entry),
                    "queue_length": waitlist_service.queue_length(db, slot_id),
                }
            else:
                db.rollback()
        else:
            db.rollback()
    except Exception:
        # Queueing is a courtesy. It must never mask or replace the real refusal.
        db.rollback()

    if details is not None:
        position = details["position"]
        suffix = (
            f" You are now number {position} on its waiting list and will be notified "
            "if it becomes free."
        )
        base = message or _default_message(code)
        return app_error(code, base + suffix, details)

    return app_error(code, message)


def _default_message(code: str) -> str:
    from app.core.errors import ERROR_MESSAGES

    return ERROR_MESSAGES.get(code, "Request failed.")


# ------------------------------------------------------------------------ read paths


def get_appointment(db: Session, actor: User, appointment_id: int) -> Appointment:
    appointment = _load(db, appointment_id)
    _assert_visible_to(appointment, actor)
    return appointment


def _scoped(stmt: Select, scope: str, now: datetime) -> Select:
    if scope == "upcoming":
        return stmt.where(Slot.start_at >= now)
    if scope == "past":
        return stmt.where(Slot.start_at < now)
    return stmt


def list_patient_appointments(
    db: Session,
    patient: User,
    status: AppointmentStatus | None = None,
    scope: str = "all",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Appointment], int]:
    stmt = (
        _appointment_query()
        .join(Slot, Appointment.slot_id == Slot.id)
        .where(Appointment.patient_id == patient.id)
    )
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    if date_from is not None:
        from app.core.timeutil import to_utc_naive

        stmt = stmt.where(Slot.start_at >= to_utc_naive(date_from))
    if date_to is not None:
        from app.core.timeutil import to_utc_naive

        stmt = stmt.where(Slot.start_at < to_utc_naive(date_to))
    stmt = _scoped(stmt, scope, utc_now_naive())

    order = Slot.start_at.asc() if scope == "upcoming" else Slot.start_at.desc()
    stmt = stmt.order_by(order, Appointment.id.desc())
    return _paginate(db, stmt, page, page_size)


def list_doctor_appointments(
    db: Session,
    doctor: User,
    status: AppointmentStatus | None = None,
    scope: str = "all",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Appointment], int]:
    stmt = (
        _appointment_query()
        .join(Slot, Appointment.slot_id == Slot.id)
        .where(Appointment.doctor_id == doctor.id)
    )
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    if date_from is not None:
        from app.core.timeutil import to_utc_naive

        stmt = stmt.where(Slot.start_at >= to_utc_naive(date_from))
    if date_to is not None:
        from app.core.timeutil import to_utc_naive

        stmt = stmt.where(Slot.start_at < to_utc_naive(date_to))
    stmt = _scoped(stmt, scope, utc_now_naive())

    order = Slot.start_at.asc() if scope == "upcoming" else Slot.start_at.desc()
    stmt = stmt.order_by(order, Appointment.id.desc())
    return _paginate(db, stmt, page, page_size)


# ----------------------------------------------------------------------- write paths


def book_appointment(
    db: Session, patient: User, payload: AppointmentCreate
) -> Appointment:
    """Book an open slot. Enforces rules 1 and 2, and honours the waiting queue.

    See the module docstring for the three-layer defence against double-booking.
    """
    slot_id = payload.slot_id

    # Advance the queue first, in its own transaction: a claim window may have lapsed,
    # in which case the offer must pass to the next patient whether or not *this*
    # booking succeeds.
    _settle_slot_queue(db, slot_id)

    try:
        # LAYER 1 — take the row lock before reading anything we intend to act on.
        # Deliberately not db.get(): the identity map could hand back a stale copy
        # that was loaded before another transaction booked this slot.
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("SLOT_NOT_FOUND")

        # LAYER 2 — rule 2: only an OPEN slot is bookable. Re-read under the lock.
        if slot.status is not SlotStatus.OPEN:
            raise app_error("SLOT_NOT_OPEN")

        now = utc_now_naive()
        if slot.start_at <= now:
            raise app_error("SLOT_IN_PAST", "That appointment time has already passed.")

        # An outstanding claim window belongs to exactly one patient (guaranteed by
        # uq_waitlist_one_offer_per_slot). While it is live, nobody else may book.
        offer = waitlist_service.current_offer(db, slot.id)
        if offer is not None and offer.patient_id != patient.id:
            if offer.offer_expires_at is None or offer.offer_expires_at > now:
                raise app_error("SLOT_RESERVED")

        # The patient's own calendar must stay consistent too: no two live
        # appointments overlapping in time, even across different doctors.
        clash = db.execute(
            select(Appointment.id)
            .join(Slot, Appointment.slot_id == Slot.id)
            .where(
                Appointment.patient_id == patient.id,
                Appointment.status == AppointmentStatus.BOOKED,
                Slot.start_at < slot.end_at,
                Slot.end_at > slot.start_at,
            )
            .limit(1)
        ).scalar_one_or_none()
        if clash is not None:
            raise app_error("PATIENT_TIME_CONFLICT")

        appointment = Appointment(
            slot_id=slot.id,
            patient_id=patient.id,
            # Copied from the slot so the doctor-side authorization filter and the
            # patient's history both survive later schedule edits.
            doctor_id=slot.doctor_id,
            status=AppointmentStatus.BOOKED,
            reason=payload.reason,
        )
        db.add(appointment)
        slot.status = SlotStatus.BOOKED

        # LAYER 3 — the UNIQUE index decides. Flushing here rather than at commit means
        # a lost race surfaces before we write notifications for a booking that failed.
        db.flush()

        # This patient's place in the queue (if any) is now spent.
        waitlist_service.mark_converted(db, slot.id, patient.id)

        # ►►► Notify the doctor that their slot was taken. ◄◄◄
        notify(
            db,
            user_id=slot.doctor_id,
            type=NotificationType.APPOINTMENT_BOOKED,
            title=f"{patient.full_name} booked an appointment",
            body=(
                f"{_when(slot)} · {_service_label(slot)}"
                + (f" — “{payload.reason}”" if payload.reason else "")
            ),
            slot_id=slot.id,
            appointment_id=appointment.id,
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()
        if OCCUPIED_SLOT_CONSTRAINT in str(exc.orig):
            # Lost a genuine race. Offer the queue instead of a dead end.
            raise _refuse_and_queue(db, patient, slot_id, "SLOT_ALREADY_BOOKED") from exc
        raise
    except AppError as exc:
        db.rollback()
        if exc.code in QUEUEABLE_REFUSALS:
            raise _refuse_and_queue(db, patient, slot_id, exc.code, exc.message) from exc
        raise
    except Exception:
        db.rollback()
        raise

    return _load(db, appointment.id)


def cancel_appointment(
    db: Session,
    actor: User,
    appointment_id: int,
    payload: AppointmentCancelRequest,
) -> Appointment:
    """Rule 3: cancelling reopens the slot, and the queue moves.

    Either party may cancel their own appointment. A patient may only do so before the
    start time; a doctor may cancel afterwards too, which is what a no-show is.
    """
    # Read slot_id with no lock so the locks below can be taken in the global order
    # (slots then appointments). slot_id is immutable once written, so this is safe.
    slot_id = db.execute(
        select(Appointment.slot_id).where(Appointment.id == appointment_id)
    ).scalar_one_or_none()
    if slot_id is None:
        raise app_error("APPOINTMENT_NOT_FOUND")

    try:
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("APPOINTMENT_NOT_FOUND")

        appointment = db.execute(
            select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        ).scalar_one_or_none()
        if appointment is None:
            raise app_error("APPOINTMENT_NOT_FOUND")

        _assert_visible_to(appointment, actor)

        if appointment.status is not AppointmentStatus.BOOKED:
            raise app_error("APPOINTMENT_NOT_ACTIVE")

        now = utc_now_naive()
        if actor.role is UserRole.PATIENT and slot.start_at <= now:
            raise app_error("CANCEL_WINDOW_CLOSED")

        by_patient = actor.role is UserRole.PATIENT
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancelled_by = (
            CancelledBy.PATIENT if by_patient else CancelledBy.DOCTOR
        )
        appointment.cancel_reason = payload.cancel_reason

        # ►►► RULE 3 ◄◄◄ The slot becomes bookable again. Same transaction, so the
        # generated column drops to NULL and the slot reopens atomically — there is no
        # instant where the slot is OPEN but still looks occupied, or vice versa.
        slot.status = SlotStatus.OPEN
        db.flush()

        # Tell the other party their appointment is off.
        reason_suffix = (
            f" Reason: {payload.cancel_reason}" if payload.cancel_reason else ""
        )
        if by_patient:
            notify(
                db,
                user_id=appointment.doctor_id,
                type=NotificationType.APPOINTMENT_CANCELLED,
                title=f"{actor.full_name} cancelled their appointment",
                body=f"{_when(slot)} · the slot is open again.{reason_suffix}",
                slot_id=slot.id,
                appointment_id=appointment.id,
            )
        else:
            notify(
                db,
                user_id=appointment.patient_id,
                type=NotificationType.APPOINTMENT_CANCELLED,
                title="Your appointment was cancelled by the clinic",
                body=f"{_when(slot)} · {_service_label(slot)}.{reason_suffix}",
                slot_id=slot.id,
                appointment_id=appointment.id,
            )

        # ►►► The slot just freed up: offer it to whoever is next in line. ◄◄◄
        # Same transaction as the release, so the offer and the reopened slot commit
        # together — nobody can be told about a slot that did not actually free up.
        waitlist_service.settle_offers(db, slot)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load(db, appointment_id)


def complete_appointment(
    db: Session,
    doctor: User,
    appointment_id: int,
    payload: AppointmentCompleteRequest,
) -> Appointment:
    """Mark an appointment as attended. Doctor-only, and only once the visit has begun.

    The slot moves to COMPLETED rather than back to OPEN: the consultation happened, so
    that window is spent and must not be re-sold.
    """
    slot_id = db.execute(
        select(Appointment.slot_id).where(Appointment.id == appointment_id)
    ).scalar_one_or_none()
    if slot_id is None:
        raise app_error("APPOINTMENT_NOT_FOUND")

    try:
        slot = db.execute(
            select(Slot).where(Slot.id == slot_id).with_for_update()
        ).scalar_one_or_none()
        if slot is None:
            raise app_error("APPOINTMENT_NOT_FOUND")

        appointment = db.execute(
            select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        ).scalar_one_or_none()
        if appointment is None:
            raise app_error("APPOINTMENT_NOT_FOUND")

        # Doctor-side ownership only: this endpoint is already role-gated to doctors.
        if appointment.doctor_id != doctor.id:
            raise app_error("APPOINTMENT_NOT_FOUND")

        if appointment.status is not AppointmentStatus.BOOKED:
            raise app_error("APPOINTMENT_NOT_ACTIVE")

        now = utc_now_naive()
        if slot.start_at > now:
            raise app_error("COMPLETE_TOO_EARLY")

        appointment.status = AppointmentStatus.COMPLETED
        appointment.completed_at = now
        if payload.doctor_notes is not None:
            appointment.doctor_notes = payload.doctor_notes

        slot.status = SlotStatus.COMPLETED
        db.flush()

        notify(
            db,
            user_id=appointment.patient_id,
            type=NotificationType.APPOINTMENT_COMPLETED,
            title="Your appointment has been marked completed",
            body=(
                f"{_when(slot)} with {doctor.full_name}."
                + (f" Notes: {payload.doctor_notes}" if payload.doctor_notes else "")
            ),
            slot_id=slot.id,
            appointment_id=appointment.id,
        )

        # The slot can never be booked again, so nobody should keep waiting for it.
        waitlist_service.expire_all(db, slot)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load(db, appointment_id)
