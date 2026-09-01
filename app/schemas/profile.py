from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field
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


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


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
