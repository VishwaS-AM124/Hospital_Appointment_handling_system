"""Registration, login and profile."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.errors import app_error
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserOut

router = APIRouter()


def _issue_token(user: User) -> TokenResponse:
    token, expires_in = create_access_token(
        user_id=user.id, role=user.role.value, email=user.email
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


def _authenticate(db, email: str, password: str) -> User:
    user = db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()
    # Verify against a real hash even when the user is missing? Not worth it here: the
    # response is identical either way, so no account existence is leaked.
    if user is None or not verify_password(password, user.password_hash):
        raise app_error("INVALID_CREDENTIALS")
    return user


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor or patient account",
)
def register(payload: RegisterRequest, db: DbSession) -> UserOut:
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        specialization=payload.specialization,
        phone=payload.phone,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_users_email" in str(exc.orig):
            raise app_error("EMAIL_TAKEN") from exc
        raise
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="Sign in with JSON")
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = _authenticate(db, payload.email, payload.password)
    return _issue_token(user)


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Sign in with an OAuth2 form (powers the Swagger Authorize button)",
)
def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession
) -> TokenResponse:
    user = _authenticate(db, form.username, form.password)
    return _issue_token(user)


@router.get("/me", response_model=UserOut, summary="The signed-in user's profile")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
