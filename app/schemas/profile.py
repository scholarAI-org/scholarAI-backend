from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date

# ==========================================
# 1. Schemas الخاص باللغات (Language)
# ==========================================
class LanguageBase(BaseModel):
    language_name: str
    proficiency_level: Optional[str] = None
    certificate_url: Optional[str] = None

class LanguageCreate(LanguageBase):
    pass

class LanguageResponse(LanguageBase):
    id: int
    profile_id: int

    class Config:
        from_attributes = True


# ==========================================
# 2. Schemas الخااص ببيانات العمل (Work Experience)
# ==========================================
class WorkExperienceBase(BaseModel):
    company_name: str
    role_title: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: Optional[bool] = False

class WorkExperienceCreate(WorkExperienceBase):
    pass

class WorkExperienceResponse(WorkExperienceBase):
    id: int
    profile_id: int

    class Config:
        from_attributes = True


# ==========================================
# 3. Schemas الرئيسي للبروفايل (Profile)
# ==========================================
class ProfileBase(BaseModel):
    # Personal Info
    full_name: str
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None

    # Family & Financial Info
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    father_income: Optional[float] = 0.0
    mother_income: Optional[float] = 0.0
    num_of_siblings: Optional[int] = 0
    currency: Optional[str] = "USD"

    # Contact Info
    email: Optional[EmailStr] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None

    # Academic Background
    degree: Optional[str] = None
    major: Optional[str] = None
    institution_name: Optional[str] = None
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None


# Schema لإدخال بيانات البروفايل لأول مرة (يمكن إضافة قوائم للخبرات واللغات)
class ProfileCreate(ProfileBase):
    experiences: Optional[List[WorkExperienceCreate]] = []
    languages: Optional[List[LanguageCreate]] = []


# Schema لتحديث البروفايل (جميع الحقول اختيارية)
class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    father_income: Optional[float] = None
    mother_income: Optional[float] = None
    num_of_siblings: Optional[int] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    degree: Optional[str] = None
    major: Optional[str] = None
    institution_name: Optional[str] = None
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None
    gpa_scale: Optional[str] = "100"  # خيارات مثل: "100", "4.0", "5.0"


# Schema المرجع للاستجابة (Response)
class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    experiences: List[WorkExperienceResponse] = []
    languages: List[LanguageResponse] = []

    class Config:
        from_attributes = True