"""The slot waiting queue.

When a slot is taken, further would-be bookers join a FIFO queue. When the slot is
released, the patient at the head is *offered* it — an exclusive claim window during
which nobody else may book that slot. If they let it lapse, the offer moves down the
queue.

    WAITING ──(slot released, you are first)──► OFFERED ──(you book)──► CONVERTED
        │                                          │
        │                                          └──(window lapses)──► EXPIRED
        │                                                                    │
        └──(you leave / doctor withdraws the slot)──► WITHDRAWN               │
                                                                             ▼
                                                        offer passes to the next WAITING

LOCKING CONTRACT — read this before editing.

Every function below that *mutates* the queue assumes the caller already holds the
``slots`` row lock (``SELECT … FOR UPDATE``) for the slot in question. That single lock
is the serialization point for everything about a slot: its status, its appointments and
its queue. Because no code path touches a slot's queue without first locking the slot,
the queue needs no lock of its own and no new entry appears in the global lock order
(still ``slots -> appointments``). Breaking that convention reintroduces the races this
module exists to prevent.
"""

from datetime import timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import app_error
from app.core.timeutil import utc_now_naive
from app.models import (
    ACTIVE_WAITLIST_STATUSES,
    NotificationType,
    Slot,
    SlotStatus,
    User,
    WaitlistEntry,
    WaitlistStatus,
)
from app.services.notification_service import notify

ACTIVE_STATUSES = (WaitlistStatus.WAITING, WaitlistStatus.OFFERED)


# ------------------------------------------------------------------------------ reads


def _entry_query() -> Select:
    return select(WaitlistEntry).options(
        selectinload(WaitlistEntry.slot).selectinload(Slot.service),
        selectinload(WaitlistEntry.slot).selectinload(Slot.doctor),
        selectinload(WaitlistEntry.patient),
    )


