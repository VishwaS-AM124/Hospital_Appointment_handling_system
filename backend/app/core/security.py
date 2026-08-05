"""Password hashing (bcrypt) and access tokens (JWT, HS256)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import app_error

# bcrypt hashes at most 72 bytes and bcrypt>=4.1 raises instead of silently
# truncating, so we truncate explicitly and document it.
_BCRYPT_MAX_BYTES = 72


def _password_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_password_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check. Returns False (never raises) on a malformed stored hash,
    so a corrupt row cannot turn into a 500."""
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str, email: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        # 'sub' must be a string — PyJWT rejects non-string subjects on decode.
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a bearer token. Expired and malformed both surface as
    TOKEN_INVALID: distinguishing them tells an attacker which guesses were closer."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise app_error("TOKEN_INVALID") from exc
