from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.models.profile import Profile, Experience

from app.schemas.profile import (
    PersonalInfo, AcademicInfo, GPA, Documents, UploadedFile, UploadStatus, UserProfile,
    Gender,
    FieldOfStudy,
    AcademicLevel,
    GPAScale,
    calculate_profile_completion,
    SkillsAndLanguages,
    SkillsAndLanguagesSuggestions,
    ExperienceCreate, ExperienceUpdate, ExperienceResponse, PreferencesUpdate, PreferencesResponse,
    LanguageItem, PassportAvailability
)

router = APIRouter(
    prefix="/profile",
    tags=["Profile"]
)

# ==========================================
# GET /profile/personal-info
# ==========================================
@router.get("/personal-info", response_model=PersonalInfo)
def get_personal_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found."
        )

    return PersonalInfo(
        first_name=profile.first_name or "",
        last_name=profile.last_name or "",
        email=current_user.email,
        phone_number=profile.phone_number or "",
        gender=profile.gender,
        birth_date=profile.birth_date,
        nationality=profile.nationality or "",
        country_of_residence=profile.country_of_residence or "",
        city=profile.city,
        financial_status=profile.financial_status,
        id_number=profile.id_number if profile else None,
        passport_status=profile.passport_status
    )


# ==========================================
# PUT /profile/personal-info
# ==========================================
@router.put("/personal-info", response_model=PersonalInfo)
def update_personal_info(
    data: PersonalInfo,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.full_name = f"{data.first_name} {data.last_name}".strip()
    profile.first_name = data.first_name
    profile.last_name = data.last_name
    profile.phone_number = data.phone_number
    profile.gender = data.gender
    profile.birth_date = data.birth_date
    profile.nationality = data.nationality
    profile.country_of_residence = data.country_of_residence
    profile.city = data.city
    profile.financial_status = data.financial_status
    profile.id_number = data.id_number
    profile.passport_status = data.passport_status

    db.commit()
    db.refresh(profile)

    return PersonalInfo(
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=current_user.email,
        phone_number=profile.phone_number,
        gender=profile.gender,
        birth_date=profile.birth_date,
        nationality=profile.nationality,
        country_of_residence=profile.country_of_residence,
        city=profile.city,
        financial_status=profile.financial_status,
        id_number=profile.id_number,
        passport_status=profile.passport_status
    )

# ==========================================
# GET /profile/academic-info
# ==========================================
@router.get("/academic-info", response_model=AcademicInfo)
def get_academic_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile or not profile.field_of_study:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academic information not found."
        )

    return AcademicInfo(
        field_of_study=profile.field_of_study,
        academic_level=profile.academic_level,
        gpa=GPA(value=profile.gpa_value, scale=profile.gpa_scale),
        institution=profile.institution or "",
        current_study_language=profile.current_study_language or [],
        expected_graduation_year=profile.expected_graduation_year
    )


