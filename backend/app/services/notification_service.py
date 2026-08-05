"""Notification creation and inbox reads.

``notify()`` only ever *stages* a row with ``db.add()`` — it never commits. The caller
commits it as part of the transaction that caused the event, so a notification cannot
announce a booking that was rolled back.
"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import app_error
from app.core.timeutil import utc_now_naive
from app.models import Notification, NotificationType, User


def notify(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    title: str,
    body: str | None = None,
    slot_id: int | None = None,
    appointment_id: int | None = None,
) -> Notification:
    """Stage a notification. The caller's commit makes it real."""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        slot_id=slot_id,
        appointment_id=appointment_id,
    )
    db.add(notification)
    return notification


def list_notifications(
    db: Session,
    user: User,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int]:
    stmt: Select = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars()
    )
    return rows, total


def unread_count(db: Session, user: User) -> int:
    return db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalar_one()


def mark_read(db: Session, user: User, notification_id: int) -> Notification:
    notification = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            # Scoped by recipient, so one user can never mark another's inbox read.
            Notification.user_id == user.id,
        )
    ).scalar_one_or_none()
    if notification is None:
        raise app_error("NOTIFICATION_NOT_FOUND")

    if notification.read_at is None:
        notification.read_at = utc_now_naive()
        db.commit()
        db.refresh(notification)
    return notification


def mark_all_read(db: Session, user: User) -> int:
    now = utc_now_naive()
    unread = list(
        db.execute(
            select(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        ).scalars()
    )
    for notification in unread:
        notification.read_at = now
    db.commit()
    return len(unread)
