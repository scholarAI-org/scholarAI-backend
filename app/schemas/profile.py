from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


# ==========================================
# 1. Enums
# ==========================================
class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class FinancialStatus(str, Enum):
    LIMITED = "LIMITED"
    MODERATE = "MODERATE"
    STABLE = "STABLE"


class AcademicLevel(str, Enum):
    TAWJIHI = "TAWJIHI"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"


class FieldOfStudy(str, Enum):
    SCIENTIFIC = "SCIENTIFIC"
    LITERARY = "LITERARY"
    SHARIA = "SHARIA"
    INDUSTRIAL = "INDUSTRIAL"
    ENTREPRENEURSHIP_BUSINESS = "ENTREPRENEURSHIP_BUSINESS"
    AGRICULTURAL = "AGRICULTURAL"
    HOME_ECONOMICS = "HOME_ECONOMICS"

    ENGINEERING = "ENGINEERING"
    COMPUTER_SCIENCE = "COMPUTER_SCIENCE"
    MEDICINE = "MEDICINE"
    BUSINESS = "BUSINESS"
    ARTS = "ARTS"
    OTHER = "OTHER"


class GPAScale(str, Enum):
    SCALE_4 = "SCALE_4"
    SCALE_5 = "SCALE_5"
    SCALE_10 = "SCALE_10"
    SCALE_100 = "SCALE_100"


class DesiredDegreeLevel(str, Enum):
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"
    DIPLOMA = "DIPLOMA"
    OTHER = "OTHER"


