import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocumentUploadSessionStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentUploadSession(Base):
    __tablename__ = "document_upload_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type = Column(String(64), nullable=False)
    object_key = Column(String(512), nullable=False, unique=True)
    original_file_name = Column(String(255), nullable=False)
    expected_content_type = Column(String(128), nullable=False)
    expected_file_size = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default=DocumentUploadSessionStatus.PENDING.value)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    user = relationship("User")
