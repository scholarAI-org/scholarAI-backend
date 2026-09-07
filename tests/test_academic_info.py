import os
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "academic-info-test-secret-key-at-least-32-bytes")

from app.api.profile import router
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.profile import Experience, Profile
from app.models.user import User
from app.services.s3 import get_s3_storage

SUBFIELD_ID = "https://openalex.org/subfields/1702"
TARGET_ID = "https://openalex.org/subfields/1706"
TOPIC_ID = "https://openalex.org/T11636"
REQUIRED_FIELDS = (
    "academic_level",
    "field_of_study",
    "gpa",
    "expected_graduation_year",
    "study_status",
    "target_field_of_study",
)
ALL_FIELDS = {
    *REQUIRED_FIELDS,
    "field_of_study_openalex_id",
    "institution",
    "current_study_language",
    "target_field_of_study_openalex_id",
    "research_specialization",
    "research_specialization_openalex_id",
}
DATABASES = ["sqlite://"]
if os.getenv("ACADEMIC_TEST_DATABASE_URL"):
    DATABASES.append(os.environ["ACADEMIC_TEST_DATABASE_URL"])


def current_year():
    return date.today().year  # noqa: DTZ011 -- match the server's calendar-year contract


def payload(level="BACHELOR", **changes):
    data = {
        "academic_level": level,
        "field_of_study": "SCIENTIFIC"
        if level == "TAWJIHI"
        else "Software Engineering",
        "field_of_study_openalex_id": None if level == "TAWJIHI" else SUBFIELD_ID,
        "gpa": {"value": 3.4, "scale": "SCALE_4"},
        "expected_graduation_year": current_year() + 1,
        "study_status": "CURRENTLY_STUDYING",
        "target_field_of_study": "Artificial Intelligence",
        "target_field_of_study_openalex_id": TARGET_ID,
    }
    return data | changes


@pytest.fixture(
    params=DATABASES, ids=lambda url: "postgres" if url != "sqlite://" else "sqlite"
)
def api(request):
    if request.param == "sqlite://":
        engine = create_engine(
            request.param,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        for model in (User, Profile, Experience):
            model.__table__.create(engine)
    else:
        # This database must already have been upgraded via Alembic; never
        # create_all here, so PostgreSQL tests exercise the actual migration.
        engine = create_engine(request.param)
        assert engine.url.host in {"localhost", "127.0.0.1"}
        assert engine.url.database.startswith("scholarai_academic_test_")
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        user = User(
            full_name="Academic Test",
            email="academic-test@example.com",
            hashed_password="unused",
        )
        db.add(user)
        db.flush()
        user_id = user.id
        db.add(Profile(user_id=user_id))
        db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_s3_storage] = lambda: None
    with TestClient(app) as client:
        client.headers["Authorization"] = (
            f"Bearer {create_access_token({'sub': str(user_id)})}"
        )
        try:
            yield client, sessions, user_id
        finally:
            with sessions() as db:
                db.delete(db.get(User, user_id))
                db.commit()
            engine.dispose()


@pytest.mark.parametrize("level", ["TAWJIHI", "BACHELOR", "MASTER", "PHD"])
def test_persists_complete_section_and_full_profile_in_fresh_session(api, level):
    client, sessions, user_id = api
    data = payload(level, current_study_language=["English"])
    saved = client.put("/profile/academic-info", json=data)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert set(result) == ALL_FIELDS
    for name, value in data.items():
        assert result[name] == value
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        for name, value in data.items():
            if name == "gpa":
                assert profile.gpa_value == value["value"]
                assert profile.gpa_scale.value == value["scale"]
            else:
                assert getattr(profile, name) == value
    assert client.get("/profile/academic-info").json() == result
    full = client.get("/profile")
    assert full.status_code == 200, full.text
    assert full.json()["academic_info"] == result
    assert full.json()["profile_completion_percentage"] == 22.0


