from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.user import User
from app.models.profile import Profile, WorkExperience, LanguageDetail
from app.schemas.profile import (
    ProfileCreate, 
    ProfileUpdate, 
    ProfileResponse, 
    WorkExperienceCreate, 
    WorkExperienceResponse, 
    LanguageCreate, 
    LanguageResponse
)
from app.core.security import get_current_user  # دالة التحقق من التوكن للمستخدم الحالي

router = APIRouter(
    prefix="/profile",
    tags=["Profile"]
)

# ==========================================
# 1. إنشاء البروفايل لأول مرة
# ==========================================
@router.post("/", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    profile_data: ProfileCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    # التأكد من عدم وجود بروفايل سابق للمستخدم
    existing_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Profile already exists for this user."
        )

    # تفكيك بيانات البروفايل وفصل القوائم (Experiences & Languages)
    data_dict = profile_data.model_dump()
    experiences_data = data_dict.pop("experiences", [])
    languages_data = data_dict.pop("languages", [])

    # إنشاء سجل البروفايل الرئيسي
    new_profile = Profile(**data_dict, user_id=current_user.id)
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)

    # إضافة خبرات العمل إن وجدت
    for exp in experiences_data:
        db.add(WorkExperience(**exp, profile_id=new_profile.id))

    # إضافة اللغات إن وجدت
    for lang in languages_data:
        db.add(LanguageDetail(**lang, profile_id=new_profile.id))

    db.commit()
    db.refresh(new_profile)
    return new_profile


# ==========================================
# 2. جلب البروفايل الخاص بالمستخدم الحالي
# ==========================================
@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Profile not found."
        )
    return profile


# ==========================================
# 3. تحديث البيانات الأساسية للبروفايل
# ==========================================
@router.put("/me", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Profile not found."
        )

    # تحديث الحقول التي أُرسلت فقط (Exclude Unset)
    update_data = profile_data.model_dump(exclude_unset=True)

    required_fields = {
        "full_name",
        "gender",
        "date_of_birth",
        "nationality",
        "country_of_residence",
        "country",
        "city",
        "phone_number",
        "degree",
        "major",
        "institution_name",
        "graduation_year",
        "gpa",
    }

    for key, value in update_data.items():
        if key in required_fields and value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{key} cannot be null."
            )

        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile


# ==========================================
# 4. إضافة خبرة عمل جديدة منفصلة
# ==========================================
@router.post("/experiences", response_model=WorkExperienceResponse, status_code=status.HTTP_201_CREATED)
def add_experience(
    exp_data: WorkExperienceCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Please create a profile first."
        )

    new_exp = WorkExperience(**exp_data.model_dump(), profile_id=profile.id)
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    return new_exp


# ==========================================
# 5. إضافة لغة جديدة منفصلة
# ==========================================
@router.post("/languages", response_model=LanguageResponse, status_code=status.HTTP_201_CREATED)
def add_language(
    lang_data: LanguageCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Please create a profile first."
        )

    new_lang = LanguageDetail(**lang_data.model_dump(), profile_id=profile.id)
    db.add(new_lang)
    db.commit()
    db.refresh(new_lang)
    return new_lang