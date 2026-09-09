import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "profile-api-test-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.profile import router
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.profile import Profile
from app.schemas.profile import AcademicLevel, ExperienceType, GPAScale


class ProfileApiEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()

        def mock_refresh(instance):
            if hasattr(instance, "id") and instance.id is None:
                instance.id = 1

        self.db.refresh.side_effect = mock_refresh
        self.profile = Profile(user_id=1, id=10)
        self.user = SimpleNamespace(id=1, email="test@example.com")
        self.db.query.return_value.filter.return_value.first.return_value = self.profile

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    # --- Academic Info Tests ---
    def test_academic_info_put_success_without_institution(self):
        payload = {
            "academic_level": AcademicLevel.BACHELOR.value,
            "field_of_study": "Computer Science",
            "field_of_study_openalex_id": "https://openalex.org/subfields/1702",
            "study_status": "CURRENTLY_STUDYING",
            "gpa": {"value": 3.75, "scale": GPAScale.SCALE_4.value},
            "expected_graduation_year": 2026,
            "current_study_language": ["English"],
        }
        response = self.client.put("/profile/academic-info", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["expected_graduation_year"], 2026)
        self.assertEqual(data["gpa"]["value"], 3.75)
        self.assertIsNone(data["institution"])
        self.db.commit.assert_called()

    def test_academic_info_put_rejected_when_missing_gpa(self):
        payload = {
            "academic_level": AcademicLevel.BACHELOR.value,
            "field_of_study": "Computer Science",
            "field_of_study_openalex_id": "https://openalex.org/subfields/1702",
            "study_status": "CURRENTLY_STUDYING",
            "expected_graduation_year": 2026,
        }
        response = self.client.put("/profile/academic-info", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_academic_info_put_rejected_when_missing_expected_graduation_year(self):
        payload = {
            "academic_level": AcademicLevel.BACHELOR.value,
            "field_of_study": "Computer Science",
            "field_of_study_openalex_id": "https://openalex.org/subfields/1702",
            "study_status": "CURRENTLY_STUDYING",
            "gpa": {"value": 3.75, "scale": GPAScale.SCALE_4.value},
        }
        response = self.client.put("/profile/academic-info", json=payload)
        self.assertEqual(response.status_code, 422)

    # --- Experience Tests ---
    def test_create_experience_success_without_description(self):
        payload = {
            "experience_type": ExperienceType.WORK.value,
            "title": "Backend Engineer",
            "organization": "OpenAI",
            "start_date": "2023-01-01",
            "end_date": "2024-01-01",
            "is_current": False,
        }
        response = self.client.post("/profile/experiences", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Backend Engineer")
        self.assertIsNone(data["description"])
        self.db.add.assert_called()

    def test_create_experience_rejected_when_not_current_and_missing_end_date(self):
        payload = {
            "experience_type": ExperienceType.WORK.value,
            "title": "Backend Engineer",
            "organization": "OpenAI",
            "start_date": "2023-01-01",
            "is_current": False,
        }
        response = self.client.post("/profile/experiences", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_create_experience_success_when_current_and_no_end_date(self):
        payload = {
            "experience_type": ExperienceType.VOLUNTEER.value,
            "title": "Community Organizer",
            "organization": "Local NGO",
            "start_date": "2024-01-01",
            "is_current": True,
        }
        response = self.client.post("/profile/experiences", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["is_current"])
        self.assertIsNone(data["end_date"])

    # --- Preferences Tests ---
    def test_preferences_preferred_countries_optional(self):
        payload = {
            "desired_degree_level": "MASTER",
            "funding_type": "FULL",
        }
        response = self.client.put("/profile/preferences", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["preferred_countries"], [])


if __name__ == "__main__":
    unittest.main()
