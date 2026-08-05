"""Appointments: a patient's claim on a slot.

This table carries the database-level guarantee behind business rule 1
("a slot can hold at most one booked appointment at a time"). See
``occupies_slot_id`` below.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import _enum_column

# Statuses that make an appointment "occupy" its slot. A cancelled appointment
# releases the slot (rule 3); a completed one does not (the visit happened).
OCCUPYING_STATUSES = ("BOOKED", "COMPLETED")


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class CancelledBy(str, enum.Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # ►►► BUSINESS RULE 1, ENFORCED BY THE DATABASE ITSELF ◄◄◄
        UniqueConstraint("occupies_slot_id", name="uq_appointments_occupied_slot"),
        Index("ix_appointments_patient", "patient_id", "status"),
        Index("ix_appointments_doctor", "doctor_id", "status"),
        Index("ix_appointments_slot", "slot_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("slots.id", ondelete="CASCADE", name="fk_appt_slot"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_appt_patient"),
        nullable=False,
    )
    # Denormalised from slots.doctor_id: every authorization check on the doctor side
    # filters by it, and it keeps patient history readable even after schedule churn.
    doctor_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_appt_doctor"),
        nullable=False,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum_column(AppointmentStatus),
        nullable=False,
        server_default=AppointmentStatus.BOOKED.value,
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    doctor_notes: Mapped[str | None] = mapped_column(String(1000))
    cancelled_by: Mapped[CancelledBy | None] = mapped_column(_enum_column(CancelledBy))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # MySQL has no partial indexes, so we project "does this row occupy its slot?"
    # into a generated column and put a plain UNIQUE index on it. The index ignores
    # NULLs, which yields exactly the constraint we want:
    #   at most ONE live (BOOKED/COMPLETED) appointment per slot,
    #   unlimited CANCELLED ones — so a released slot is re-bookable (rule 3).
    #
    # It MUST be VIRTUAL (persisted=False), not STORED. Verified on MySQL 8.0.44:
    # STORED makes CREATE TABLE fail with "ERROR 1215: Cannot add foreign key
    # constraint", because MySQL forbids ON DELETE CASCADE on the *base column* of a
    # STORED generated column — and slot_id is the base column. InnoDB indexes
    # virtual columns fine, so the guarantee is identical. Do not change this.
    occupies_slot_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        Computed(
            f"IF(status IN ('{OCCUPYING_STATUSES[0]}','{OCCUPYING_STATUSES[1]}'), slot_id, NULL)",
            persisted=False,
        ),
        nullable=True,
    )

    slot: Mapped["Slot"] = relationship(back_populates="appointments")  # noqa: F821
    patient: Mapped["User"] = relationship(foreign_keys=[patient_id])  # noqa: F821
    doctor: Mapped["User"] = relationship(foreign_keys=[doctor_id])  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.status is AppointmentStatus.BOOKED

    def __repr__(self) -> str:
        return (
            f"<Appointment id={self.id} slot_id={self.slot_id} "
            f"patient_id={self.patient_id} {self.status.value}>"
        )
