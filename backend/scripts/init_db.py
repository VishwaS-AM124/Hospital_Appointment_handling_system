"""Create the database, apply sql/01_schema.sql, and load demo data.

Run from the backend/ directory:

    python -m scripts.init_db                       # create + schema + seed
    python -m scripts.init_db --no-seed             # schema only
    python -m scripts.init_db --drop --yes          # recreate from scratch
    python -m scripts.init_db --db appointment_db_test --no-seed

Safe to re-run: the DDL uses CREATE TABLE IF NOT EXISTS, and seeding clears the four
application tables first so demo data never accumulates duplicates.

Seed dates are generated relative to *now*, so a reviewer always finds upcoming
appointments no matter when they clone this.
"""

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow "python scripts/init_db.py" as well as "python -m scripts.init_db".
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.timeutil import utc_now_naive  # noqa: E402
from app.models import (  # noqa: E402
    Appointment,
    AppointmentStatus,
    CancelledBy,
    Notification,
    NotificationType,
    Service,
    Slot,
    SlotStatus,
    User,
    UserRole,
    WaitlistEntry,
    WaitlistStatus,
)

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "01_schema.sql"
DEMO_PASSWORD = "Passw0rd!"


# ----------------------------------------------------------------------- DDL plumbing


def split_statements(sql: str) -> list[str]:
    """Split a plain DDL script into statements.

    Adequate because this schema contains no stored programs (no BEGIN...END blocks or
    custom DELIMITER lines), so a semicolon always ends a statement. Line comments are
    stripped first so a ';' inside one cannot split anything.
    """
    without_comments = re.sub(r"--[^\n]*", "", sql)
    return [
        statement.strip()
        for statement in without_comments.split(";")
        if statement.strip()
    ]


def create_database(db_name: str) -> None:
    server = create_engine(settings.server_url, isolation_level="AUTOCOMMIT", future=True)
    with server.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    server.dispose()
    print(f"  database `{db_name}` ready")


def drop_database(db_name: str) -> None:
    server = create_engine(settings.server_url, isolation_level="AUTOCOMMIT", future=True)
    with server.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
    server.dispose()
    print(f"  dropped database `{db_name}`")


def apply_schema(engine) -> None:
    statements = split_statements(SCHEMA_FILE.read_text(encoding="utf-8"))
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    print(f"  applied {len(statements)} DDL statement(s) from {SCHEMA_FILE.name}")


