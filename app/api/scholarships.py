from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.core.database import get_db
from app.models import Scholarship
from app.schemas import ScholarshipCreate, ScholarshipResponse, ScholarshipExistsResponse

router = APIRouter(prefix="/api/scholarships", tags=["Scholarships"])


# 1. Endpoint للتحقق من وجود المنحة (يمنع التكرار قبل الـ Scraping)
@router.get("/exists", response_model=ScholarshipExistsResponse)
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


# 2. Endpoint لإنشاء منحة جديدة
@router.post("/", response_model=ScholarshipResponse, status_code=status.HTTP_201_CREATED)
def create_scholarship(
    scholarship_data: ScholarshipCreate,
    db: Session = Depends(get_db)
):
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