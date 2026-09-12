from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Scholarship
from app.models.user import User
from app.schemas.scholarship_review_details import ScholarshipReviewDetailsResponse

router = APIRouter(prefix="/admin/scholarships", tags=["Admin"])


@router.get(
    "/{scholarship_id}/review-details",
    response_model=ScholarshipReviewDetailsResponse,
    summary="Get scholarship review details",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def get_scholarship_review_details(
    scholarship_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipReviewDetailsResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = (
        db.query(
            Scholarship.title,
            Scholarship.organization_name,
            Scholarship.country,
            Scholarship.description_html.label("description"),
        )
        .filter(Scholarship.id == scholarship_id)
        .first()
    )
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return ScholarshipReviewDetailsResponse.model_validate(scholarship)
