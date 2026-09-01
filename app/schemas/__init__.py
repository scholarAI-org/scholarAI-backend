from app.schemas.user import UserCreate, UserResponse, Token
from app.schemas.profile import (
    PersonalInfo,
    AcademicInfo,
    Documents,
    SkillsAndLanguages,
    PreferencesResponse,
    UserProfile,          # بدلاً من ProfileResponse
    ProfileUpdate,
    ExperienceCreate,     # بدلاً من WorkExperienceCreate
    ExperienceResponse,   # بدلاً من WorkExperienceResponse
    LanguageItem,         # بدلاً من LanguageCreate / LanguageResponse
)