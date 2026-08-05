"""In-app notifications.

Rows are written inside the same transaction as the event that caused them, so a
notification can never claim something that was rolled back. Delivery to the browser is
by polling ``GET /notifications`` — see docs/DESIGN.md for why not WebSockets here.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import _enum_column


class NotificationType(str, enum.Enum):
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"        # -> doctor: a patient booked you
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"  # -> the other party
    APPOINTMENT_COMPLETED = "APPOINTMENT_COMPLETED"  # -> patient
    SLOT_AVAILABLE = "SLOT_AVAILABLE"                # -> next in queue: claim it now
    WAITLIST_JOINED = "WAITLIST_JOINED"              # -> patient: you are #N in line
    WAITLIST_MISSED = "WAITLIST_MISSED"              # -> patient: claim window elapsed
    SLOT_WITHDRAWN = "SLOT_WITHDRAWN"                # -> queue: doctor removed the slot


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # The unread badge and the inbox listing both hit this index.
        Index("ix_notifications_user_unread", "user_id", "read_at", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_notification_user"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        _enum_column(NotificationType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(String(600))

    # Deep links. Both SET NULL rather than CASCADE: the notification is a historical
    # record and should survive the thing it refers to being removed.
    slot_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("slots.id", ondelete="SET NULL", name="fk_notification_slot"),
    )
    appointment_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("appointments.id", ondelete="SET NULL", name="fk_notification_appt"),
    )

    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} {self.type.value}>"
