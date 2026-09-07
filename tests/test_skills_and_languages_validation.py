import os
import unittest
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "skills-validation-test-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.profile import router
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.profile import Experience, Profile
from app.models.user import User


class SkillsAndLanguagesValidationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        User.__table__.create(self.engine)
        Profile.__table__.create(self.engine)
        Experience.__table__.create(self.engine)

        with self.Session() as db:
            user = User(
                full_name="Validation User",
                email="validation@example.com",
                hashed_password="x",
                is_email_verified=True,
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id))
            db.commit()
            self.user_id = user.id

        self.current_user = SimpleNamespace(
            id=self.user_id, email="validation@example.com"
        )

        app = FastAPI()
        app.include_router(router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

        unauthenticated_app = FastAPI()
        unauthenticated_app.include_router(router)
        unauthenticated_app.dependency_overrides[get_db] = override_get_db
        self.unauthenticated_client = TestClient(unauthenticated_app)

    def tearDown(self):
        self.engine.dispose()

    def _put(self, languages=None, skills=None, client=None):
        return (client or self.client).put(
            "/profile/skills-and-languages",
            json={"languages": languages or [], "skills": skills or []},
        )

    def test_accepts_unique_values_and_trims_outer_whitespace(self):
        response = self._put(
            languages=[{"name": " English ", "proficiency": "ADVANCED"}],
            skills=[" Python ", "SQL"],
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["languages"][0]["name"], "English")
        self.assertEqual(response.json()["skills"], ["Python", "SQL"])

        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.user_id).one()
            self.assertEqual(profile.languages_data[0]["name"], "English")
            self.assertEqual(profile.skills_data, ["Python", "SQL"])

    def test_rejects_duplicate_language_ignoring_case_and_whitespace(self):
        response = self._put(
            languages=[
                {"name": "English", "proficiency": "ADVANCED"},
                {"name": " english ", "proficiency": "NATIVE"},
            ]
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("language", response.json()["detail"].lower())

    def test_rejects_duplicate_skill_on_create_and_update(self):
        duplicate_create = self._put(skills=["Python", " python "])
        self.assertEqual(duplicate_create.status_code, 409)

        created = self._put(skills=["Python", "SQL"])
        self.assertEqual(created.status_code, 200, created.text)

        duplicate_update = self._put(skills=["Python", " PYTHON "])
        self.assertEqual(duplicate_update.status_code, 409)
        self.assertIn("skill", duplicate_update.json()["detail"].lower())

        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.user_id).one()
            self.assertEqual(profile.skills_data, ["Python", "SQL"])

    def test_rejects_empty_too_long_and_wrongly_typed_values(self):
        invalid_payloads = [
            {"languages": [{"name": "  ", "proficiency": "BEGINNER"}]},
            {"languages": [{"name": "English", "proficiency": "UNKNOWN"}]},
            {"skills": ["  "]},
            {"skills": ["x" * 101]},
            {"skills": [123]},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.put(
                    "/profile/skills-and-languages",
                    json={"languages": [], "skills": [], **payload},
                )
                self.assertEqual(response.status_code, 422, response.text)

    def test_rejects_unbounded_list_sizes(self):
        too_many_languages = [
            {"name": f"Language {index}", "proficiency": "BEGINNER"}
            for index in range(51)
        ]
        too_many_skills = [f"Skill {index}" for index in range(101)]

        self.assertEqual(
            self._put(languages=too_many_languages).status_code,
            422,
        )
        self.assertEqual(self._put(skills=too_many_skills).status_code, 422)

    def test_endpoint_requires_authentication(self):
        response = self._put(skills=["Python"], client=self.unauthenticated_client)
        self.assertIn(response.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
