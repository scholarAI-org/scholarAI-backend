from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated, Optional, List
from datetime import date
from pydantic import field_validator

# نص إلزامي: لا يقبل قيمة فارغة أو مسافات فقط.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. Schemas الرئيسي للبروفايل (Profile)
# ==========================================
class ProfileBase(BaseModel):

    # Personal Info
    full_name: RequiredText
    gender: RequiredText
    marital_status: Optional[str] = None
    date_of_birth: date
    country_of_birth: Optional[str] = None
    nationality: RequiredText
    country_of_residence: RequiredText
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
    country: RequiredText
    city: RequiredText
    address: Optional[str] = None
    phone_number: RequiredText

    # Academic Background
    degree: RequiredText
    major: RequiredText
    institution_name: RequiredText
    graduation_year: int
    gpa: float
    gpa_scale: str = "100"


# ==========================================
# 4. إنشاء البروفايل لأول مرة
# ==========================================
class ProfileCreate(ProfileBase):
    experiences: List[WorkExperienceCreate] = Field(default_factory=list)
    languages: List[LanguageCreate] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Ahmed Ali",
                "gender": "male",
                "date_of_birth": "2000-01-15",
                "nationality": "Jordanian",
                "country_of_residence": "Jordan",
                "country": "Jordan",
                "city": "Amman",
                "phone_number": "+962790000000",
                "degree": "Bachelor",
                "major": "Computer Science",
                "institution_name": "University of Jordan",
                "graduation_year": 2024,
                "gpa": 84.5,
                "gpa_scale": "100",
                "experiences": [],
                "languages": [],
            }
        }
    )

    @field_validator(
        "full_name", "gender", "nationality", "country_of_residence",
        "country", "city", "phone_number", "degree", "major",
        "institution_name"
    )
    @classmethod
    def reject_placeholder_values(cls, value: str) -> str:
        forbidden = {"string", "select", "choose", "اختر", "غير محدد"}

        if value.strip().casefold() in forbidden:
            raise ValueError("يرجى إدخال قيمة حقيقية، وليس قيمة افتراضية")

        return value


# ==========================================
# 5. تحديث البروفايل
# جميع الحقول اختيارية حتى نسمح بالتحديث الجزئي
# ==========================================
class ProfileUpdate(BaseModel):

    # Personal Info
    full_name: Optional[RequiredText] = None
    gender: Optional[RequiredText] = None
    marital_status: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_birth: Optional[str] = None
    nationality: Optional[RequiredText] = None
    country_of_residence: Optional[RequiredText] = None
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
    country: Optional[RequiredText] = None
    city: Optional[RequiredText] = None
    address: Optional[str] = None
    phone_number: Optional[RequiredText] = None

    # Academic Background
    degree: Optional[RequiredText] = None
    major: Optional[RequiredText] = None
    institution_name: Optional[RequiredText] = None
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None
    gpa_scale: Optional[str] = None

    @field_validator(
        "full_name", "gender", "nationality", "country_of_residence",
        "country", "city", "phone_number", "degree", "major",
        "institution_name"
    )
    @classmethod
    def reject_placeholder_values(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        forbidden = {"string", "select", "choose", "اختر", "غير محدد"}
        if value.casefold() in forbidden:
            raise ValueError("يرجى إدخال قيمة حقيقية، وليس قيمة افتراضية")

        return value


# ==========================================
# 6. Profile Response
# ==========================================
class ProfileResponse(ProfileBase):
    id: int
    user_id: int

    experiences: List[WorkExperienceResponse] = Field(default_factory=list)
    languages: List[LanguageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
