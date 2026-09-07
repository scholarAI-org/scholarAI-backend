from app.models.profile import Profile
from app.schemas.profile import GPA, AcademicInfoResponse


def academic_info_response(profile: Profile | None) -> AcademicInfoResponse | None:
    """One serializer for section GET/PUT and full-profile reads, including drafts."""
    if profile is None:
        return None
    values = {
        name: getattr(profile, name)
        for name in AcademicInfoResponse.model_fields
        if name != "gpa"
    }
    values["current_study_language"] = profile.current_study_language or []
    values["gpa"] = (
        GPA(value=profile.gpa_value, scale=profile.gpa_scale)
        if profile.gpa_value is not None and profile.gpa_scale is not None
        else None
    )
    if not any(value is not None and value != [] for value in values.values()):
        return None
    return AcademicInfoResponse.model_validate(values)
