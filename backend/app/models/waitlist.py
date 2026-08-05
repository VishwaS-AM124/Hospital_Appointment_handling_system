"""Slot waiting queue.

When a patient loses a booking race — or simply arrives after the slot was taken — they
are placed in a FIFO queue for that slot. When the slot is released (either party
cancels), the patient at the head of the queue is *offered* it: a time-limited exclusive
claim window during which nobody else may book it.

Two database-level guarantees, both built the same way as the rule-1 index on
appointments (a generated column plus a UNIQUE index that ignores NULLs):

  uq_waitlist_active_pair       one active queue entry per (slot, patient)
  uq_waitlist_one_offer_per_slot  at most ONE outstanding offer per slot, ever

The second is the important one: it makes "two patients were both told the slot is
theirs" impossible at the storage-engine level, not merely unlikely.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import _enum_column


class WaitlistStatus(str, enum.Enum):
    WAITING = "WAITING"      # in the queue
    OFFERED = "OFFERED"      # holds the exclusive claim window
    CONVERTED = "CONVERTED"  # claimed it and booked
    WITHDRAWN = "WITHDRAWN"  # left voluntarily, or the slot was withdrawn
    EXPIRED = "EXPIRED"      # claim window elapsed, or the slot time passed


# Statuses that occupy a place in the queue.
ACTIVE_WAITLIST_STATUSES = ("WAITING", "OFFERED")


class WaitlistEntry(Base):
    __tablename__ = "slot_waitlist"
    __table_args__ = (
        UniqueConstraint(
            "active_slot_id", "active_patient_id", name="uq_waitlist_active_pair"
        ),
        UniqueConstraint("offered_slot_id", name="uq_waitlist_one_offer_per_slot"),
        # Supports the FIFO head-of-queue lookup and the position count.
        Index("ix_waitlist_queue", "slot_id", "status", "created_at", "id"),
        Index("ix_waitlist_patient", "patient_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("slots.id", ondelete="CASCADE", name="fk_waitlist_slot"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_waitlist_patient"),
        nullable=False,
    )
    status: Mapped[WaitlistStatus] = mapped_column(
        _enum_column(WaitlistStatus), nullable=False, server_default=WaitlistStatus.WAITING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    offered_at: Mapped[datetime | None] = mapped_column(DateTime)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    # See the module docstring. VIRTUAL for the same reason as
    # appointments.occupies_slot_id: slot_id carries an ON DELETE CASCADE foreign key,
    # and MySQL forbids that on the base column of a STORED generated column.
    active_slot_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        Computed(
            f"IF(status IN ('{ACTIVE_WAITLIST_STATUSES[0]}','{ACTIVE_WAITLIST_STATUSES[1]}'), "
            "slot_id, NULL)",
            persisted=False,
        ),
        nullable=True,
    )
    active_patient_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        Computed(
            f"IF(status IN ('{ACTIVE_WAITLIST_STATUSES[0]}','{ACTIVE_WAITLIST_STATUSES[1]}'), "
            "patient_id, NULL)",
            persisted=False,
        ),
        nullable=True,
    )
    offered_slot_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        Computed("IF(status = 'OFFERED', slot_id, NULL)", persisted=False),
        nullable=True,
    )

    slot: Mapped["Slot"] = relationship(back_populates="waitlist")  # noqa: F821
    patient: Mapped["User"] = relationship(foreign_keys=[patient_id])  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.status in (WaitlistStatus.WAITING, WaitlistStatus.OFFERED)

    def __repr__(self) -> str:
        return (
            f"<WaitlistEntry id={self.id} slot_id={self.slot_id} "
            f"patient_id={self.patient_id} {self.status.value}>"
        )
