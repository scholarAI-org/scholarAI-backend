from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.profile import Experience, Profile
from app.models.user import User
from app.schemas.documents import (
    AvatarConfirmResponse,
    AvatarUploadUrlRequest,
    ConfirmUploadRequest,
    DownloadUrlResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.schemas.profile import (
    AcademicInfoResponse,
    AcademicInfoUpdate,
    Documents,
    ExperienceCreate,
    ExperienceResponse,
    ExperienceUpdate,
    LanguageItem,
    PersonalInfo,
    PreferencesResponse,
    PreferencesUpdate,
    SkillsAndLanguages,
    SkillsAndLanguagesSuggestions,
    UploadedFile,
    UserProfile,
    calculate_profile_completion,
)
from app.services.academic_info import academic_info_response
from app.services.avatar import (
    avatar_presigned_url,
    confirm_avatar_upload,
    create_avatar_upload_session,
    delete_avatar,
)
from app.services.documents import (
    confirm_upload_session,
    create_download_url,
    create_upload_session,
    delete_document,
    public_documents,
)
from app.services.s3 import StorageClient, get_s3_storage

router = APIRouter(prefix="/profile", tags=["Profile"])


# ==========================================
# Helper Function: Build Response & Calculate Completion
# ==========================================
def build_full_profile_response(
    profile: Profile,
    user: User,
    storage: Optional[StorageClient] = None,
) -> UserProfile:
    # المعلومات الشخصية — تتعامل مع profile فارغ (مستخدم جديد لم يُكمل بياناته)
    personal_info = None
    if profile.first_name and profile.last_name and profile.birth_date and profile.gender and profile.nationality and profile.country_of_residence:
        personal_info = PersonalInfo(
            first_name=profile.first_name,
            last_name=profile.last_name,
            email=user.email,
            phone_number=profile.phone_number,
            gender=profile.gender,
            birth_date=profile.birth_date,
            nationality=profile.nationality,
            country_of_residence=profile.country_of_residence,
            city=profile.city,
            financial_status=profile.financial_status,
            id_number=profile.id_number,
            passport_number=profile.passport_number,
        )

    academic_info = academic_info_response(profile)

    documents_data = public_documents(profile)

    languages_list = (
        [LanguageItem(**lang) for lang in profile.languages_data]
        if profile.languages_data
        else []
    )

    skills_and_languages = SkillsAndLanguages(
        languages=languages_list, skills=profile.skills_data or []
    )

    experiences_list = [
        ExperienceResponse.model_validate(exp) for exp in (profile.experiences or [])
    ]

    preferences_data = PreferencesResponse(
        desired_degree_level=profile.desired_degree_level,
        funding_type=profile.funding_type,
        preferred_fields_of_study=profile.preferred_fields_of_study or [],
        preferred_countries=profile.preferred_countries or [],
        is_profile_completed=bool(profile.desired_degree_level and profile.funding_type),
    )

    completion_percentage = calculate_profile_completion(
        personal_info=personal_info,
        academic_info=academic_info,
        documents=documents_data,
        skills_and_languages=skills_and_languages,
        experiences=experiences_list,
        preferences=preferences_data,
    )

    return UserProfile(
        id=profile.id,
        user_id=profile.user_id,
        personal_info=personal_info,
        academic_info=academic_info,
        documents=documents_data,
        skills_and_languages=skills_and_languages,
        experiences=experiences_list,
        preferences=preferences_data,
        avatar_url=avatar_presigned_url(profile, storage) if storage is not None else None,
        profile_completion_percentage=completion_percentage,
    )


# ==========================================
# GET /profile/personal-info
# ==========================================
@router.get("/personal-info", response_model=PersonalInfo | None)
def get_personal_info(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    # Registration creates an empty profile. Do not validate that draft as a
    # completed PersonalInfo resource; PUT remains strictly validated.
    if not profile or not all((
        profile.first_name, profile.last_name, profile.birth_date,
        profile.gender, profile.nationality, profile.country_of_residence,
    )):
        return None

    return PersonalInfo(
        first_name=profile.first_name or "",
        last_name=profile.last_name or "",
        email=current_user.email,
        phone_number=profile.phone_number,
        gender=profile.gender,
        birth_date=profile.birth_date,
        nationality=profile.nationality or "",
        country_of_residence=profile.country_of_residence or "",
        city=profile.city,
        financial_status=profile.financial_status,
        id_number=profile.id_number,
        passport_number=profile.passport_number,
    )


# ==========================================
# PUT /profile/personal-info
# ==========================================
@router.put("/personal-info", response_model=PersonalInfo)
def update_personal_info(
    data: PersonalInfo,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. تحديث البريد الإلكتروني في كائن User إذا تغير
    if data.email != current_user.email:
        existing_user = db.query(User).filter(User.email == data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="البريد الإلكتروني مستخدم بالفعل من قبل حساب آخر.",
            )
        current_user.email = data.email

    # 2. جلب الـ Profile أو إنشائه إن لم يكن موجوداً
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    # 3. تحديث بيانات الـ Profile
    profile.first_name = data.first_name
    profile.last_name = data.last_name
    profile.email = data.email          # مزامنة email في profiles أيضاً
    profile.phone_number = data.phone_number
    profile.gender = data.gender
    profile.birth_date = data.birth_date
    profile.nationality = data.nationality
    profile.country_of_residence = data.country_of_residence
    profile.city = data.city
    profile.financial_status = data.financial_status
    profile.id_number = data.id_number
    profile.passport_number = data.passport_number

    # 4. حفظ التغييرات لكل من User و Profile
    db.commit()
    db.refresh(current_user)
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
        passport_number=profile.passport_number,
    )



# ==========================================
# GET /profile/academic-info
# ==========================================
@router.get("/academic-info", response_model=AcademicInfoResponse | None)
def get_academic_info(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    return academic_info_response(profile)


# ==========================================
# PUT /profile/academic-info
# ==========================================
@router.put("/academic-info", response_model=AcademicInfoResponse)
def update_academic_info(
    data: AcademicInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    for name, value in data.model_dump(mode="json", exclude={"gpa"}).items():
        setattr(profile, name, value)
    profile.gpa_value = data.gpa.value
    profile.gpa_scale = data.gpa.scale

    db.commit()
    db.refresh(profile)

    return academic_info_response(profile)


# ==========================================
# Avatar Endpoints
# ==========================================
@router.post("/avatar/upload-url", response_model=UploadUrlResponse)
def create_avatar_upload_url(
    payload: AvatarUploadUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    session = create_avatar_upload_session(
        db=db,
        user=current_user,
        storage=storage,
        file_name=payload.file_name,
        content_type=payload.content_type,
        file_size=payload.file_size,
    )
    expires_in = settings.S3_PRESIGN_PUT_EXPIRE_SECONDS
    upload_url = storage.presign_put(
        session.object_key, session.expected_content_type, expires_in
    )
    return UploadUrlResponse(
        upload_id=session.id,
        upload_url=upload_url,
        headers={"Content-Type": session.expected_content_type},
        expires_in=expires_in,
    )


@router.post("/avatar/confirm", response_model=AvatarConfirmResponse)
def confirm_profile_avatar(
    payload: ConfirmUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    profile, avatar_url, expires_in = confirm_avatar_upload(
        db=db,
        user=current_user,
        storage=storage,
        upload_id=payload.upload_id,
    )
    return AvatarConfirmResponse(
        file_name=profile.avatar_file_name or "",
        content_type=profile.avatar_content_type or "",
        file_size=profile.avatar_file_size or 0,
        uploaded_at=profile.avatar_uploaded_at,
        avatar_url=avatar_url,
        expires_in=expires_in,
    )


@router.get("/avatar/url", response_model=DownloadUrlResponse)
def get_avatar_url(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    avatar_url = avatar_presigned_url(profile, storage)
    if not avatar_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="لا يوجد أفاتار.",
        )
    return DownloadUrlResponse(
        download_url=avatar_url,
        expires_in=settings.S3_PRESIGN_GET_EXPIRE_SECONDS,
    )


@router.delete("/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    delete_avatar(db=db, user=current_user, storage=storage)


# ==========================================
# Upload / Documents Endpoints
# ==========================================
@router.post("/documents/upload-url", response_model=UploadUrlResponse)
def create_document_upload_url(
    payload: UploadUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    session = create_upload_session(
        db=db,
        user=current_user,
        storage=storage,
        document_type=payload.document_type,
        file_name=payload.file_name,
        content_type=payload.content_type,
        file_size=payload.file_size,
    )
    expires_in = settings.S3_PRESIGN_PUT_EXPIRE_SECONDS
    upload_url = storage.presign_put(
        session.object_key, session.expected_content_type, expires_in
    )
    return UploadUrlResponse(
        upload_id=session.id,
        upload_url=upload_url,
        headers={"Content-Type": session.expected_content_type},
        expires_in=expires_in,
    )


@router.post("/documents/confirm", response_model=UploadedFile)
def confirm_document_upload(
    payload: ConfirmUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    record = confirm_upload_session(
        db=db,
        user=current_user,
        storage=storage,
        upload_id=payload.upload_id,
    )
    return UploadedFile.model_validate(record)


@router.get(
    "/documents/{document_id}/download-url",
    response_model=DownloadUrlResponse,
)
def get_document_download_url(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    download_url, expires_in = create_download_url(
        db=db,
        user=current_user,
        storage=storage,
        document_id=document_id,
    )
    return DownloadUrlResponse(download_url=download_url, expires_in=expires_in)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    delete_document(
        db=db,
        user=current_user,
        storage=storage,
        document_id=document_id,
    )


@router.get("/documents", response_model=Documents)
def get_documents(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    return public_documents(profile)


# ==========================================
# Skills & Languages Endpoints
# ==========================================
@router.get("/skills-and-languages", response_model=SkillsAndLanguages)
def get_skills_and_languages(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        return SkillsAndLanguages()

    languages_list = (
        [LanguageItem(**lang) for lang in profile.languages_data]
        if profile.languages_data
        else []
    )

    return SkillsAndLanguages(
        languages=languages_list, skills=profile.skills_data or []
    )


@router.get(
    "/skills-and-languages/suggestions",
    response_model=SkillsAndLanguagesSuggestions,
)
def get_suggestions():
    return SkillsAndLanguagesSuggestions(
        popular_languages=[
            "العربية",
            "الإنجليزيّة",
            "التركية",
            "الفرنسية",
            "الإسبانية",
            "الألمانية",
        ],
        suggested_skills_by_category={
            "تقنية": [
                "JavaScript",
                "Python",
                "React",
                "Node.js",
                "Docker",
                "Power BI",
                "Data Analysis",
            ],
            "تواصل": ["التواصل الفعال", "إدارة الوقت", "العمل الجماعي", "القيادة"],
            "أخرى": ["إدارة المشاريع", "حل المشكلات", "التفكير النقدي"],
        },
    )


@router.put("/skills-and-languages", response_model=SkillsAndLanguages)
def update_skills_and_languages(
    data: SkillsAndLanguages,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.languages_data = [
        lang.model_dump(mode="json", by_alias=True) for lang in data.languages
    ]
    profile.skills_data = data.skills

    db.commit()
    db.refresh(profile)

    return data


# ==========================================
# Experiences Endpoints
# ==========================================
@router.get("/experiences", response_model=List[ExperienceResponse])
def get_experiences(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        return []

    return db.query(Experience).filter(Experience.profile_id == profile.id).all()


@router.post(
    "/experiences",
    response_model=ExperienceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experience(
    data: ExperienceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        description=data.description,
    )

    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    return new_exp


@router.put("/experiences/{exp_id}", response_model=ExperienceResponse)
def update_experience(
    exp_id: int,
    data: ExperienceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    exp = (
        db.query(Experience)
        .filter(Experience.id == exp_id, Experience.profile_id == profile.id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience item not found")

    if data.experience_type is not None:
        exp.experience_type = data.experience_type
    if data.title is not None:
        exp.title = data.title
    if data.organization is not None:
        exp.organization = data.organization
    if data.start_date is not None:
        exp.start_date = data.start_date
    if data.is_current is not None:
        exp.is_current = data.is_current
        exp.end_date = None if data.is_current else data.end_date
    elif data.end_date is not None:
        exp.end_date = data.end_date
    if data.description is not None:
        exp.description = data.description

    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/experiences/{exp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    exp = (
        db.query(Experience)
        .filter(Experience.id == exp_id, Experience.profile_id == profile.id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience item not found")

    db.delete(exp)
    db.commit()
    return None


# ==========================================
# Preferences Endpoints
# ==========================================
@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        return PreferencesResponse()

    return PreferencesResponse(
        desired_degree_level=profile.desired_degree_level,
        funding_type=profile.funding_type,
        preferred_fields_of_study=profile.preferred_fields_of_study or [],
        preferred_countries=profile.preferred_countries or [],
        is_profile_completed=bool(profile.desired_degree_level and profile.funding_type),
    )


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    data: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    profile.desired_degree_level = data.desired_degree_level
    profile.funding_type = data.funding_type
    profile.preferred_fields_of_study = data.preferred_fields_of_study
    profile.preferred_countries = data.preferred_countries

    db.commit()
    db.refresh(profile)

    return PreferencesResponse(
        desired_degree_level=profile.desired_degree_level,
        funding_type=profile.funding_type,
        preferred_fields_of_study=profile.preferred_fields_of_study,
        preferred_countries=profile.preferred_countries,
        is_profile_completed=bool(profile.desired_degree_level and profile.funding_type),
    )


# ==========================================
# GET /profile (البروفايل الكامل)
# ==========================================
@router.get("", response_model=UserProfile)
def get_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageClient = Depends(get_s3_storage),
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()

    # إذا لم يوجد profile (مستخدم قديم سبق التسجيل)، أنشئ واحداً فارغاً
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return build_full_profile_response(profile, current_user, storage)
