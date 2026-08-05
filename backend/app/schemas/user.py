"""User output shapes.

Three deliberately different views of the same table. Patients browsing the directory
get DoctorPublicOut (no email, no phone); doctors looking at their own appointments get
PatientPublicOut (name and phone, because they need to call the patient); only the
account owner ever sees UserOut.
"""

from pydantic import BaseModel

from app.models import UserRole
from app.schemas.common import ORM_CONFIG, UtcDatetime


class UserOut(BaseModel):
    """The signed-in user's own profile. Never exposes password_hash."""

    model_config = ORM_CONFIG

    id: int
    full_name: str
    email: str
    role: UserRole
    specialization: str | None = None
    phone: str | None = None
    created_at: UtcDatetime


class DoctorPublicOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    full_name: str
    specialization: str | None = None


class PatientPublicOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    full_name: str
    phone: str | None = None
