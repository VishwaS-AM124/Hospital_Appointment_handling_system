"""Notification inbox. Every query is scoped to the signed-in recipient."""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services import notification_service

router = APIRouter()


# Literal paths before "/{notification_id}/…" so they are never shadowed.
@router.get("", response_model=Page[NotificationOut], summary="My notifications")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationOut]:
    items, total = notification_service.list_notifications(
        db, user, unread_only=unread_only, page=page, page_size=page_size
    )
    return Page.build(
        [NotificationOut.model_validate(item) for item in items], total, page, page_size
    )


@router.get(
    "/unread-count", response_model=UnreadCountOut, summary="Unread badge count"
)
def get_unread_count(db: DbSession, user: CurrentUser) -> UnreadCountOut:
    return UnreadCountOut(unread=notification_service.unread_count(db, user))


@router.post("/read-all", response_model=UnreadCountOut, summary="Mark all as read")
def mark_all_read(db: DbSession, user: CurrentUser) -> UnreadCountOut:
    notification_service.mark_all_read(db, user)
    return UnreadCountOut(unread=0)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark one as read",
)
def mark_read(
    notification_id: int, db: DbSession, user: CurrentUser
) -> NotificationOut:
    notification = notification_service.mark_read(db, user, notification_id)
    return NotificationOut.model_validate(notification)