@pytest.mark.parametrize("track", ["SCIENTIFIC", "LITERARY", "SHARIA", "INDUSTRIAL"])
def test_high_school_tracks_without_current_id(api, track):
    data = payload("TAWJIHI", field_of_study=track)
    del data["field_of_study_openalex_id"]
    response = api[0].put("/profile/academic-info", json=data)
    assert response.status_code == 200
    assert response.json()["field_of_study_openalex_id"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"field_of_study": "Computer Science"},
        {"field_of_study": "AGRICULTURAL"},
        {"field_of_study": "HOME_ECONOMICS"},
        {"field_of_study": "ENTREPRENEURSHIP_BUSINESS"},
        {"field_of_study_openalex_id": SUBFIELD_ID},
    ],
)
def test_invalid_high_school_track_or_id(api, changes):
    assert (
        api[0]
        .put("/profile/academic-info", json=payload("TAWJIHI", **changes))
        .status_code
        == 422
    )


@pytest.mark.parametrize("level", ["BACHELOR", "MASTER", "PHD"])
@pytest.mark.parametrize("missing", [True, False])
def test_university_current_id_required(api, level, missing):
    data = payload(level, field_of_study_openalex_id=None)
    if missing:
        del data["field_of_study_openalex_id"]
    assert api[0].put("/profile/academic-info", json=data).status_code == 422


@pytest.mark.parametrize("level", ["TAWJIHI", "BACHELOR", "MASTER", "PHD"])
@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_required_fields(api, level, field):
    data = payload(level)
    del data[field]
    response = api[0].put("/profile/academic-info", json=data)
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


@pytest.mark.parametrize(
    "changes",
    [
        {"study_status": "UNKNOWN"},
        {"study_status": None},
        {"academic_level": "DIPLOMA"},
        {"field_of_study": "   "},
        {"target_field_of_study": "   "},
        {"target_field_of_study": None},
        {"target_field_of_study": 42},
        {"field_of_study": "x" * 256},
        {"target_field_of_study": "x" * 256},
        {"institution": "x" * 256},
        {"field_of_study_openalex_id": "1702|Computer Science"},
        {"field_of_study_openalex_id": TOPIC_ID},
        {"field_of_study_openalex_id": "https://openalex.org/subfields/not-a-number"},
        {"target_field_of_study_openalex_id": "https://example.com/subfields/1706"},
        {"target_field_of_study_openalex_id": TOPIC_ID},
        {"unexpected_academic_field": "value"},
    ],
)
def test_invalid_input_does_not_overwrite_existing_data(api, changes):
    client = api[0]
    original = client.put("/profile/academic-info", json=payload()).json()
    response = client.put("/profile/academic-info", json=payload(**changes))
    assert response.status_code == 422
    assert client.get("/profile/academic-info").json() == original


@pytest.mark.parametrize("institution", [None, "", "   ", "  Example University  "])
def test_optional_institution_and_name_normalization(api, institution):
    response = api[0].put(
        "/profile/academic-info",
        json=payload(
            institution=institution,
            field_of_study="  Software Engineering  ",
            target_field_of_study="  Artificial Intelligence  ",
        ),
    )
    assert response.status_code == 200
    assert response.json()["institution"] == (
        institution.strip() if institution is not None else None
    )
    assert response.json()["field_of_study"] == "Software Engineering"
    assert response.json()["target_field_of_study"] == "Artificial Intelligence"


@pytest.mark.parametrize("status", ["CURRENTLY_STUDYING", "GRADUATED"])
def test_study_status_persists(api, status):
    response = api[0].put("/profile/academic-info", json=payload(study_status=status))
    assert response.status_code == 200
    assert api[0].get("/profile").json()["academic_info"]["study_status"] == status


def test_target_id_nullable_for_frontend_transition(api):
    data = payload()
    del data["target_field_of_study_openalex_id"]
    response = api[0].put("/profile/academic-info", json=data)
    assert response.status_code == 200
    assert response.json()["target_field_of_study_openalex_id"] is None


@pytest.mark.parametrize(
    "scale,limit",
    [("SCALE_4", 4), ("SCALE_5", 5), ("SCALE_10", 10), ("SCALE_100", 100)],
)
def test_gpa_scale_boundaries(api, scale, limit):
    for value in [0, limit]:
        assert (
            api[0]
            .put(
                "/profile/academic-info",
                json=payload(gpa={"value": value, "scale": scale}),
            )
            .status_code
            == 200
        )
    for value in [-0.1, limit + 0.1]:
        assert (
            api[0]
            .put(
                "/profile/academic-info",
                json=payload(gpa={"value": value, "scale": scale}),
            )
            .status_code
            == 422
        )


