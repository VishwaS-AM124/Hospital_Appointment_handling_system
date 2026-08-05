"""Waiting-queue payloads."""

from pydantic import BaseModel

from app.models import WaitlistStatus
from app.schemas.common import ORM_CONFIG, UtcDatetime
from app.schemas.slot import SlotOut
from app.schemas.user import PatientPublicOut


class WaitlistJoinRequest(BaseModel):
    """Body is empty today; kept so the endpoint can gain options without a version bump."""


class WaitlistEntryOut(BaseModel):
    model_config = ORM_CONFIG

    id: int
    slot_id: int
    patient_id: int
    status: WaitlistStatus
    created_at: UtcDatetime
    offered_at: UtcDatetime | None = None
    offer_expires_at: UtcDatetime | None = None

    # 1-based place in the queue; None once the entry is no longer active.
    position: int | None = None
    # True while this entry holds the exclusive, unexpired claim window.
    can_claim_now: bool = False

    slot: SlotOut | None = None
    patient: PatientPublicOut | None = None


class WaitlistSummaryOut(BaseModel):
    """Attached to the error body when a booking attempt puts the caller in a queue."""

    waitlist_id: int
    slot_id: int
    position: int
    queue_length: int
