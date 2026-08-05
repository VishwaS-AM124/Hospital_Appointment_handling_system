"""Aggregates the v1 routers. Prefixes and tags are assigned here, not in the modules."""

from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    auth,
    doctors,
    notifications,
    services,
    slots,
    waitlist,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(doctors.router, prefix="/doctors", tags=["doctors"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(slots.router, prefix="/slots", tags=["slots"])
api_router.include_router(
    appointments.router, prefix="/appointments", tags=["appointments"]
)
api_router.include_router(waitlist.router, prefix="/waitlist", tags=["waitlist"])
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["notifications"]
)