@pytest.mark.parametrize(
    "gpa", [{"value": 45, "scale": "SCALE_100"}, {"value": 1.5, "scale": "SCALE_4"}]
)
def test_low_but_valid_gpa_accepted(api, gpa):
    assert (
        api[0].put("/profile/academic-info", json=payload(gpa=gpa)).status_code == 200
    )


@pytest.mark.parametrize(
    "gpa",
    [
        None,
        {},
        {"value": "abc", "scale": "SCALE_4"},
        {"value": "3.4", "scale": "SCALE_4"},
        {"value": True, "scale": "SCALE_4"},
        {"value": 3, "scale": "SCALE_20"},
    ],
)
def test_invalid_gpa_rejected(api, gpa):
    assert (
        api[0].put("/profile/academic-info", json=payload(gpa=gpa)).status_code == 422
    )


@pytest.mark.parametrize(
    "offset,expected", [(-51, 422), (-50, 200), (10, 200), (11, 422)]
)
def test_dynamic_graduation_year(api, offset, expected):
    assert (
        api[0]
        .put(
            "/profile/academic-info",
            json=payload(expected_graduation_year=current_year() + offset),
        )
        .status_code
        == expected
    )


def test_year_validator_uses_runtime_not_import_time(api):
    with patch("app.schemas.profile.date") as clock:
        clock.today.return_value = date(2040, 1, 1)
        assert (
            api[0]
            .put("/profile/academic-info", json=payload(expected_graduation_year=2050))
            .status_code
            == 200
        )
        assert (
            api[0]
            .put("/profile/academic-info", json=payload(expected_graduation_year=2051))
            .status_code
            == 422
        )


@pytest.mark.parametrize("year", [True, 2027.5, "2027", None])
def test_invalid_year_type(api, year):
    assert (
        api[0]
        .put("/profile/academic-info", json=payload(expected_graduation_year=year))
        .status_code
        == 422
    )


def test_phd_topic_persisted_and_cleared_when_changing_level(api):
    client, sessions, user_id = api
    data = payload(
        "PHD",
        research_specialization="  Machine Learning  ",
        research_specialization_openalex_id=TOPIC_ID,
    )
    response = client.put("/profile/academic-info", json=data)
    assert response.status_code == 200
    assert response.json()["research_specialization"] == "Machine Learning"
    with sessions() as db:
        assert (
            db.query(Profile)
            .filter_by(user_id=user_id)
            .one()
            .research_specialization_openalex_id
            == TOPIC_ID
        )
    assert (
        client.get("/profile").json()["academic_info"][
            "research_specialization_openalex_id"
        ]
        == TOPIC_ID
    )
    assert (
        client.put("/profile/academic-info", json=payload("MASTER")).status_code == 200
    )
    result = client.get("/profile/academic-info").json()
    assert result["research_specialization"] is None
    assert result["research_specialization_openalex_id"] is None


@pytest.mark.parametrize("level", ["TAWJIHI", "BACHELOR", "MASTER"])
def test_research_specialization_only_for_phd(api, level):
    response = api[0].put(
        "/profile/academic-info",
        json=payload(
            level,
            research_specialization="Machine Learning",
            research_specialization_openalex_id=TOPIC_ID,
        ),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"research_specialization": "Machine Learning"},
        {"research_specialization_openalex_id": TOPIC_ID},
        {
            "research_specialization": "Machine Learning",
            "research_specialization_openalex_id": SUBFIELD_ID,
        },
    ],
)
def test_phd_topic_requires_matching_pair_and_topic_id_format(api, changes):
    assert (
        api[0].put("/profile/academic-info", json=payload("PHD", **changes)).status_code
        == 422
    )


@pytest.mark.parametrize(
    "legacy_field",
    [
        "COMPUTER_SCIENCE",
        "ENGINEERING",
        "MEDICINE",
        "BUSINESS",
        "ARTS",
        "OTHER",
        "AGRICULTURAL",
    ],
)
def test_legacy_data_preserved_and_not_counted_as_complete(api, legacy_field):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.academic_level = (
            "TAWJIHI" if legacy_field == "AGRICULTURAL" else "BACHELOR"
        )
        profile.field_of_study = legacy_field
        profile.institution = "Old University"
        profile.expected_graduation_year = 1990
        profile.gpa_value, profile.gpa_scale = 3.0, "SCALE_4"
        db.commit()
    section = client.get("/profile/academic-info")
    full = client.get("/profile")
    assert section.status_code == full.status_code == 200
    assert section.json()["field_of_study"] == legacy_field
    assert section.json()["study_status"] is None
    assert section.json()["target_field_of_study"] is None
    assert full.json()["academic_info"] == section.json()
    assert full.json()["profile_completion_percentage"] == 0