# ==========================================
# PUT /profile/academic-info
# ==========================================
@router.put("/academic-info", response_model=AcademicInfo)
def update_academic_info(
    data: AcademicInfo,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.field_of_study = data.field_of_study
    profile.academic_level = data.academic_level
    profile.gpa_value = data.gpa.value
    profile.gpa_scale = data.gpa.scale
    profile.institution = data.institution
    profile.current_study_language = data.current_study_language
    profile.expected_graduation_year = data.expected_graduation_year

    db.commit()
    db.refresh(profile)

    return AcademicInfo(
        field_of_study=profile.field_of_study,
        academic_level=profile.academic_level,
        gpa=GPA(value=profile.gpa_value, scale=profile.gpa_scale),
        institution=profile.institution,
        current_study_language=profile.current_study_language,
        expected_graduation_year=profile.expected_graduation_year
    )

# ==========================================
# 1. Endpoint رفع الملفات الفعلي
# ==========================================
@router.post("/documents/upload", response_model=UploadedFile)
def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    file_content = file.file.read()
    file_size = len(file_content)
    
    fake_file_url = f"https://storage.scholarai.com/uploads/{current_user.id}/{file.filename}"

    return UploadedFile(
        status=UploadStatus.UPLOADED,
        file_url=fake_file_url,
        file_name=file.filename,
        file_type=file.content_type,
        file_size=file_size,
        uploaded_at=datetime.utcnow()
    )


# ==========================================
# 2. GET /profile/documents
# ==========================================
@router.get("/documents", response_model=Documents)
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    
    if not profile or not profile.documents_data:
        return Documents()

    return Documents(**profile.documents_data)


# ==========================================
# 3. PUT /profile/documents
# ==========================================
@router.put("/documents", response_model=Documents)
def update_documents(
    data: Documents,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.documents_data = data.model_dump(mode="json", by_alias=True)

    db.commit()
    db.refresh(profile)

    return data


# ==========================================
# 1. GET /profile/skills-and-languages
# ==========================================
@router.get("/skills-and-languages", response_model=SkillsAndLanguages)
def get_skills_and_languages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        return SkillsAndLanguages()

    return SkillsAndLanguages(
        languages=profile.languages_data or [],
        skills=profile.skills_data or []
    )


# ==========================================
# 2. GET /profile/skills-and-languages/suggestions
# ==========================================
@router.get("/skills-and-languages/suggestions", response_model=SkillsAndLanguagesSuggestions)
def get_suggestions():
    return SkillsAndLanguagesSuggestions(
        popular_languages=[
            "العربية", "الإنجليزيّة", "التركية", "الفرنسية", "الإسبانية", "الألمانية"
        ],
        suggested_skills_by_category={
            "تقنية": ["JavaScript", "Python", "React", "Node.js", "Docker", "Power BI", "Data Analysis"],
            "تواصل": ["التواصل الفعال", "إدارة الوقت", "العمل الجماعي", "القيادة"],
            "أخرى": ["إدارة المشاريع", "حل المشكلات", "التفكير النقدي"]
        }
    )


# ==========================================
# 3. PUT /profile/skills-and-languages
# ==========================================
@router.put("/skills-and-languages", response_model=SkillsAndLanguages)
def update_skills_and_languages(
    data: SkillsAndLanguages,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.languages_data = [lang.model_dump(mode="json", by_alias=True) for lang in data.languages]
    profile.skills_data = data.skills

    db.commit()
    db.refresh(profile)

    return data


# ==========================================
# 1. GET /profile/experiences
# ==========================================
@router.get("/experiences", response_model=List[ExperienceResponse])
def get_experiences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        return []
    
    return db.query(Experience).filter(Experience.profile_id == profile.id).all()


# ==========================================
# 2. POST /profile/experiences
# ==========================================
@router.post("/experiences", response_model=ExperienceResponse, status_code=status.HTTP_201_CREATED)
def create_experience(
    data: ExperienceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    new_exp = Experience(
        profile_id=profile.id,
        experience_type=data.experience_type,
        title=data.title,
        organization=data.organization,
        start_date=data.start_date,
        end_date=None if data.is_current else data.end_date,
        is_current=data.is_current,
        description=data.description
    )
    
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    return new_exp


# ==========================================
# 3. PUT /profile/experiences/{exp_id}
# ==========================================
@router.put("/experiences/{exp_id}", response_model=ExperienceResponse)
def update_experience(
    exp_id: int,
    data: ExperienceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    exp = db.query(Experience).filter(Experience.id == exp_id, Experience.profile_id == profile.id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experience item not found")

    exp.experience_type = data.experience_type
    exp.title = data.title
    exp.organization = data.organization
    exp.start_date = data.start_date
    exp.end_date = None if data.is_current else data.end_date
    exp.is_current = data.is_current
    exp.description = data.description

    db.commit()
    db.refresh(exp)
    return exp


# ==========================================
# 4. DELETE /profile/experiences/{exp_id}
# ==========================================
@router.delete("/experiences/{exp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    exp = db.query(Experience).filter(Experience.id == exp_id, Experience.profile_id == profile.id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experience item not found")

    db.delete(exp)
    db.commit()
    return None


# ==========================================
# 1. GET /profile/preferences
# ==========================================
@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    
    if not profile:
        return PreferencesResponse()

    return PreferencesResponse(
        desired_degree_level=profile.desired_degree_level,
        funding_type=profile.funding_type,
        preferred_fields_of_study=profile.preferred_fields_of_study or [],
        preferred_countries=profile.preferred_countries or [],
        is_profile_completed=profile.is_completed
    )


# ==========================================
# 2. PUT /profile/preferences
# ==========================================
@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    data: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.desired_degree_level = data.desired_degree_level
    profile.funding_type = data.funding_type
    profile.preferred_fields_of_study = data.preferred_fields_of_study
    profile.preferred_countries = data.preferred_countries
    profile.is_completed = True

    db.commit()
    db.refresh(profile)

    return PreferencesResponse(
        desired_degree_level=profile.desired_degree_level,
        funding_type=profile.funding_type,
        preferred_fields_of_study=profile.preferred_fields_of_study,
        preferred_countries=profile.preferred_countries,
        is_profile_completed=profile.is_completed
    )


# ==========================================
# GET /profile (البروفايل الكامل)
# ==========================================
@router.get("", response_model=UserProfile)
def get_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    personal_info = PersonalInfo(
        first_name=profile.first_name if profile else "",
        last_name=profile.last_name if profile else "",
        email=current_user.email,
        phone_number=profile.phone_number if profile else "",
        gender=profile.gender if profile and profile.gender else Gender.MALE,
        birth_date=profile.birth_date if profile and profile.birth_date else date.today(),
        nationality=profile.nationality if profile else "",
        country_of_residence=profile.country_of_residence if profile else "",
        city=profile.city if profile else None,
        financial_status=profile.financial_status if profile else None,
        id_number=profile.id_number if profile and profile.id_number else "",
        passport_status=(
            profile.passport_status
            if profile and profile.passport_status
            else PassportAvailability.NOT_AVAILABLE
        )
    )

    academic_info = AcademicInfo(
        field_of_study=profile.field_of_study if profile and profile.field_of_study else FieldOfStudy.OTHER,
        academic_level=profile.academic_level if profile and profile.academic_level else AcademicLevel.BACHELOR,
        gpa=GPA(
            value=profile.gpa_value if profile and profile.gpa_value else 0.0,
            scale=profile.gpa_scale if profile and profile.gpa_scale else GPAScale.SCALE_100
        ),
        institution=profile.institution if profile else "",
        current_study_language=profile.current_study_language if profile and profile.current_study_language else [],
        expected_graduation_year=profile.expected_graduation_year if profile and profile.expected_graduation_year else 2026
    )

    documents_data = Documents.model_validate(profile.documents_data) if (profile and profile.documents_data) else Documents()
    languages_list = [LanguageItem(**lang) for lang in profile.languages_data] if (profile and profile.languages_data) else []
    skills_and_languages = SkillsAndLanguages(
        languages=languages_list,
        skills=profile.skills_data or []
    ) 

    experiences_list = []
    if profile:
        experiences_db = db.query(Experience).filter(Experience.profile_id == profile.id).all()
        experiences_list = [ExperienceResponse.model_validate(exp) for exp in experiences_db]

    preferences_data = PreferencesResponse(
        desired_degree_level=profile.desired_degree_level if profile else None,
        funding_type=profile.funding_type if profile else None,
        preferred_fields_of_study=profile.preferred_fields_of_study if profile else [],
        preferred_countries=profile.preferred_countries if profile else [],
        is_profile_completed=profile.is_completed if profile else False
    )

    completion_percentage = calculate_profile_completion(
        personal_info,
        academic_info,
        documents_data,
        skills_and_languages,
        experiences_list,
        preferences_data
    )

    return UserProfile(
        personal_info=personal_info,
        academic_info=academic_info,
        documents=documents_data,
        skills_and_languages=skills_and_languages,
        experiences=experiences_list,
        preferences=preferences_data,
        profile_completion_percentage=completion_percentage
    )
