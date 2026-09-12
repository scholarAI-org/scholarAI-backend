from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.core.database import Base


class NotificationType(str, Enum):
    GENERAL = "general"
    SCHOLARSHIP = "scholarship"
    SCHOLARSHIP_REVIEW = "scholarship_review"


class NotificationActionType(str, Enum):
    OPEN_SCHOLARSHIP_REVIEW = "open_scholarship_review"


class AdminNotification(Base):
    __tablename__ = "admin_notifications"
    __table_args__ = (
        Index(
            "ix_admin_notifications_recipient_created",
            "recipient_id",
            "created_at",
            "id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), nullable=False, default="general")
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at = Column(DateTime(timezone=True), nullable=True)
    # NULL audience is global. Never update the legacy shared read fields:
    # they are a historical baseline; all new reads live in the per-admin table.
    recipient_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    related_entity_id = Column(Integer, nullable=True)
    action_type = Column(String(50), nullable=True)
    event_key = Column(String(255), nullable=True, unique=True)


class AdminNotificationRead(Base):
    __tablename__ = "admin_notification_reads"

    admin_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    notification_id = Column(
        Integer,
        ForeignKey("admin_notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
