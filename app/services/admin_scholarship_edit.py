from datetime import datetime, timezone
from typing import Any, cast

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.Scholarship import Scholarship
from app.models.user import User
from app.schemas.admin import ScholarshipReviewStatus
from app.schemas.admin_scholarship_edit import AdminScholarshipUpdate
from app.services.audit import create_audit_log


def edit_pending_scholarship(
    db: Session,
    scholarship_id: int,
    payload: AdminScholarshipUpdate,
    admin: User,
) -> Scholarship:
    """Persist content changes and their audit record in one transaction."""
    try:
        scholarship = (
            db.query(Scholarship)
            .filter(Scholarship.id == scholarship_id)
            .with_for_update()
            .first()
        )
        if scholarship is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scholarship not found.",
            )
        if scholarship.status != ScholarshipReviewStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending scholarships can be edited during review.",
            )

        changes: dict[str, Any] = {}
        for field, new_value in payload.model_dump(exclude_unset=True).items():
            old_value = getattr(scholarship, field)
            if old_value != new_value:
                changes[field] = {"old": old_value, "new": new_value}
                setattr(scholarship, field, new_value)

        if not changes:
            return scholarship

        scholarship.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        # The existing helper commits both the dirty scholarship and the audit.
        create_audit_log(
            db=db,
            admin=admin,
            action="edit",
            entity_name=cast(str, scholarship.title)[:255],
            entity_id=cast(int, scholarship.id),
            details={"changes": jsonable_encoder(changes)},
        )
        db.refresh(scholarship)
        return scholarship
    except Exception:
        db.rollback()
        raise