def active_entry(db: Session, slot_id: int, patient_id: int) -> WaitlistEntry | None:
    return db.execute(
        select(WaitlistEntry).where(
            WaitlistEntry.slot_id == slot_id,
            WaitlistEntry.patient_id == patient_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()


def queue_length(db: Session, slot_id: int) -> int:
    return db.execute(
        select(func.count())
        .select_from(WaitlistEntry)
        .where(
            WaitlistEntry.slot_id == slot_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one()


def queue_position(db: Session, entry: WaitlistEntry) -> int | None:
    """1-based place in the queue, or None if the entry is no longer active.

    Ordered by (created_at, id). DATETIME has one-second granularity, so two patients
    who joined in the same second would tie — the auto-increment id breaks it
    deterministically, which keeps positions stable instead of flapping between reads.
    """
    if entry.status not in ACTIVE_STATUSES:
        return None
    ahead = db.execute(
        select(func.count())
        .select_from(WaitlistEntry)
        .where(
            WaitlistEntry.slot_id == entry.slot_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
            or_(
                WaitlistEntry.created_at < entry.created_at,
                and_(
                    WaitlistEntry.created_at == entry.created_at,
                    WaitlistEntry.id < entry.id,
                ),
            ),
        )
    ).scalar_one()
    return ahead + 1


def current_offer(db: Session, slot_id: int) -> WaitlistEntry | None:
    """The entry holding the claim window, expired or not.

    At most one can exist — enforced by uq_waitlist_one_offer_per_slot.
    """
    return db.execute(
        select(WaitlistEntry).where(
            WaitlistEntry.slot_id == slot_id,
            WaitlistEntry.status == WaitlistStatus.OFFERED,
        )
    ).scalar_one_or_none()


def is_claimable_by(entry: WaitlistEntry | None, patient_id: int) -> bool:
    """True when `entry` is a live offer belonging to this patient."""
    if entry is None or entry.status is not WaitlistStatus.OFFERED:
        return False
    if entry.patient_id != patient_id:
        return False
    return entry.offer_expires_at is None or entry.offer_expires_at > utc_now_naive()


def decorate(db: Session, entry: WaitlistEntry) -> WaitlistEntry:
    """Attach the transient `position` / `can_claim_now` fields WaitlistEntryOut reads."""
    entry.position = queue_position(db, entry)
    entry.can_claim_now = is_claimable_by(entry, entry.patient_id)
    return entry


def list_patient_entries(
    db: Session, patient: User, active_only: bool = True
) -> list[WaitlistEntry]:
    stmt = _entry_query().where(WaitlistEntry.patient_id == patient.id)
    if active_only:
        stmt = stmt.where(WaitlistEntry.status.in_(ACTIVE_STATUSES))
    stmt = stmt.order_by(WaitlistEntry.created_at.desc(), WaitlistEntry.id.desc())
    entries = list(db.execute(stmt).scalars())

    # The embedded SlotOut carries waitlist_count, which defaults to 0. Fill it in, or
    # the patient sees "0 waiting" on a slot they are demonstrably queued for.
    slots = [entry.slot for entry in entries if entry.slot is not None]
    if slots:
        counts = counts_for_slots(db, [slot.id for slot in slots])
        for slot in slots:
            slot.waitlist_count = counts.get(slot.id, 0)

    for entry in entries:
        decorate(db, entry)
    return entries


def counts_for_slots(db: Session, slot_ids: list[int]) -> dict[int, int]:
    """Queue length per slot, in one query — avoids N+1 on list endpoints."""
    if not slot_ids:
        return {}
    rows = db.execute(
        select(WaitlistEntry.slot_id, func.count())
        .where(
            WaitlistEntry.slot_id.in_(slot_ids),
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
        .group_by(WaitlistEntry.slot_id)
    ).all()
    return {slot_id: count for slot_id, count in rows}


# ----------------------------------------------------------------------------- writes
# All of the following require the caller to hold the slot row lock.


def join_queue(
    db: Session, slot: Slot, patient: User
) -> tuple[WaitlistEntry, bool]:
    """Add `patient` to the back of `slot`'s queue.

    Returns (entry, created). Idempotent: an existing active entry is returned with
    created=False rather than duplicated, which is what makes it safe to call from the
    failure path of a booking attempt.
    """
    existing = active_entry(db, slot.id, patient.id)
    if existing is not None:
        return existing, False

    entry = WaitlistEntry(
        slot_id=slot.id, patient_id=patient.id, status=WaitlistStatus.WAITING
    )
    db.add(entry)
    # Flush so the unique index is checked now and queue_position sees this row.
    db.flush()

    position = queue_position(db, entry)
    notify(
        db,
        user_id=patient.id,
        type=NotificationType.WAITLIST_JOINED,
        title=f"You are #{position} in line for a slot",
        body=(
            "That appointment time is taken. If it frees up we will offer it to you in "
            f"queue order — you are currently number {position}."
        ),
        slot_id=slot.id,
    )
    return entry, True


def leave_queue(db: Session, patient: User, slot_id: int) -> WaitlistEntry:
    entry = active_entry(db, slot_id, patient.id)
    if entry is None:
        raise app_error("WAITLIST_ENTRY_NOT_FOUND")
    entry.status = WaitlistStatus.WITHDRAWN
    db.flush()
    return entry


def offer_to_next(db: Session, slot: Slot) -> WaitlistEntry | None:
    """Promote the head of the queue to an exclusive claim window, and notify them.

    ►►► This is the notification the task calls for: when a slot is released, the patient
    who was next in the queue is told, and for the length of the claim window only they
    can take it. ◄◄◄
    """
    now = utc_now_naive()
    # Never offer a slot that has already started, or one that is not bookable.
    if slot.start_at <= now or slot.status is not SlotStatus.OPEN:
        return None

    head = db.execute(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.slot_id == slot.id,
            WaitlistEntry.status == WaitlistStatus.WAITING,
        )
        .order_by(WaitlistEntry.created_at.asc(), WaitlistEntry.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if head is None:
        return None

    # The window never runs past the appointment itself — an offer that expires after
    # the slot has started would be useless.
    window_end = now + timedelta(minutes=settings.waitlist_claim_window_minutes)
    head.status = WaitlistStatus.OFFERED
    head.offered_at = now
    head.offer_expires_at = min(window_end, slot.start_at)

    minutes = max(1, int((head.offer_expires_at - now).total_seconds() // 60))
    notify(
        db,
        user_id=head.patient_id,
        type=NotificationType.SLOT_AVAILABLE,
        title="A slot you were waiting for is now free",
        body=(
            "You were next in line and the appointment has been released. It is held "
            f"for you for the next {minutes} minute(s) — book it now to keep it."
        ),
        slot_id=slot.id,
    )
    db.flush()
    return head


def settle_offers(db: Session, slot: Slot) -> WaitlistEntry | None:
    """Bring a slot's queue up to date and return the live offer, if any.

    Expires a lapsed claim window, notifies that patient they missed it, and passes the
    offer to the next person. Called on every booking attempt and by the background
    sweep, so the queue advances even with no scheduler running.
    """
    now = utc_now_naive()
    offer = current_offer(db, slot.id)

    if offer is not None:
        still_valid = offer.offer_expires_at is None or offer.offer_expires_at > now
        if still_valid:
            return offer

        offer.status = WaitlistStatus.EXPIRED
        notify(
            db,
            user_id=offer.patient_id,
            type=NotificationType.WAITLIST_MISSED,
            title="Your held slot has been released",
            body=(
                "The time we were holding for you has passed to the next patient in "
                "line. You can still join the queue again if you would like."
            ),
            slot_id=slot.id,
        )
        db.flush()

    return offer_to_next(db, slot)


def mark_converted(db: Session, slot_id: int, patient_id: int) -> None:
    """The patient booked the slot, so their place in the queue is spent."""
    entry = active_entry(db, slot_id, patient_id)
    if entry is not None:
        entry.status = WaitlistStatus.CONVERTED
        db.flush()


def withdraw_all(
    db: Session,
    slot: Slot,
    reason: str | None = None,
    *,
    keep_slot_link: bool = False,
) -> int:
    """The slot is going away or changing — tell everyone still queued for it.

    ``keep_slot_link=False`` (the default) is for deletion: the slot row is about to
    disappear, so the notification must not reference it. Pass True when the slot
    survives, e.g. it was rescheduled.
    """
    entries = list(
        db.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.slot_id == slot.id,
                WaitlistEntry.status.in_(ACTIVE_STATUSES),
            )
        ).scalars()
    )
    for entry in entries:
        entry.status = WaitlistStatus.WITHDRAWN
        notify(
            db,
            user_id=entry.patient_id,
            type=NotificationType.SLOT_WITHDRAWN,
            title="A slot you were waiting for is no longer available",
            body=reason
            or "The doctor has removed that appointment time from their schedule.",
            slot_id=slot.id if keep_slot_link else None,
        )
    if entries:
        db.flush()
    return len(entries)


def expire_all(db: Session, slot: Slot) -> int:
    """Quietly close out a queue that can no longer be fulfilled (the slot's time has
    passed, or it was completed). No notification: telling someone about a slot that is
    already in the past is noise."""
    entries = list(
        db.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.slot_id == slot.id,
                WaitlistEntry.status.in_(ACTIVE_STATUSES),
            )
        ).scalars()
    )
    for entry in entries:
        entry.status = WaitlistStatus.EXPIRED
    if entries:
        db.flush()
    return len(entries)


# --------------------------------------------------------------------- background sweep


def sweep_expired_offers(db: Session) -> int:
    """Advance every queue whose claim window has lapsed, and close out queues for slots
    whose time has passed. Returns the number of slots touched.

    Without this, a lapsed offer would only be noticed the next time somebody tried to
    book that slot — so the next patient in line could wait indefinitely for a
    notification that never came.
    """
    now = utc_now_naive()

    lapsed = db.execute(
        select(WaitlistEntry.slot_id).where(
            WaitlistEntry.status == WaitlistStatus.OFFERED,
            WaitlistEntry.offer_expires_at.is_not(None),
            WaitlistEntry.offer_expires_at <= now,
        )
    ).scalars().all()

    past = db.execute(
        select(WaitlistEntry.slot_id)
        .join(Slot, WaitlistEntry.slot_id == Slot.id)
        .where(
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
            Slot.start_at <= now,
        )
    ).scalars().all()

    touched = 0
    for slot_id in sorted(set(lapsed) | set(past)):
        try:
            # Same locking contract as everywhere else: take the slot lock first.
            slot = db.execute(
                select(Slot).where(Slot.id == slot_id).with_for_update()
            ).scalar_one_or_none()
            if slot is None:
                db.rollback()
                continue
            if slot.start_at <= now:
                expire_all(db, slot)
            else:
                settle_offers(db, slot)
            db.commit()
            touched += 1
        except Exception:
            db.rollback()
            raise
    return touched
