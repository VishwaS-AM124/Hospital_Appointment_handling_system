"""Doctor service (offering) CRUD. Doctor-only; every handler is ownership-filtered."""

from fastapi import APIRouter, status

from app.api.deps import DbSession, DoctorUser
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate
from app.services import service_service

router = APIRouter()


# NOTE: literal paths are declared before "/{service_id}" so that /mine is never
# captured by the parameterised route.
@router.get("/mine", response_model=list[ServiceOut], summary="My services")
def list_my_services(db: DbSession, doctor: DoctorUser) -> list[ServiceOut]:
    services = service_service.list_services(db, doctor)
    return [ServiceOut.model_validate(service) for service in services]


@router.post(
    "",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a service",
)
def create_service(
    payload: ServiceCreate, db: DbSession, doctor: DoctorUser
) -> ServiceOut:
    service = service_service.create_service(db, doctor, payload)
    return ServiceOut.model_validate(service)


@router.get("/{service_id}", response_model=ServiceOut, summary="Get one of my services")
def get_service(service_id: int, db: DbSession, doctor: DoctorUser) -> ServiceOut:
    service = service_service.get_owned_service(db, doctor, service_id)
    return ServiceOut.model_validate(service)


@router.patch("/{service_id}", response_model=ServiceOut, summary="Update a service")
def update_service(
    service_id: int, payload: ServiceUpdate, db: DbSession, doctor: DoctorUser
) -> ServiceOut:
    service = service_service.update_service(db, doctor, service_id, payload)
    return ServiceOut.model_validate(service)


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a service (refused while a booked slot uses it)",
)
def delete_service(service_id: int, db: DbSession, doctor: DoctorUser) -> None:
    service_service.delete_service(db, doctor, service_id)
