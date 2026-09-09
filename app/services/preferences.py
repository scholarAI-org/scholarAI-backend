from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.profile import Profile
from app.schemas.profile import (
    DesiredDegreeLevel,
    PreferencesResponse,
    PreferencesState,
    PreferencesUpdate,
)


def preferences_response(profile: Profile | None) -> PreferencesResponse:
    """One nullable serializer for section GET/PUT and aggregate profile reads."""
    if profile is None:
        return PreferencesResponse()
    is_phd = profile.desired_degree_level == DesiredDegreeLevel.PHD
    is_open = bool(profile.open_to_all_countries)
    specialization = profile.detailed_specialization if is_phd else None
    return PreferencesResponse.model_validate(
        {
            "desired_degree_level": profile.desired_degree_level,
            "target_field_of_study": profile.target_field_of_study,
            "target_field_of_study_openalex_id": profile.target_field_of_study_openalex_id,
            "detailed_specialization": specialization,
            "funding_type": profile.funding_type,
            "preferred_countries": []
            if is_open
            else (profile.preferred_countries or []),
            "open_to_all_countries": is_open,
            "is_profile_completed": bool(
                profile.desired_degree_level
                and profile.funding_type
                and profile.target_field_of_study
                and profile.target_field_of_study.strip()
                and (not is_phd or (specialization and specialization.strip()))
            ),
        }
    )


def save_preferences(
    db: Session, user_id: int, profile: Profile | None, update: PreferencesUpdate
) -> Profile:
    values = preferences_response(profile).model_dump(exclude={"is_profile_completed"})
    changes = update.model_dump(exclude_unset=True)
    # Existing fields retain their established null-as-no-change PUT semantics.
    for name in (
        "desired_degree_level",
        "funding_type",
        "preferred_countries",
        "open_to_all_countries",
    ):
        if changes.get(name) is None:
            changes.pop(name, None)
    if "target_field_of_study" in changes:
        target_changed = (
            changes["target_field_of_study"] != values["target_field_of_study"]
        )
        if changes["target_field_of_study"] is None:
            # A supplied non-null ID will still fail validation below.
            changes.setdefault("target_field_of_study_openalex_id", None)
        elif target_changed and "target_field_of_study_openalex_id" not in changes:
            changes["target_field_of_study_openalex_id"] = None
    values.update(changes)
    try:
        normalized = PreferencesState.model_validate(values)
    except ValidationError as exc:
        errors = [dict(error, loc=("body", *error["loc"])) for error in exc.errors()]
        raise RequestValidationError(errors) from exc
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)
    for name, value in normalized.model_dump(mode="json").items():
        setattr(profile, name, value)
    db.commit()
    db.refresh(profile)
    return profile
