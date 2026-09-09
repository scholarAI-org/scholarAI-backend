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
    financial_status: FinancialStatus

    # اختياري مفروض عليه Validation في حال وجوده
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{7,14}$")
    city: Optional[str] = Field(None, max_length=100)
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
    """Nullable legacy/draft academic data; no inferred status or taxonomy IDs.

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
    motivation_letter: UploadedFile = Field(default_factory=UploadedFile)

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
        if not self.is_current and self.end_date is None:
            raise ValueError("تاريخ النهاية إجباري عندما لا تكون الخبرة مستمرة")
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
CountryCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{2}$", to_upper=True),
]


class PreferencesState(BaseModel):
    """Validate the merged preference state, including partial/draft profiles."""

    desired_degree_level: DesiredDegreeLevel | None = None
    target_field_of_study: AcademicName | None = None
    target_field_of_study_openalex_id: OpenAlexSubfieldId | None = Field(
        default=None,
        description="Optional OpenAlex Subfield ID. The same taxonomy is valid for all degrees.",
    )
    detailed_specialization: AcademicName | None = None
    funding_type: FundingType | None = None
    preferred_countries: list[CountryCode] = Field(default_factory=list)
    open_to_all_countries: bool = False

    @field_validator("preferred_countries", mode="before")
    @classmethod
    def default_countries(cls, value):
        return value if value is not None else []

    @model_validator(mode="after")
    def validate_preferences(self) -> "PreferencesState":
        if self.target_field_of_study_openalex_id and not self.target_field_of_study:
            raise ValueError("target_field_of_study is required with its OpenAlex ID.")
        if self.desired_degree_level == DesiredDegreeLevel.PHD:
            if not self.detailed_specialization:
                raise ValueError("detailed_specialization is required for PHD.")
        else:
            self.detailed_specialization = None
        if self.open_to_all_countries:
            self.preferred_countries = []
        return self

    model_config = ConfigDict(extra="forbid")


class Preferences(PreferencesState):
    desired_degree_level: DesiredDegreeLevel
    funding_type: FundingType


class PreferencesUpdate(BaseModel):
    """Partial update; degree-dependent rules validate the merged stored state."""

    desired_degree_level: Optional[DesiredDegreeLevel] = None
    funding_type: Optional[FundingType] = None
    target_field_of_study: AcademicName | None = Field(
        default=None, description="One intended OpenAlex field; shared taxonomy for all degrees."
    )
    target_field_of_study_openalex_id: OpenAlexSubfieldId | None = Field(
        default=None, description="Optional OpenAlex Subfield ID for the intended field."
    )
    detailed_specialization: AcademicName | None = Field(
        default=None, description="Required when the resulting degree is PHD; otherwise cleared."
    )
    preferred_countries: list[CountryCode] | None = None
    open_to_all_countries: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class PreferencesResponse(BaseModel):
    """Response schema — جميع الحقول Optional لأن المستخدم الجديد لم يُكمل تفضيلاته بعد."""
    desired_degree_level: Optional[DesiredDegreeLevel] = None
    funding_type: Optional[FundingType] = None
    target_field_of_study: str | None = None
    target_field_of_study_openalex_id: str | None = None
    detailed_specialization: str | None = None
    preferred_countries: List[str] = []
    open_to_all_countries: bool = False
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
    has_experience: Optional[bool] = None
    preferences: Optional[PreferencesResponse] = None
    avatar_url: Optional[str] = None
    profile_completion_percentage: float = 0.0

    model_config = ConfigDict(from_attributes=True)


def _is_english_language(name: str) -> bool:
    clean = name.strip().lower()
    return clean in ["english", "en"] or any(k in clean for k in ["انجليز", "إنجليز"])


def calculate_profile_completion(
    personal_info: Optional[PersonalInfo],
    academic_info: Optional[AcademicInfoResponse],
    documents: Documents,
    skills_and_languages: SkillsAndLanguages,
    experiences: List[ExperienceResponse],
    preferences: PreferencesResponse,
    has_experience: Optional[bool] = None,
    open_to_all_countries: Optional[bool] = None,
) -> float:
    """
    حساب نسبة اكتمال الملف الشخصي بالأوزان الدقيقة (100%):
    1. Personal Information (22%):
       - First name: 1%
       - Last name: 1%
       - Date of birth: 4%
       - Nationality: 5%
       - Country of residence: 4%
       - Gender: 1%
       - Financial situation: 2%
       - Passport number: 4%
    2. Academic Information (22%):
       - Current Education level: 6%
       - Current/previous field of study: 6%
       - GPA / academic average: 7%
       - Graduation / expected graduation year: 3%
    3. Scholarship Preferences (28%):
       - Target degree: 8%
       - Target field: 8%
       - Preferred countries OR Open to all: 6%
       - Funding preference: 6%
    4. Languages (10%):
       - English proficiency: 7%
       - Other language information: 3%
    5. Experience & Activities (5%):
       - If No: 5%
       - If Yes and at least 1 valid experience: 5%
       - Otherwise: 0%
    6. Skills (5%):
       - 1 skill: 2%
       - 2 skills: 4%
       - 3+ skills: 5%
    7. Documents (8%):
       - CV: 2%
       - Motivation letter: 2%
       - Language certificate (english_test): 3%
       - Degree certificate (graduation_certificate): 1%
    """
    score = 0.0

    # 1. Personal Information (22%)
    if personal_info is not None:
        if personal_info.first_name:
            score += 1.0
        if personal_info.last_name:
            score += 1.0
        if personal_info.birth_date:
            score += 4.0
        if personal_info.nationality:
            score += 5.0
        if personal_info.country_of_residence:
            score += 4.0
        if personal_info.gender:
            score += 1.0
        if personal_info.financial_status:
            score += 2.0
        if personal_info.passport_number:
            score += 4.0

    # 2. Academic Information (22%): honor the required OpenAlex contract.
    if is_academic_info_complete(academic_info):
        if academic_info.academic_level:
            score += 6.0
        if academic_info.field_of_study:
            score += 6.0
        if academic_info.gpa and academic_info.gpa.value is not None:
            score += 7.0
        if academic_info.expected_graduation_year is not None:
            score += 3.0

    # 3. Scholarship Preferences (28%)
    if preferences is not None:
        if preferences.desired_degree_level:
            score += 8.0
        if preferences.target_field_of_study and preferences.target_field_of_study.strip():
            score += 8.0
        # Preferred countries OR Open to all: 6%
        is_open_to_all = (
            getattr(preferences, "open_to_all_countries", False)
            or bool(open_to_all_countries)
            or any(
                str(c).strip().upper() in ["ALL", "ANY", "OPEN_TO_ALL"]
                for c in (preferences.preferred_countries or [])
            )
        )
        has_countries = bool(preferences.preferred_countries and len(preferences.preferred_countries) > 0)
        if has_countries or is_open_to_all:
            score += 6.0
        if preferences.funding_type:
            score += 6.0

    # 4. Languages (10%)
    has_english = False
    has_other_language = False
    if skills_and_languages and skills_and_languages.languages:
        for lang in skills_and_languages.languages:
            if _is_english_language(lang.name):
                has_english = True
            else:
                has_other_language = True

    # Also check if english_test document is uploaded for English proficiency
    if documents and getattr(documents, "english_test", None):
        if documents.english_test.status == UploadStatus.UPLOADED:
            has_english = True

    if has_english:
        score += 7.0
    if has_other_language:
        score += 3.0

    # 5. Experience & Activities (5%)
    if has_experience is False:
        score += 5.0
    elif len(experiences) >= 1:
        score += 5.0

    # 6. Skills (5%)
    skills_count = len(skills_and_languages.skills) if (skills_and_languages and skills_and_languages.skills) else 0
    if skills_count >= 3:
        score += 5.0
    elif skills_count == 2:
        score += 4.0
    elif skills_count == 1:
        score += 2.0

    # 7. Documents (8%)
    if documents:
        if getattr(documents, "cv", None) and documents.cv.status == UploadStatus.UPLOADED:
            score += 2.0
        if getattr(documents, "motivation_letter", None) and documents.motivation_letter.status == UploadStatus.UPLOADED:
            score += 2.0
        if getattr(documents, "english_test", None) and documents.english_test.status == UploadStatus.UPLOADED:
            score += 3.0
        if getattr(documents, "graduation_certificate", None) and documents.graduation_certificate.status == UploadStatus.UPLOADED:
            score += 1.0

    return round(score, 2)



def is_academic_info_complete(academic_info: AcademicInfoResponse | None) -> bool:
    if academic_info is None:
        return False
    try:
        AcademicInfoUpdate.model_validate(academic_info.model_dump())
    except ValidationError:
        return False
    return True
