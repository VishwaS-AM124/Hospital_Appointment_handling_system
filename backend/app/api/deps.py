"""Shared FastAPI dependencies: DB session, current user, role gates.

The authorization boundary has two distinct halves, and both matter:

  * Role gates (``DoctorUser`` / ``PatientUser``) answer "may this *kind* of account
    call this endpoint at all?" and fail with 403 FORBIDDEN_ROLE.
  * Ownership filters, applied inside every service function, answer "is this
    particular row yours?" and fail with 404.

A role gate alone is not authorization: without the ownership filter, any doctor could
read any other doctor's schedule just by guessing an id.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import app_error
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User, UserRole

# auto_error=False so a missing header raises our own NOT_AUTHENTICATED envelope
# instead of Starlette's bare {"detail": "Not authenticated"}.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token value.")

# Declared only so Swagger UI renders an Authorize button that posts the login form.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/token", auto_error=False
)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    oauth_token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """Resolve the bearer token to a live user row.

    Accepts the token from either security scheme so both the Swagger Authorize button
    and a plain Authorization header work.
    """
    token = credentials.credentials if credentials else oauth_token
    if not token:
        raise app_error("NOT_AUTHENTICATED")

    payload = decode_access_token(token)
    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise app_error("TOKEN_INVALID") from exc

    user = db.get(User, user_id)
    if user is None:
        # Token signed correctly but the account is gone — treat as an invalid session.
        raise app_error("TOKEN_INVALID")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_doctor(user: CurrentUser) -> User:
    if user.role is not UserRole.DOCTOR:
        raise app_error(
            "FORBIDDEN_ROLE", "Only a doctor account can use this endpoint."
        )
    return user


def require_patient(user: CurrentUser) -> User:
    if user.role is not UserRole.PATIENT:
        raise app_error(
            "FORBIDDEN_ROLE", "Only a patient account can use this endpoint."
        )
    return user


DoctorUser = Annotated[User, Depends(require_doctor)]
PatientUser = Annotated[User, Depends(require_patient)]
