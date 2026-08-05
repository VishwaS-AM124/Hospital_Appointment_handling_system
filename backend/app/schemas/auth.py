"""Registration, login and token payloads."""

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models import UserRole
from app.schemas.user import UserOut


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    specialization: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        # Stored lower-cased so "A@x.com" and "a@x.com" cannot become two accounts.
        return value.strip().lower()

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must contain at least one letter.")
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit.")
        return value

    @model_validator(mode="after")
    def _specialization_is_for_doctors(self) -> "RegisterRequest":
        if self.role is UserRole.PATIENT and self.specialization:
            raise ValueError("Only doctors can have a specialization.")
        if self.specialization is not None:
            self.specialization = self.specialization.strip() or None
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
