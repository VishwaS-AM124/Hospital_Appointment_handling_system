"""Domain errors and the one JSON error envelope the whole API returns.

Every non-2xx response has the shape:

    {"error": {"code": "SLOT_ALREADY_BOOKED", "message": "...", "details": null}}

A stable machine-readable ``code`` is what lets the React client react specifically to
a lost booking race instead of showing a generic failure.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# code -> HTTP status
ERROR_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "NOT_AUTHENTICATED": 401,
    "INVALID_CREDENTIALS": 401,
    "TOKEN_INVALID": 401,
    "FORBIDDEN_ROLE": 403,
    "EMAIL_TAKEN": 409,
    "USER_NOT_FOUND": 404,
    "SERVICE_NOT_FOUND": 404,
    "SERVICE_NAME_TAKEN": 409,
    "SERVICE_IN_USE": 409,
    "SLOT_NOT_FOUND": 404,
    "SLOT_NOT_OPEN": 409,
    "SLOT_IN_PAST": 409,
    "SLOT_OVERLAP": 409,
    "SLOT_HAS_APPOINTMENT": 409,
    "SLOT_ALREADY_BOOKED": 409,
    "APPOINTMENT_NOT_FOUND": 404,
    "APPOINTMENT_NOT_ACTIVE": 409,
    "ALREADY_BOOKED_BY_YOU": 409,
    "PATIENT_TIME_CONFLICT": 409,
    "CANCEL_WINDOW_CLOSED": 409,
    "COMPLETE_TOO_EARLY": 409,
    "SLOT_RESERVED": 409,
    "SLOT_ALREADY_OPEN": 409,
    "ALREADY_ON_WAITLIST": 409,
    "WAITLIST_ENTRY_NOT_FOUND": 404,
    "NOTIFICATION_NOT_FOUND": 404,
    "INTERNAL_ERROR": 500,
}

# Default human-facing text. Callers may override with something more specific.
ERROR_MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "The request body failed validation.",
    "NOT_AUTHENTICATED": "You must sign in to do that.",
    "INVALID_CREDENTIALS": "That email and password combination is not valid.",
    "TOKEN_INVALID": "Your session is invalid or has expired. Please sign in again.",
    "FORBIDDEN_ROLE": "Your account role is not allowed to use this endpoint.",
    "EMAIL_TAKEN": "An account with that email address already exists.",
    "USER_NOT_FOUND": "User not found.",
    "SERVICE_NOT_FOUND": "Service not found.",
    "SERVICE_NAME_TAKEN": "You already have a service with that name.",
    "SERVICE_IN_USE": (
        "This service is attached to a booked or completed slot, so it cannot be "
        "deleted. Deactivate it instead to stop offering it."
    ),
    "SLOT_NOT_FOUND": "Slot not found.",
    "SLOT_NOT_OPEN": "That slot is no longer open for booking.",
    "SLOT_IN_PAST": "That slot's start time has already passed.",
    "SLOT_OVERLAP": "This overlaps another slot in your schedule.",
    "SLOT_HAS_APPOINTMENT": (
        "This slot has an appointment on it and cannot be edited or deleted. "
        "Cancel the appointment first."
    ),
    "SLOT_ALREADY_BOOKED": (
        "This slot was just booked by another patient. Please choose another time."
    ),
    "APPOINTMENT_NOT_FOUND": "Appointment not found.",
    "APPOINTMENT_NOT_ACTIVE": "This appointment is already cancelled or completed.",
    "ALREADY_BOOKED_BY_YOU": (
        "You already have an appointment on this slot — you can see it under "
        "My appointments."
    ),
    "PATIENT_TIME_CONFLICT": (
        "You already have an appointment that overlaps this time."
    ),
    "CANCEL_WINDOW_CLOSED": (
        "This appointment has already started, so it can no longer be cancelled "
        "online. Please contact the clinic."
    ),
    "COMPLETE_TOO_EARLY": (
        "This appointment cannot be marked completed before its start time."
    ),
    "SLOT_RESERVED": (
        "This slot is being held for the patient at the front of its waiting list. "
        "You will be offered it if they do not take it."
    ),
    "SLOT_ALREADY_OPEN": (
        "This slot is open — book it directly instead of joining the waiting list."
    ),
    "ALREADY_ON_WAITLIST": "You are already on the waiting list for this slot.",
    "WAITLIST_ENTRY_NOT_FOUND": "Waiting list entry not found.",
    "NOTIFICATION_NOT_FOUND": "Notification not found.",
    "INTERNAL_ERROR": "Something went wrong on our side.",
}


class AppError(Exception):
    """A predictable, user-facing failure. Routers let these bubble up."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def app_error(code: str, message: str | None = None, details: Any | None = None) -> AppError:
    """Build an AppError from the code tables above."""
    return AppError(
        code=code,
        message=message or ERROR_MESSAGES.get(code, "Request failed."),
        status_code=ERROR_STATUS.get(code, 400),
        details=details,
    )


def _envelope(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


# Starlette raises bare HTTPExceptions for things we never construct ourselves
# (404 on an unknown path, 405, and the 401/403 from security schemes). Map the
# common ones onto our own vocabulary so clients only ever see one error format.
_HTTP_STATUS_TO_CODE: dict[int, str] = {
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN_ROLE",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic error objects can contain non-JSON-serializable ctx values
        # (e.g. a ValueError instance), so flatten to primitives.
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        first = details[0]["message"] if details else ERROR_MESSAGES["VALIDATION_ERROR"]
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", first, details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the real cause, return a generic message: internals are not the
        # client's business.
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", ERROR_MESSAGES["INTERNAL_ERROR"]),
        )
