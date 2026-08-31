from datetime import date, datetime
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic.alias_generators import to_camel

from app.models.profile import (
    AcademicLevel,
    DesiredDegreeLevel,
    ExperienceType,
    FieldOfStudy,
    FinancialStatus,
    FundingType,
    Gender,
    GPAScale,
    PassportAvailability,
)

# نوع نصي يتأكد من أن النصوص المحشوة ليست فارغة
RequiredText = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UploadStatus(str, Enum):
    NOT_UPLOADED = "NOT_UPLOADED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class LanguageProficiency(str, Enum):
    NATIVE = "NATIVE"
    ADVANCED_C1_C2 = "ADVANCED"
    INTERMEDIATE_B1_B2 = "INTERMEDIATE"
    BEGINNER_A1_A2 = "BEGINNER"


class GPA(CamelModel):
    value: float
    scale: GPAScale


class PersonalInfo(CamelModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    gender: Gender
    birth_date: date
    nationality: str
    country_of_residence: str
    city: Optional[str] = None
    financial_status: Optional[FinancialStatus] = None
    id_number: str
    passport_status: PassportAvailability = PassportAvailability.NOT_AVAILABLE


class AcademicInfo(CamelModel):
    field_of_study: FieldOfStudy
    academic_level: AcademicLevel
    gpa: GPA
    institution: str
    current_study_language: List[str]
    expected_graduation_year: int


class UploadedFile(CamelModel):
    status: UploadStatus = UploadStatus.NOT_UPLOADED
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: Optional[datetime] = None


class RecommendationLetter(UploadedFile):
    id: str


class Documents(CamelModel):
    cv: UploadedFile = Field(default_factory=UploadedFile)
    motivation_letter: UploadedFile = Field(default_factory=UploadedFile)
    bachelor_certificate: UploadedFile = Field(default_factory=UploadedFile)
    official_transcript: UploadedFile = Field(default_factory=UploadedFile)
    language_certificate: UploadedFile = Field(default_factory=UploadedFile)
    recommendation_letters: List[RecommendationLetter] = Field(default_factory=list)


class LanguageItem(CamelModel):
    language_name: str
    proficiency_level: LanguageProficiency


class LanguageCreate(BaseModel):
    language_name: str
    proficiency_level: LanguageProficiency


class LanguageResponse(LanguageCreate):
    id: int
    profile_id: int
    model_config = ConfigDict(from_attributes=True)


class SkillsAndLanguages(CamelModel):
    languages: List[LanguageItem] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)


class ExperienceBase(CamelModel):
    experience_type: ExperienceType
    title: str
    organization: str
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None


class ExperienceCreate(ExperienceBase):
    pass


class ExperienceUpdate(ExperienceBase):
    pass


class ExperienceResponse(ExperienceBase):
    id: int
    profile_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class WorkExperienceCreate(ExperienceBase):
    pass


class WorkExperienceResponse(ExperienceBase):
    id: int
    profile_id: int
    model_config = ConfigDict(from_attributes=True)


class ProfileBase(BaseModel):
    full_name: RequiredText
    gender: RequiredText
    marital_status: Optional[str] = None
    date_of_birth: date
    country_of_birth: Optional[str] = None
    nationality: RequiredText
    country_of_residence: RequiredText
    id_type: Optional[str] = None
    id_number: Optional[str] = None

    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    father_income: Optional[float] = 0.0
    mother_income: Optional[float] = 0.0
    num_of_siblings: Optional[int] = 0
    currency: Optional[str] = "USD"

    country: RequiredText
    city: RequiredText
    address: Optional[str] = None
    phone_number: RequiredText

    degree: RequiredText
    major: RequiredText
    institution_name: RequiredText
    graduation_year: int
    gpa: float
    gpa_scale: str = "100"


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
        "full_name",
        "gender",
        "nationality",
        "country_of_residence",
        "country",
        "city",
        "phone_number",
        "degree",
        "major",
        "institution_name",
    )
    @classmethod
    def reject_placeholder_values(cls, value: str) -> str:
        forbidden = {"string", "select", "choose", "اختر", "غير محدد"}
        if value.strip().casefold() in forbidden:
            raise ValueError("يرجى إدخال قيمة حقيقية، وليس قيمة افتراضية")
        return value


class ProfileUpdate(BaseModel):
    full_name: Optional[RequiredText] = None
    gender: Optional[RequiredText] = None
    marital_status: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_birth: Optional[str] = None
    nationality: Optional[RequiredText] = None
    country_of_residence: Optional[RequiredText] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None

    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    father_income: Optional[float] = None
    mother_income: Optional[float] = None
    num_of_siblings: Optional[int] = None
    currency: Optional[str] = None

    country: Optional[RequiredText] = None
    city: Optional[RequiredText] = None
    address: Optional[str] = None
    phone_number: Optional[RequiredText] = None

    degree: Optional[RequiredText] = None
    major: Optional[RequiredText] = None
    institution_name: Optional[RequiredText] = None
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None
    gpa_scale: Optional[str] = None

    @field_validator(
        "full_name",
        "gender",
        "nationality",
        "country_of_residence",
        "country",
        "city",
        "phone_number",
        "degree",
        "major",
        "institution_name",
    )
    @classmethod
    def reject_placeholder_values(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        forbidden = {"string", "select", "choose", "اختر", "غير محدد"}
        if value.strip().casefold() in forbidden:
            raise ValueError("يرجى إدخال قيمة حقيقية، وليس قيمة افتراضية")
        return value


class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    experiences: List[WorkExperienceResponse] = Field(default_factory=list)
    languages: List[LanguageResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class SkillsAndLanguagesSuggestions(CamelModel):
    popular_languages: List[str]
    suggested_skills_by_category: Dict[str, List[str]]


class PreferencesBase(CamelModel):
    desired_degree_level: Optional[DesiredDegreeLevel] = None
    funding_type: Optional[FundingType] = None
    preferred_fields_of_study: List[str] = Field(default_factory=list)
    preferred_countries: List[str] = Field(default_factory=list)


class PreferencesUpdate(PreferencesBase):
    pass


class PreferencesResponse(PreferencesBase):
    is_profile_completed: bool = False


class UserProfile(CamelModel):
    personal_info: PersonalInfo
    academic_info: AcademicInfo
    documents: Documents
    skills_and_languages: SkillsAndLanguages
    experiences: List[ExperienceResponse] = Field(default_factory=list)
    preferences: PreferencesResponse
    profile_completion_percentage: int


def calculate_profile_completion(
    personal: PersonalInfo,
    academic: AcademicInfo,
    documents: Documents,
    skills_lang: SkillsAndLanguages,
    experiences: List[ExperienceResponse],
    preferences: PreferencesResponse,
) -> int:
    score = 0

    if personal.first_name and personal.last_name and personal.phone_number and personal.nationality:
        score += 20
    if academic.institution and academic.gpa.value > 0:
        score += 20

    uploaded_documents = (
        documents.cv,
        documents.motivation_letter,
        documents.bachelor_certificate,
        documents.official_transcript,
        documents.language_certificate,
    )
    if any(document.status == UploadStatus.UPLOADED for document in uploaded_documents) or documents.recommendation_letters:
        score += 20
    if skills_lang.languages or skills_lang.skills:
        score += 15
    if experiences:
        score += 15
    if preferences.desired_degree_level and preferences.funding_type:
        score += 10

    return score
