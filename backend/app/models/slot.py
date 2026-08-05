"""Slots: a bookable window in one doctor's calendar.

``status`` is the fast path for "is this bookable?". It is kept in lockstep with the
appointments table by the service layer, always inside the same transaction:

    OPEN      -> no occupying appointment
    BOOKED    -> exactly one appointment with status BOOKED
    COMPLETED -> exactly one appointment with status COMPLETED (stays unbookable)
"""

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import _enum_column


class SlotStatus(str, enum.Enum):
    OPEN = "OPEN"
    BOOKED = "BOOKED"
    COMPLETED = "COMPLETED"


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        Index("ix_slots_doctor_start", "doctor_id", "start_at"),
        Index("ix_slots_open_browse", "status", "start_at"),
        Index("ix_slots_service", "service_id"),
        CheckConstraint("end_at > start_at", name="ck_slots_time"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_slots_doctor"),
        nullable=False,
    )
    service_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("services.id", ondelete="SET NULL", name="fk_slots_service"),
    )
    # Naive UTC — see app/core/timeutil.py.
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        _enum_column(SlotStatus), nullable=False, server_default=SlotStatus.OPEN.value
    )
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    doctor: Mapped["User"] = relationship(  # noqa: F821
        back_populates="slots", foreign_keys=[doctor_id]
    )
    service: Mapped["Service | None"] = relationship(  # noqa: F821
        back_populates="slots", foreign_keys=[service_id]
    )
    appointments: Mapped[list["Appointment"]] = relationship(  # noqa: F821
        back_populates="slot", cascade="all, delete-orphan"
    )
    waitlist: Mapped[list["WaitlistEntry"]] = relationship(  # noqa: F821
        back_populates="slot", cascade="all, delete-orphan"
    )

    @property
    def duration_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)

    def __repr__(self) -> str:
        return f"<Slot id={self.id} doctor_id={self.doctor_id} {self.start_at} {self.status.value}>"
