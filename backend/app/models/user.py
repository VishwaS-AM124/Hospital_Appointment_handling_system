"""Users: one table for both roles, discriminated by ``role``."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    DOCTOR = "DOCTOR"
    PATIENT = "PATIENT"


def _enum_column(enum_cls: type[enum.Enum]):
    """Store the enum's *value* in MySQL, not Python's member name."""
    return SQLEnum(
        enum_cls,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(_enum_column(UserRole), nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    services: Mapped[list["Service"]] = relationship(  # noqa: F821
        back_populates="doctor",
        cascade="all, delete-orphan",
        foreign_keys="Service.doctor_id",
    )
    slots: Mapped[list["Slot"]] = relationship(  # noqa: F821
        back_populates="doctor",
        cascade="all, delete-orphan",
        foreign_keys="Slot.doctor_id",
    )

    @property
    def is_doctor(self) -> bool:
        return self.role is UserRole.DOCTOR

    @property
    def is_patient(self) -> bool:
        return self.role is UserRole.PATIENT

    def __repr__(self) -> str:
        return f"<User id={self.id} role={self.role.value} email={self.email!r}>"
