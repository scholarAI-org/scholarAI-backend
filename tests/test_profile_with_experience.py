import os
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "profile-with-experience-test-key-at-least-32-bytes")

from app.api.profile import router
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.profile import Experience, Profile
from app.models.user import User

PATH = "/profile/profile-with-experience"
PROFILE_DATA = {
    "first_name": "John",
    "last_name": "Doe",
    "nationality": "PS",
    "country_of_residence": "PS",
    "academic_level": "BACHELOR",
    "study_status": "GRADUATED",
    "field_of_study": "Computer Science",
    "detailed_specialization": "Software Engineering",
    "institution": "Example University",
    "gpa_value": 3.5,
    "gpa_scale": "SCALE_4",
    "current_study_language": ["English", "Arabic"],
    "expected_graduation_year": 2026,
    "desired_degree_level": "MASTER",
    "target_field_of_study": "Computer Science",
    "research_specialization": "Artificial Intelligence",
    "languages_data": [
        {"name": "Arabic", "proficiency": "NATIVE", "metadata": {"verified": False}}
    ],
    "skills_data": ["Python", "SQL"],
    "has_experience": True,
}


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (User, Profile, Experience):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        user = User(full_name="John Doe", email="john@example.com", hashed_password="unused")
        db.add(user)
        db.flush()
        user_id = user.id
        # Deliberately different IDs catch accidental filtering by user_id on experiences.
        db.add(Profile(id=50, user_id=user_id))
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = (
                f"Bearer {create_access_token({'sub': str(user_id)})}"
            )
            yield client, sessions, user_id
    finally:
        engine.dispose()


def experience(**changes):
    return Experience(
        **({
            "experience_type": "WORK",
            "title": "Backend Developer",
            "organization": "Example Organization",
            "start_date": date(2025, 1, 1),
            "end_date": None,
            "is_current": True,
            "description": "Backend development experience.",
        } | changes)
    )


def test_returns_exact_profile_and_multiple_linked_experiences(api):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        for name, value in PROFILE_DATA.items():
            setattr(profile, name, value)
        profile.email = "private@example.com"
        profile.passport_number = "PRIVATE123"
        profile.documents_data = {"cv": {"object_key": "private/cv.pdf"}}
        profile.experiences = [
            experience(),
            experience(
                experience_type="VOLUNTEER",
                title="Community Organizer",
                end_date=date(2025, 12, 31),
                is_current=False,
                description=None,
            ),
        ]
        db.commit()

    response = client.get(PATH)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"profile", "experiences"}
    assert data["profile"] == PROFILE_DATA
    assert sorted(data["experiences"], key=lambda item: item["title"]) == [
        {
            "experience_type": "WORK",
            "title": "Backend Developer",
            "organization": "Example Organization",
            "start_date": "2025-01-01",
            "end_date": None,
            "is_current": True,
            "description": "Backend development experience.",
        },
        {
            "experience_type": "VOLUNTEER",
            "title": "Community Organizer",
            "organization": "Example Organization",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "is_current": False,
            "description": None,
        },
    ]


def test_other_users_data_cannot_be_selected_or_exposed(api):
    client, sessions, user_id = api
    with sessions() as db:
        own_profile = db.query(Profile).filter_by(user_id=user_id).one()
        own_profile.experiences = [experience()]
        other = User(full_name="Other User", email="other@example.com", hashed_password="unused")
        other.profile = Profile(first_name="Private", experiences=[experience(title="Secret")])
        db.add(other)
        db.commit()
        other_id, other_profile_id = other.id, other.profile.id

    response = client.get(PATH, params={"user_id": other_id, "profile_id": other_profile_id})
    assert response.status_code == 200
    assert response.json()["profile"]["first_name"] is None
    assert [item["title"] for item in response.json()["experiences"]] == ["Backend Developer"]

    # The other user's valid token selects their own profile and experiences.
    response = client.get(
        PATH, headers={"Authorization": f"Bearer {create_access_token({'sub': str(other_id)})}"}
    )
    assert response.status_code == 200
    assert response.json()["profile"]["first_name"] == "Private"
    assert [item["title"] for item in response.json()["experiences"]] == ["Secret"]


@pytest.mark.parametrize("has_experience", [None, False, True])
def test_profile_without_experiences_returns_empty_array(api, has_experience):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.has_experience = has_experience
        db.commit()
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["experiences"] == []
    assert response.json()["profile"] == {
        key: has_experience if key == "has_experience" else (
            [] if key in {"current_study_language", "languages_data", "skills_data"} else None
        )
        for key in PROFILE_DATA
    }


def test_nullable_json_and_legacy_experience_fields_remain_null(api):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.current_study_language = None
        profile.languages_data = None
        profile.skills_data = None
        profile.experiences = [experience(is_current=False, description=None)]
        db.flush()
        db.execute(update(Experience).values(is_current=None))
        db.commit()
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    for field in ("current_study_language", "languages_data", "skills_data"):
        assert response.json()["profile"][field] is None
    for field in ("end_date", "is_current", "description"):
        assert response.json()["experiences"][0][field] is None


def test_missing_profile_returns_404_without_creating_one(api):
    client, sessions, user_id = api
    with sessions() as db:
        db.delete(db.query(Profile).filter_by(user_id=user_id).one())
        db.commit()
    response = client.get(PATH)
    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}
    with sessions() as db:
        assert db.query(Profile).filter_by(user_id=user_id).count() == 0


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_authentication_matches_existing_protected_endpoint(api, authorization):
    client = api[0]
    client.headers.pop("Authorization")
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get(PATH, headers=headers)
    existing = client.get("/profile/experiences", headers=headers)
    assert response.status_code in {401, 403}
    assert response.status_code == existing.status_code
    assert response.json() == existing.json()
    assert response.headers.get("WWW-Authenticate") == existing.headers.get("WWW-Authenticate")


def test_experiences_are_eager_loaded_without_extra_queries_or_writes(api):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.experiences = [experience(title=f"Experience {index}") for index in range(12)]
        db.commit()
    statements = []
    engine = sessions.kw["bind"]

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = client.get(PATH)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    assert response.status_code == 200
    assert len(response.json()["experiences"]) == 12
    # One authentication query and one query for the profile plus its experiences.
    assert len(statements) == 2
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
