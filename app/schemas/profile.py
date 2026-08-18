from pydantic import BaseModel, Field
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
# 2. Schemas الخاص ببيانات العمل (Work Experience)
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
    gender: str
    marital_status: Optional[str] = None
    date_of_birth: date
    country_of_birth: Optional[str] = None
    nationality: str
    country_of_residence: str
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
    country: str
    city: str
    address: Optional[str] = None
    phone_number: str

    # Academic Background
    degree: str
    major: str
    institution_name: str
    graduation_year: int
    gpa: float
    gpa_scale: str = "100"


# ==========================================
# 4. إنشاء البروفايل لأول مرة
# ==========================================
class ProfileCreate(ProfileBase):
    experiences: List[WorkExperienceCreate] = Field(default_factory=list)
    languages: List[LanguageCreate] = Field(default_factory=list)


# ==========================================
# 5. تحديث البروفايل
# جميع الحقول اختيارية حتى نسمح بالتحديث الجزئي
# ==========================================
class ProfileUpdate(BaseModel):

    # Personal Info
    full_name: Optional[str] = None
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
    father_income: Optional[float] = None
    mother_income: Optional[float] = None
    num_of_siblings: Optional[int] = None
    currency: Optional[str] = None

    # Contact Info
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
    gpa_scale: Optional[str] = None


# ==========================================
# 6. Profile Response
# ==========================================
class ProfileResponse(ProfileBase):
    id: int
    user_id: int

    experiences: List[WorkExperienceResponse] = Field(default_factory=list)
    languages: List[LanguageResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True