class FundingType(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    SELF = "SELF"
    ANY = "ANY"


class ExperienceType(str, Enum):
    WORK = "WORK"
    VOLUNTEER = "VOLUNTEER"
    RESEARCH = "RESEARCH"
    STUDENT_ACTIVITY = "STUDENT_ACTIVITY"


class UploadStatus(str, Enum):
    NOT_UPLOADED = "NOT_UPLOADED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class LanguageProficiency(str, Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    NATIVE = "NATIVE"


# ==========================================
# 2. Sub-Schemas with Strict Validation Rules
# ==========================================
class PersonalInfo(BaseModel):
    # إجباري
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    birth_date: date
    gender: Gender
    nationality: str = Field(..., min_length=2, max_length=2, description="ISO 2-letter country code, e.g. PS")
    country_of_residence: str = Field(..., min_length=2, max_length=2, description="ISO 2-letter country code")

    # اختياري مفروض عليه Validation في حال وجوده
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{7,14}$")
    city: Optional[str] = Field(None, max_length=100)
    financial_status: Optional[FinancialStatus] = None
    id_number: Optional[str] = Field(None, pattern=r"^\d{9}$", description="Must be exactly 9 digits")
    passport_number: Optional[str] = Field(None, pattern=r"^[A-Z0-9]{6,12}$")

    @field_validator("birth_date")
    @classmethod
    def validate_age(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 15 or age > 80:
            raise ValueError("العمر يجب أن يكون بين 15 و 80 سنة للتقديم على المنح")
        return value

    model_config = ConfigDict(from_attributes=True)


class PersonalInfoUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    gender: Optional[Gender] = None
    nationality: Optional[str] = Field(None, min_length=2, max_length=2)
    country_of_residence: Optional[str] = Field(None, min_length=2, max_length=2)
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{7,14}$")
    city: Optional[str] = Field(None, max_length=100)
    financial_status: Optional[FinancialStatus] = None
    id_number: Optional[str] = Field(None, pattern=r"^\d{9}$")
    passport_number: Optional[str] = Field(None, pattern=r"^[A-Z0-9]{6,12}$")

    @field_validator("birth_date")
    @classmethod
    def validate_age(cls, value: Optional[date]) -> Optional[date]:
        if value is not None:
            today = date.today()
            age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
            if age < 15 or age > 80:
                raise ValueError("العمر يجب أن يكون بين 15 و 80 سنة للتقديم على المنح")
        return value


class GPA(BaseModel):
    value: float = Field(..., ge=0.0)
    scale: GPAScale

    @model_validator(mode="after")
    def validate_gpa_limits(self) -> "GPA":
        limits = {
            GPAScale.SCALE_4: 4.0,
            GPAScale.SCALE_5: 5.0,
            GPAScale.SCALE_10: 10.0,
            GPAScale.SCALE_100: 100.0,
        }
        max_limit = limits.get(self.scale)
        if max_limit and self.value > max_limit:
            raise ValueError(f"قيمة المعدل {self.value} تتجاوز الحد الأقصى للسلم المختار ({max_limit})")
        return self


class AcademicInfo(BaseModel):
    academic_level: AcademicLevel
    field_of_study: FieldOfStudy
    institution: str = Field(..., min_length=2, max_length=255)
    gpa: Optional[GPA] = None

    current_study_language: List[str] = []
    expected_graduation_year: Optional[int] = Field(None, ge=1990, le=2035)

    model_config = ConfigDict(from_attributes=True)


class AcademicInfoUpdate(BaseModel):
    academic_level: Optional[AcademicLevel] = None
    field_of_study: Optional[FieldOfStudy] = None
    institution: Optional[str] = Field(None, min_length=2, max_length=255)
    gpa: Optional[GPA] = None
    current_study_language: Optional[List[str]] = None
    expected_graduation_year: Optional[int] = Field(None, ge=1990, le=2035)


class UploadedFile(BaseModel):
    status: UploadStatus = UploadStatus.NOT_UPLOADED
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: Optional[datetime] = None


class Documents(BaseModel):
    cv: UploadedFile = Field(default_factory=UploadedFile)
    transcript: UploadedFile = Field(default_factory=UploadedFile)
    graduation_certificate: UploadedFile = Field(default_factory=UploadedFile)
    passport: UploadedFile = Field(default_factory=UploadedFile)
    recommendation_letters: List[UploadedFile] = Field(default_factory=list)
    english_test: UploadedFile = Field(default_factory=UploadedFile)

    model_config = ConfigDict(from_attributes=True)


class LanguageItem(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    proficiency: LanguageProficiency


class SkillsAndLanguages(BaseModel):
    languages: List[LanguageItem] = []
    skills: List[str] = []


class SkillsAndLanguagesSuggestions(BaseModel):
    popular_languages: List[str]
    suggested_skills_by_category: Dict[str, List[str]]


# ==========================================
# 3. Experience Schemas
# ==========================================
class Experience(BaseModel):
    experience_type: ExperienceType
    title: str = Field(..., min_length=2, max_length=250)
    organization: str = Field(..., min_length=2, max_length=250)
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "Experience":
        if not self.is_current and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
        return self


class ExperienceCreate(Experience):
    pass


class ExperienceUpdate(BaseModel):
    experience_type: Optional[ExperienceType] = None
    title: Optional[str] = Field(None, min_length=2, max_length=250)
    organization: Optional[str] = Field(None, min_length=2, max_length=250)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: Optional[bool] = None
    description: Optional[str] = None


class ExperienceResponse(Experience):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. Preferences Schemas
# ==========================================
class Preferences(BaseModel):
    desired_degree_level: DesiredDegreeLevel
    funding_type: FundingType

    preferred_fields_of_study: List[str] = []
    preferred_countries: List[str] = []


class PreferencesUpdate(BaseModel):
    desired_degree_level: Optional[DesiredDegreeLevel] = None
    funding_type: Optional[FundingType] = None
    preferred_fields_of_study: Optional[List[str]] = None
    preferred_countries: Optional[List[str]] = None


class PreferencesResponse(BaseModel):
    """Response schema — جميع الحقول Optional لأن المستخدم الجديد لم يُكمل تفضيلاته بعد."""
    desired_degree_level: Optional[DesiredDegreeLevel] = None
    funding_type: Optional[FundingType] = None
    preferred_fields_of_study: List[str] = []
    preferred_countries: List[str] = []
    is_profile_completed: bool = False

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. Full Profile Schemas & Completion Logic
# ==========================================
class ProfileUpdate(BaseModel):
    personal_info: Optional[PersonalInfoUpdate] = None
    academic_info: Optional[AcademicInfoUpdate] = None
    documents: Optional[Documents] = None
    skills_and_languages: Optional[SkillsAndLanguages] = None
    preferences: Optional[PreferencesUpdate] = None


class UserProfile(BaseModel):
    id: int
    user_id: int
    personal_info: Optional[PersonalInfo] = None        # None = لم يُكمل المستخدم بياناته بعد
    academic_info: Optional[AcademicInfo] = None        # None = لم يُكمل المستخدم بياناته بعد
    documents: Optional[Documents] = None
    skills_and_languages: Optional[SkillsAndLanguages] = None
    experiences: List[ExperienceResponse] = []
    preferences: Optional[PreferencesResponse] = None
    profile_completion_percentage: float = 0.0

    model_config = ConfigDict(from_attributes=True)


def calculate_profile_completion(
    personal_info: Optional[PersonalInfo],
    academic_info: Optional[AcademicInfo],
    documents: Documents,
    skills_and_languages: SkillsAndLanguages,
    experiences: List[ExperienceResponse],
    preferences: PreferencesResponse,
) -> float:
    """
    حساب نسبة اكتمال الملف الشخصي بناءً على الحقول الإلزامية فقط.
    الأقسام الإلزامية الأساسية:
    1. المعلومات الشخصية الإلزامية (الاسم، الإيميل، تاريخ الميلاد، الجنس، الجنسية، بلد الإقامة).
    2. المعلومات الأكاديمية (المستوى، التخصص، الجامعة/المؤسسة، المعدل).
    3. التفضيلات الإلزامية (المستوى المرغوب، نوع التمويل).
    """
    total_sections = 3
    completed_sections = 0

    # 1. المعلومات الشخصية — None يعني لم تُكتب بعد
    if personal_info is not None:
        is_personal_complete = all([
            personal_info.first_name,
            personal_info.last_name,
            personal_info.email,
            personal_info.birth_date,
            personal_info.gender,
            personal_info.nationality,
            personal_info.country_of_residence,
        ])
        if is_personal_complete:
            completed_sections += 1

    # 2. البيانات الأكاديمية الإلزامية — None يعني لم تُكتب بعد
    if academic_info is not None:
        is_academic_complete = all([
            academic_info.academic_level,
            academic_info.field_of_study,
            academic_info.institution,
            academic_info.gpa and academic_info.gpa.value is not None,
        ])
        if is_academic_complete:
            completed_sections += 1

    # 3. التفضيلات الإلزامية
    is_preferences_complete = all([
        preferences.desired_degree_level,
        preferences.funding_type,
    ])
    if is_preferences_complete:
        completed_sections += 1

    return round((completed_sections / total_sections) * 100, 2)