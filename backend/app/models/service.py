"""Services: what a doctor offers. Slots may optionally reference one."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("doctor_id", "name", name="uq_services_doctor_name"),
        Index("ix_services_doctor", "doctor_id", "is_active"),
        CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_services_duration"),
        CheckConstraint("price >= 0", name="ck_services_price"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_services_doctor"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0.00"
    )
    is_active: Mapped[bool] = mapped_column(TINYINT(1), nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    doctor: Mapped["User"] = relationship(  # noqa: F821
        back_populates="services", foreign_keys=[doctor_id]
    )
    slots: Mapped[list["Slot"]] = relationship(  # noqa: F821
        back_populates="service", foreign_keys="Slot.service_id"
    )

    def __repr__(self) -> str:
        return f"<Service id={self.id} doctor_id={self.doctor_id} name={self.name!r}>"