def clear_tables(engine) -> None:
    """Truncate in FK-safe order with checks disabled, so ids restart at 1."""
    tables = (
        "notifications",
        "slot_waitlist",
        "appointments",
        "slots",
        "services",
        "users",
    )
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in tables:
            connection.execute(text(f"TRUNCATE TABLE `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    print("  cleared existing rows")


# ------------------------------------------------------------------------------- seed


def _next_weekday_at(base: datetime, days_ahead: int, hour: int, minute: int = 0) -> datetime:
    """A UTC instant `days_ahead` days from now, at a fixed UTC wall clock."""
    target = (base + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return target


def seed(engine) -> None:
    clear_tables(engine)
    now = utc_now_naive()
    password_hash = hash_password(DEMO_PASSWORD)

    with Session(engine, future=True) as db:
        doctors = [
            User(
                full_name="Dr. Anita Rao",
                email="anita.rao@citycare-hospital.com",
                password_hash=password_hash,
                role=UserRole.DOCTOR,
                specialization="Cardiology",
                phone="+91 98400 11111",
            ),
            User(
                full_name="Dr. Vikram Shah",
                email="vikram.shah@citycare-hospital.com",
                password_hash=password_hash,
                role=UserRole.DOCTOR,
                specialization="Orthopaedics",
                phone="+91 98400 22222",
            ),
            User(
                full_name="Dr. Leela Menon",
                email="leela.menon@citycare-hospital.com",
                password_hash=password_hash,
                role=UserRole.DOCTOR,
                specialization="Dermatology",
                phone="+91 98400 33333",
            ),
        ]
        patients = [
            User(
                full_name="Ravi Kumar",
                email="ravi.kumar@example.com",
                password_hash=password_hash,
                role=UserRole.PATIENT,
                phone="+91 90000 11111",
            ),
            User(
                full_name="Sana Iqbal",
                email="sana.iqbal@example.com",
                password_hash=password_hash,
                role=UserRole.PATIENT,
                phone="+91 90000 22222",
            ),
            User(
                full_name="John Doe",
                email="john.doe@example.com",
                password_hash=password_hash,
                role=UserRole.PATIENT,
                phone="+91 90000 33333",
            ),
            User(
                full_name="Mei Lin",
                email="mei.lin@example.com",
                password_hash=password_hash,
                role=UserRole.PATIENT,
                phone="+91 90000 44444",
            ),
        ]
        db.add_all(doctors + patients)
        db.flush()

        anita, vikram, leela = doctors
        ravi, sana, john, _mei = patients

        services = [
            Service(doctor_id=anita.id, name="Cardiology Consultation",
                    description="Initial consultation and ECG review.",
                    duration_minutes=30, price=800.00),
            Service(doctor_id=anita.id, name="Echocardiogram",
                    description="Ultrasound imaging of the heart.",
                    duration_minutes=45, price=2500.00),
            Service(doctor_id=vikram.id, name="Orthopaedic Consultation",
                    description="Joint and bone assessment.",
                    duration_minutes=30, price=700.00),
            Service(doctor_id=vikram.id, name="Fracture Follow-up",
                    description="Post-cast review and X-ray check.",
                    duration_minutes=20, price=450.00),
            Service(doctor_id=leela.id, name="Skin Consultation",
                    description="General dermatology assessment.",
                    duration_minutes=25, price=600.00),
            Service(doctor_id=leela.id, name="Acne Treatment Review",
                    description="Follow-up for ongoing acne therapy.",
                    duration_minutes=20, price=500.00, is_active=False),
        ]
        db.add_all(services)
        db.flush()

        cardiology, echo, ortho, fracture, skin, _acne = services

        slots: list[Slot] = []

        # A run of open slots over the next week for each doctor, so /slots/open is
        # immediately interesting to browse.
        for day in range(1, 8):
            for hour, (doctor, service) in enumerate(
                ((anita, cardiology), (vikram, ortho), (leela, skin)), start=9
            ):
                start = _next_weekday_at(now, day, hour)
                slots.append(
                    Slot(
                        doctor_id=doctor.id,
                        service_id=service.id,
                        start_at=start,
                        end_at=start + timedelta(minutes=service.duration_minutes),
                        status=SlotStatus.OPEN,
                    )
                )

        # A couple of extra open slots with a different service, to exercise filtering.
        echo_start = _next_weekday_at(now, 2, 14)
        slots.append(Slot(doctor_id=anita.id, service_id=echo.id, start_at=echo_start,
                          end_at=echo_start + timedelta(minutes=45), status=SlotStatus.OPEN))
        fracture_start = _next_weekday_at(now, 3, 15)
        slots.append(Slot(doctor_id=vikram.id, service_id=fracture.id,
                          start_at=fracture_start,
                          end_at=fracture_start + timedelta(minutes=20),
                          status=SlotStatus.OPEN))

        # --- slots that demonstrate each state -----------------------------------
        booked_start = _next_weekday_at(now, 1, 11)
        booked_slot = Slot(doctor_id=anita.id, service_id=cardiology.id,
                           start_at=booked_start,
                           end_at=booked_start + timedelta(minutes=30),
                           status=SlotStatus.BOOKED)

        booked_start_2 = _next_weekday_at(now, 2, 11)
        booked_slot_2 = Slot(doctor_id=vikram.id, service_id=ortho.id,
                             start_at=booked_start_2,
                             end_at=booked_start_2 + timedelta(minutes=30),
                             status=SlotStatus.BOOKED)

        # In the past, already attended.
        completed_start = _next_weekday_at(now, -3, 10)
        completed_slot = Slot(doctor_id=leela.id, service_id=skin.id,
                              start_at=completed_start,
                              end_at=completed_start + timedelta(minutes=25),
                              status=SlotStatus.COMPLETED)

        # Booked then cancelled, so the slot is OPEN again — rule 3, visible in the UI.
        reopened_start = _next_weekday_at(now, 4, 16)
        reopened_slot = Slot(doctor_id=anita.id, service_id=cardiology.id,
                             start_at=reopened_start,
                             end_at=reopened_start + timedelta(minutes=30),
                             status=SlotStatus.OPEN)

        slots += [booked_slot, booked_slot_2, completed_slot, reopened_slot]
        db.add_all(slots)
        db.flush()

        db.add_all(
            [
                Appointment(
                    slot_id=booked_slot.id, patient_id=ravi.id, doctor_id=anita.id,
                    status=AppointmentStatus.BOOKED,
                    reason="Chest tightness while climbing stairs.",
                ),
                Appointment(
                    slot_id=booked_slot_2.id, patient_id=sana.id, doctor_id=vikram.id,
                    status=AppointmentStatus.BOOKED,
                    reason="Left knee pain after running.",
                ),
                Appointment(
                    slot_id=completed_slot.id, patient_id=john.id, doctor_id=leela.id,
                    status=AppointmentStatus.COMPLETED,
                    reason="Persistent rash on forearm.",
                    doctor_notes="Contact dermatitis. Topical steroid for 10 days.",
                    completed_at=completed_slot.end_at,
                ),
                # The cancelled row that released `reopened_slot`.
                Appointment(
                    slot_id=reopened_slot.id, patient_id=ravi.id, doctor_id=anita.id,
                    status=AppointmentStatus.CANCELLED,
                    reason="Routine check-up.",
                    cancelled_by=CancelledBy.PATIENT,
                    cancel_reason="Work conflict — will rebook.",
                    cancelled_at=now - timedelta(hours=6),
                ),
            ]
        )
        db.commit()

    print(
        f"  seeded {len(doctors)} doctors, {len(patients)} patients, "
        f"{len(services)} services, {len(slots)} slots, 4 appointments"
    )
    print(f"\n  All demo accounts use the password: {DEMO_PASSWORD}")
    print("    doctor  anita.rao@citycare-hospital.com")
    print("    patient ravi.kumar@example.com")


# ------------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=settings.db_name, help="database name")
    parser.add_argument("--drop", action="store_true", help="DROP DATABASE first")
    parser.add_argument("--no-seed", action="store_true", help="skip demo data")
    parser.add_argument("--yes", action="store_true", help="skip the --drop confirmation")
    args = parser.parse_args()

    print(f"Target: {settings.db_user}@{settings.db_host}:{settings.db_port}/{args.db}")

    if args.drop:
        if not args.yes:
            answer = input(f"  DROP DATABASE `{args.db}` — all data lost. Type 'yes': ")
            if answer.strip().lower() != "yes":
                print("  aborted")
                return 1
        drop_database(args.db)

    create_database(args.db)

    url = settings.database_url.replace(f"/{settings.db_name}?", f"/{args.db}?")
    engine = create_engine(url, future=True)
    try:
        apply_schema(engine)
        if not args.no_seed:
            seed(engine)
    finally:
        engine.dispose()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
