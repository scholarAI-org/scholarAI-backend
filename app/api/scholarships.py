from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Scholarship
from app.models.admin_notification import NotificationActionType, NotificationType
from app.models.user import User
from app.schemas import (
    RecommendationScholarshipResponse,
    ScholarshipCreate,
    ScholarshipExistsResponse,
    ScholarshipResponse,
    ScholarshipStatusDistribution,
)
from app.services.admin_notifications import create_admin_notification
from app.services.audit import create_audit_log

router = APIRouter(prefix="/api/scholarships", tags=["Scholarships"])

SCHOLARSHIP_DISTRIBUTION_STATUS_MAP = {
    "published": "approved",
    "pending": "pending",
    "rejected": "rejected",
}


@router.get(
    "/recommendations",
    response_model=list[RecommendationScholarshipResponse],
    summary="Get scholarships for the recommendation system",
    description=(
        "Public feed of all scholarships, ordered by ID, regardless of status. "
        "Each listing retains its stored status. "
        "The description field contains the source description HTML."
    ),
)
def get_recommendation_scholarships(db: Session = Depends(get_db)):
    return (
        db.query(
            Scholarship.id,
            Scholarship.title,
            Scholarship.slug,
            Scholarship.country,
            Scholarship.deadline,
            Scholarship.description_html.label("description"),
            Scholarship.apply_link,
            Scholarship.status,
        )
        .order_by(Scholarship.id.asc())
        .all()
    )


@router.get(
    "/exists",
    response_model=ScholarshipExistsResponse,
    summary="Check if a scholarship already exists",
    description="Used by scrapers to skip duplicates before ingesting a listing.",
)
def check_scholarship_exists(
    source: str = Query(..., description="مصدر المنحة مثل 'for9a' أو 'ministry'"),
    source_id: str = Query(..., description="المعرف الفريد للمنحة من الموقع الأصلي"),
    db: Session = Depends(get_db)
):
    scholarship = db.query(Scholarship).filter(
        Scholarship.source == source,
        Scholarship.source_id == source_id
    ).first()

    if scholarship:
        return {"exists": True, "scholarship_id": scholarship.id}
    
    return {"exists": False, "scholarship_id": None}


@router.get(
    "/status-distribution",
    response_model=ScholarshipStatusDistribution,
    summary="Get scholarship status distribution",
    description="Returns scholarship counts by status. Requires an authenticated admin.",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_scholarship_status_distribution(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    counts = (
        db.query(Scholarship.status, func.count(Scholarship.id))
        .filter(Scholarship.status.in_(SCHOLARSHIP_DISTRIBUTION_STATUS_MAP.values()))
        .group_by(Scholarship.status)
        .all()
    )
    counts_by_stored_status = dict(counts)
    return {
        response_status: counts_by_stored_status.get(stored_status, 0)
        for response_status, stored_status in SCHOLARSHIP_DISTRIBUTION_STATUS_MAP.items()
    }


@router.post(
    "/",
    response_model=ScholarshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a scholarship listing",
    responses={
        400: {"description": "Integrity / duplicate constraint error"},
        403: {"description": "Requires admin role"},
        409: {"description": "Scholarship already exists for this source and source_id"},
    },
)
def create_scholarship(
    scholarship_data: ScholarshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # مصادقة مطلوبة
):
    # تحقق من صلاحية المستخدم — admin فقط
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه العملية مخصصة للمشرفين فقط.",
        )
    # تحقق احترازي لمنع تكرار نفس المنحة إذا أُرسلت مجدداً
    if scholarship_data.source_id:
        existing = db.query(Scholarship).filter(
            Scholarship.source == scholarship_data.source,
            Scholarship.source_id == scholarship_data.source_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="هذه المنحة مسجلة مسبقاً من هذا المصدر."
            )

    new_scholarship = Scholarship(**scholarship_data.model_dump())
    
    try:
        db.add(new_scholarship)
        db.flush()
        if (
            new_scholarship.source in {"for9a", "ministry"}
            and new_scholarship.status == "pending"
        ):
            create_admin_notification(
                db,
                notification_type=NotificationType.SCHOLARSHIP_REVIEW,
                title="New scholarship pending review",
                message=f'New aggregated scholarship "{new_scholarship.title}" requires review.',
                related_entity_id=cast(int, new_scholarship.id),
                action_type=NotificationActionType.OPEN_SCHOLARSHIP_REVIEW,
                event_key=f"scholarship:{new_scholarship.id}:pending",
            )
        # The audit helper commits the scholarship, notification, and audit together.
        create_audit_log(
            db=db,
            admin=current_user,
            action="create",
            action_display="إضافة منحة",
            entity_name=new_scholarship.title,
            entity_id=new_scholarship.id,
            details={
                "source": new_scholarship.source,
                "country": new_scholarship.country,
            },
        )
        return new_scholarship
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="خطأ في قيد البيانات أو أنها مكررة."
        )
    except Exception:
        db.rollback()
        raise
