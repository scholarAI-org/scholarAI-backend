from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User

ACTION_DISPLAY_MAP = {
    "publish": "اعتماد ونشر",
    "edit": "تعديل",
    "delete": "حذف",
}


def create_audit_log(
    db: Session,
    admin: User,
    action: str,
    entity_name: str,
    entity_type: str = "scholarship",
    entity_id: Optional[int] = None,
    action_display: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Helper to record an administrative action in the audit log."""
    display = action_display or ACTION_DISPLAY_MAP.get(action.lower(), action)
    log = AuditLog(
        admin_id=admin.id,
        admin_name=admin.full_name or "المسؤول",
        action=action.lower(),
        action_display=display,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