def test_registration_draft_and_partial_academic_records(api):
    client, sessions, user_id = api
    assert client.get("/profile/academic-info").json() is None
    assert client.get("/profile").json()["academic_info"] is None
    with sessions() as db:
        db.query(Profile).filter_by(user_id=user_id).one().academic_level = "BACHELOR"
        db.commit()
    section = client.get("/profile/academic-info")
    assert section.status_code == 200
    assert section.json()["academic_level"] == "BACHELOR"
    assert section.json()["field_of_study"] is None
    assert client.get("/profile").json()["academic_info"] == section.json()


def test_missing_profile_can_save_first_academic_section(api):
    client, sessions, user_id = api
    with sessions() as db:
        db.delete(db.query(Profile).filter_by(user_id=user_id).one())
        db.commit()
    assert client.get("/profile/academic-info").json() is None
    assert client.put("/profile/academic-info", json=payload()).status_code == 200
    assert (
        client.get("/profile").json()["academic_info"]["target_field_of_study"]
        == payload()["target_field_of_study"]
    )


def test_completion_excludes_optional_fields_and_requires_target(api):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.first_name, profile.last_name = "Test", "User"
        profile.birth_date = date(current_year() - 25, 1, 1)
        profile.gender, profile.nationality, profile.country_of_residence = (
            "MALE",
            "PS",
            "PS",
        )
        profile.financial_status = "MODERATE"
        profile.desired_degree_level, profile.funding_type = "PHD", "FULL"
        db.commit()
    assert (
        client.put(
            "/profile/academic-info",
            json=payload("PHD", gpa={"value": 0, "scale": "SCALE_4"}),
        ).status_code
        == 200
    )
    # Personal required fields: 18; academic: 22; degree/funding: 14.
    assert client.get("/profile").json()["profile_completion_percentage"] == 54
    with sessions() as db:
        db.query(Profile).filter_by(user_id=user_id).one().target_field_of_study = None
        db.commit()
    assert client.get("/profile").json()["profile_completion_percentage"] == 32


def test_academic_endpoints_require_authentication(api):
    client = api[0]
    del client.headers["Authorization"]
    assert client.get("/profile/academic-info").status_code == 401
    assert client.put("/profile/academic-info", json=payload()).status_code == 401


def test_completion_choices_persist_with_academic_contract(api):
    client, sessions, user_id = api
    assert client.put("/profile/academic-info", json=payload()).status_code == 200
    response = client.put("/profile/experiences/status", json={"has_experience": False})
    assert response.status_code == 200
    response = client.put("/profile/preferences", json={"open_to_all_countries": True})
    assert response.status_code == 200
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        assert profile.has_experience is False
        assert profile.open_to_all_countries is True
        assert profile.field_of_study_openalex_id == SUBFIELD_ID
    full = client.get("/profile").json()
    assert full["has_experience"] is False
    assert full["preferences"]["open_to_all_countries"] is True
    assert full["profile_completion_percentage"] == 33  # Academic 22 + countries 6 + no experience 5.


def test_openapi_contract():
    from app.main import app

    with TestClient(app) as client:
        result = client.get("/openapi.json")
        assert result.status_code == 200
        schema = result.json()
    models = schema["components"]["schemas"]
    update = models["AcademicInfoUpdate"]
    response = models["AcademicInfoResponse"]
    assert set(update["properties"]) == set(response["properties"]) == ALL_FIELDS
    assert set(update["required"]) == set(REQUIRED_FIELDS)
    assert "enum" not in update["properties"]["field_of_study"]
    assert "FieldOfStudy" not in models
    assert models["StudyStatus"]["enum"] == ["CURRENTLY_STUDYING", "GRADUATED"]
    assert models["GPAScale"]["enum"] == ["SCALE_4", "SCALE_5", "SCALE_10", "SCALE_100"]
    assert "maximum" not in update["properties"]["expected_graduation_year"]
    assert schema["paths"]["/profile/academic-info"]["put"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/AcademicInfoUpdate")
