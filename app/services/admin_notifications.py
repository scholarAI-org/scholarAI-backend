"""Persist content and isolate read state without taking transaction ownership."""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.admin_notification import (
    AdminNotification,
    AdminNotificationRead,
    NotificationActionType,
    NotificationType,
)
from app.models.user import User


def _insert(db: Session, table):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return pg_insert(table)
    if dialect == "sqlite":
        return sqlite_insert(table)
    raise ValueError(f"Unsupported notification database dialect: {dialect}")


def create_admin_notification(
    db: Session,
    *,
    notification_type: NotificationType,
    title: str,
    message: str,
    related_entity_id: int | None = None,
    action_type: NotificationActionType | None = None,
    recipient_id: int | None = None,
    event_key: str | None = None,
) -> AdminNotification:
    """Create an unread notification; the caller must commit or roll back.

    Omit recipient_id for the global admin audience, including future admins.
    Supply a stable event_key for retryable events. It is scoped by type and
    audience; unrelated general notifications need no idempotency key.
    """
    kind = NotificationType(notification_type)
    action = NotificationActionType(action_type) if action_type is not None else None
    if not title.strip() or len(title) > 255 or not message.strip():
        raise ValueError(
            "Notification title and message must be nonempty; title max is 255"
        )
    if recipient_id is not None:
        admin = (
            db.query(User.id)
            .filter(User.id == recipient_id, User.role == "admin")
            .first()
        )
        if admin is None:
            raise ValueError("Notification recipient must be an existing admin")
    key = None
    if event_key is not None:
        audience = "global" if recipient_id is None else str(recipient_id)
        key = f"{kind.value}:{audience}:{event_key}"
        if not event_key.strip() or len(key) > 255:
            raise ValueError(
                "Event key must be nonempty and its scoped length at most 255"
            )
    values = {
        "notification_type": kind.value,
        "title": title,
        "message": message,
        "related_entity_id": related_entity_id,
        "action_type": action.value if action else None,
        "recipient_id": recipient_id,
        "event_key": key,
        "is_read": False,
    }
    # ON CONFLICT handles concurrent retries without rolling back the caller's work.
    statement = _insert(db, AdminNotification).values(**values)
    if key is not None:
        statement = statement.on_conflict_do_nothing(index_elements=["event_key"])
    notification_id = db.execute(
        statement.returning(AdminNotification.id)
    ).scalar_one_or_none()
    if notification_id is not None:
        return (
            db.query(AdminNotification)
            .filter(AdminNotification.id == notification_id)
            .one()
        )
    return db.query(AdminNotification).filter(AdminNotification.event_key == key).one()


def visible_notifications(db: Session, admin_id: int):
    """Shared projection for list, count, and mutation visibility checks."""
    read = AdminNotificationRead
    notification = AdminNotification
    return (
        db.query(
            notification.id,
            notification.notification_type.label("type"),
            notification.title,
            notification.message,
            notification.created_at,
            or_(notification.is_read.is_(True), read.admin_id.is_not(None)).label(
                "is_read"
            ),
            notification.related_entity_id,
            notification.action_type,
            func.coalesce(read.read_at, notification.read_at).label("read_at"),
        )
        .outerjoin(
            read,
            and_(read.notification_id == notification.id, read.admin_id == admin_id),
        )
        .filter(
            or_(
                notification.recipient_id.is_(None),
                notification.recipient_id == admin_id,
            )
        )
    )


def filtered_notifications(
    db: Session,
    admin_id: int,
    *,
    is_read: bool | None = None,
    notification_type: NotificationType | None = None,
):
    query = visible_notifications(db, admin_id)
    if is_read is not None:
        read_expression = or_(
            AdminNotification.is_read.is_(True),
            AdminNotificationRead.admin_id.is_not(None),
        )
        query = query.filter(read_expression.is_(is_read))
    if notification_type is not None:
        query = query.filter(
            AdminNotification.notification_type == notification_type.value
        )
    return query


def mark_notification_read(db: Session, admin_id: int, notification_id: int):
    notification = (
        visible_notifications(db, admin_id)
        .filter(AdminNotification.id == notification_id)
        .first()
    )
    if notification is None:
        return None
    # Insert only if absent, keeping the first timestamp even across concurrent requests.
    statement = (
        _insert(db, AdminNotificationRead)
        .values(
            admin_id=admin_id,
            notification_id=notification_id,
            read_at=notification.read_at or datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["admin_id", "notification_id"])
    )
    db.execute(statement)
    return db.execute(
        select(
            AdminNotificationRead.notification_id.label("id"),
            AdminNotificationRead.read_at,
        ).where(
            AdminNotificationRead.admin_id == admin_id,
            AdminNotificationRead.notification_id == notification_id,
        )
    ).one()
