from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    admin_name = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False, index=True)  # 'publish', 'edit', 'delete'
    action_display = Column(String(100), nullable=False)  # 'اعتماد ونشر', 'تعديل', 'حذف'
    entity_type = Column(String(50), nullable=False, default="scholarship")
    entity_id = Column(Integer, nullable=True)
    entity_name = Column(String(255), nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
