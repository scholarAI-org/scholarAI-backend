from datetime import date, datetime
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationError,
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


class HighSchoolTrack(str, Enum):
    SCIENTIFIC = "SCIENTIFIC"
    LITERARY = "LITERARY"
    SHARIA = "SHARIA"
    INDUSTRIAL = "INDUSTRIAL"


class StudyStatus(str, Enum):
    CURRENTLY_STUDYING = "CURRENTLY_STUDYING"
    GRADUATED = "GRADUATED"


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
    value: float = Field(..., ge=0.0, strict=True, allow_inf_nan=False)
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


AcademicName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
OpenAlexSubfieldId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=255,
        pattern=r"^https://openalex\.org/subfields/[1-9][0-9]*$",
    ),
]
OpenAlexTopicId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=255,
        pattern=r"^https://openalex\.org/T[1-9][0-9]*$",
    ),
]


class AcademicInfoUpdate(BaseModel):
    """Complete section replacement; legacy reads use AcademicInfoResponse."""

    academic_level: AcademicLevel
    field_of_study: AcademicName = Field(
        description=(
            "TAWJIHI: SCIENTIFIC, LITERARY, SHARIA or INDUSTRIAL. "
            "Otherwise an OpenAlex Subfield display name."
        )
    )
    field_of_study_openalex_id: OpenAlexSubfieldId | None = Field(
        default=None, description="Required for BACHELOR/MASTER/PHD; must be null for TAWJIHI."
    )
    institution: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None
    ) = None
    gpa: GPA
    current_study_language: list[AcademicName] = Field(default_factory=list)
    expected_graduation_year: int = Field(
        strict=True,
        description="Inclusive range: runtime current year minus 50 through current year plus 10.",
    )
    study_status: StudyStatus
    target_field_of_study: AcademicName
    target_field_of_study_openalex_id: OpenAlexSubfieldId | None = Field(
        default=None,
        description="Selected OpenAlex Subfield ID; nullable during frontend migration.",
    )
    research_specialization: AcademicName | None = None
    research_specialization_openalex_id: OpenAlexTopicId | None = None

    @field_validator("expected_graduation_year")
    @classmethod
    def validate_graduation_year(cls, value: int) -> int:
        current_year = date.today().year  # noqa: DTZ011 -- contract uses the server's runtime calendar year
        if not current_year - 50 <= value <= current_year + 10:
            raise ValueError(
                f"Graduation year must be between {current_year - 50} and {current_year + 10}."
            )
        return value

    @model_validator(mode="after")
    def validate_academic_fields(self) -> "AcademicInfoUpdate":
        if self.academic_level == AcademicLevel.TAWJIHI:
            if self.field_of_study not in {track.value for track in HighSchoolTrack}:
                raise ValueError(
                    "TAWJIHI field_of_study must be SCIENTIFIC, LITERARY, SHARIA or INDUSTRIAL."
                )
            if self.field_of_study_openalex_id is not None:
                raise ValueError("TAWJIHI field_of_study_openalex_id must be null.")
        elif self.field_of_study_openalex_id is None:
            raise ValueError("field_of_study_openalex_id is required for BACHELOR, MASTER and PHD.")

        has_name = self.research_specialization is not None
        has_id = self.research_specialization_openalex_id is not None
        if self.academic_level != AcademicLevel.PHD and (has_name or has_id):
            raise ValueError("Research specialization is only valid for PHD.")
        if has_name != has_id:
            raise ValueError(
                "Research specialization name and OpenAlex Topic ID must be provided together."
            )
        return self

    model_config = ConfigDict(extra="forbid")


class AcademicInfoResponse(BaseModel):
    """Nullable legacy/draft data; no inferred status, taxonomy IDs or target field.

    Runtime year bounds and new required-field rules apply on writes only, so
    previously saved profiles remain readable as the contract and date change.
    """

    academic_level: AcademicLevel | None = None
    field_of_study: str | None = None
    field_of_study_openalex_id: str | None = None
    institution: str | None = None
    gpa: GPA | None = None
    current_study_language: list[str] = Field(default_factory=list)
    expected_graduation_year: int | None = None
    study_status: StudyStatus | None = None
    target_field_of_study: str | None = None
    target_field_of_study_openalex_id: str | None = None
    research_specialization: str | None = None
    research_specialization_openalex_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UploadedFile(BaseModel):
    """Stable document metadata. object_key is loaded from storage but never serialized."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: Optional[str] = None
    document_type: Optional[str] = None
    status: UploadStatus = UploadStatus.NOT_UPLOADED
    file_name: Optional[str] = None
    content_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("content_type", "file_type"),
    )
    file_size: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    object_key: Optional[str] = Field(default=None, exclude=True)


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
    academic_info: Optional[AcademicInfoResponse] = None
    documents: Optional[Documents] = None
    skills_and_languages: Optional[SkillsAndLanguages] = None
    experiences: List[ExperienceResponse] = []
    preferences: Optional[PreferencesResponse] = None
    avatar_url: Optional[str] = None
    profile_completion_percentage: float = 0.0

    model_config = ConfigDict(from_attributes=True)


def calculate_profile_completion(
    personal_info: Optional[PersonalInfo],
    academic_info: Optional[AcademicInfoResponse],
    documents: Documents,
    skills_and_languages: SkillsAndLanguages,
    experiences: List[ExperienceResponse],
    preferences: PreferencesResponse,
) -> float:
    """
    حساب نسبة اكتمال الملف الشخصي بناءً على الحقول الإلزامية فقط.
    الأقسام الإلزامية الأساسية:
    1. المعلومات الشخصية الإلزامية (الاسم، الإيميل، تاريخ الميلاد، الجنس، الجنسية، بلد الإقامة).
    2. المعلومات الأكاديمية المطلوبة وفق عقد الحفظ، دون اشتراط المؤسسة.
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
    if is_academic_info_complete(academic_info):
        completed_sections += 1

    # 3. التفضيلات الإلزامية
    is_preferences_complete = all([
        preferences.desired_degree_level,
        preferences.funding_type,
    ])
    if is_preferences_complete:
        completed_sections += 1

    return round((completed_sections / total_sections) * 100, 2)


def is_academic_info_complete(academic_info: AcademicInfoResponse | None) -> bool:
    if academic_info is None:
        return False
    try:
        AcademicInfoUpdate.model_validate(academic_info.model_dump())
    except ValidationError:
        return False
    return True
