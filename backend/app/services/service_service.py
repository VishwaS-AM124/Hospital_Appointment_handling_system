"""Doctor 'service' (offering) CRUD.

Every function takes the acting doctor and filters by ``doctor_id``, so one doctor can
never read or mutate another's catalogue (rule 5).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import app_error
from app.models import Service, Slot, SlotStatus, User
from app.schemas.service import ServiceCreate, ServiceUpdate


def list_services(db, doctor: User) -> list[Service]:
    return list(
        db.execute(
            select(Service)
            .where(Service.doctor_id == doctor.id)
            .order_by(Service.created_at.desc(), Service.id.desc())
        ).scalars()
    )


def list_active_services_for_doctor(db, doctor_id: int) -> list[Service]:
    """Public view used by patients browsing a doctor's offerings."""
    return list(
        db.execute(
            select(Service)
            .where(Service.doctor_id == doctor_id, Service.is_active.is_(True))
            .order_by(Service.name.asc())
        ).scalars()
    )


def get_owned_service(db, doctor: User, service_id: int) -> Service:
    """Fetch a service the doctor owns.

    A service that exists but belongs to someone else raises SERVICE_NOT_FOUND, not a
    403: a 403 would confirm the id is real and let an attacker enumerate the table.
    """
    service = db.execute(
        select(Service).where(
            Service.id == service_id, Service.doctor_id == doctor.id
        )
    ).scalar_one_or_none()
    if service is None:
        raise app_error("SERVICE_NOT_FOUND")
    return service


def create_service(db, doctor: User, payload: ServiceCreate) -> Service:
    service = Service(
        doctor_id=doctor.id,
        name=payload.name,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        price=payload.price,
        is_active=payload.is_active,
    )
    db.add(service)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_services_doctor_name" in str(exc.orig):
            raise app_error("SERVICE_NAME_TAKEN") from exc
        raise
    db.refresh(service)
    return service


def update_service(db, doctor: User, service_id: int, payload: ServiceUpdate) -> Service:
    service = get_owned_service(db, doctor, service_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(service, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_services_doctor_name" in str(exc.orig):
            raise app_error("SERVICE_NAME_TAKEN") from exc
        raise
    db.refresh(service)
    return service


def delete_service(db, doctor: User, service_id: int) -> None:
    """Hard-delete a service.

    Refused while any booked or completed slot still points at it — deleting it would
    rewrite history that a patient has already seen. Slots that are merely OPEN are
    fine: the FK is ON DELETE SET NULL, so they simply lose their label.
    """
    service = get_owned_service(db, doctor, service_id)
    in_use = db.execute(
        select(Slot.id)
        .where(Slot.service_id == service.id, Slot.status != SlotStatus.OPEN)
        .limit(1)
    ).scalar_one_or_none()
    if in_use is not None:
        raise app_error("SERVICE_IN_USE")
    db.delete(service)
    db.commit()
