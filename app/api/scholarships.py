from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Scholarship
from app.models.user import User
from app.schemas import (
    ScholarshipCreate,
    ScholarshipExistsResponse,
    ScholarshipResponse,
    ScholarshipStatusDistribution,
)

router = APIRouter(prefix="/api/scholarships", tags=["Scholarships"])

SCHOLARSHIP_DISTRIBUTION_STATUS_MAP = {
    "published": "approved",
    "pending": "pending",
    "rejected": "rejected",
}


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
        db.commit()
        db.refresh(new_scholarship)
        return new_scholarship
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="خطأ في قيد البيانات أو أنها مكررة."
        )
