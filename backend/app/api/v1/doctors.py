"""Doctor directory.

Read-only and intentionally thin: it returns DoctorPublicOut (name + specialization),
never email or phone, so browsing the directory cannot be used to harvest contact
details. It exposes no schedule data at all — open slots come from /slots/open.
"""

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.models import User, UserRole
from app.schemas.service import ServiceOut
from app.schemas.user import DoctorPublicOut
from app.services import service_service

router = APIRouter()


@router.get("", response_model=list[DoctorPublicOut], summary="List doctors")
def list_doctors(
    db: DbSession,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=120, description="Name or specialization"),
) -> list[DoctorPublicOut]:
    stmt = select(User).where(User.role == UserRole.DOCTOR)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(User.full_name.like(pattern), User.specialization.like(pattern))
        )
    doctors = db.execute(stmt.order_by(User.full_name.asc())).scalars()
    return [DoctorPublicOut.model_validate(doctor) for doctor in doctors]


@router.get(
    "/{doctor_id}/services",
    response_model=list[ServiceOut],
    summary="A doctor's active services",
)
def list_doctor_services(
    doctor_id: int, db: DbSession, _: CurrentUser
) -> list[ServiceOut]:
    services = service_service.list_active_services_for_doctor(db, doctor_id)
    return [ServiceOut.model_validate(service) for service in services]
