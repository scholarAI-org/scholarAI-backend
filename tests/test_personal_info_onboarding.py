import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.setdefault('SECRET_KEY', 'personal-info-test-key')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.profile import router
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.profile import Profile
from app.schemas.profile import PersonalInfo


class PersonalInfoOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.profile = Profile(user_id=1)
        self.db.query.return_value.filter.return_value.first.return_value = self.profile
        self.user = SimpleNamespace(id=1, email='sara@example.com')
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def test_original_response_construction_rejects_registration_draft(self):
        with self.assertRaises(ValidationError):
            PersonalInfo(first_name='', last_name='', email=self.user.email,
                         gender=None, birth_date=None, nationality='',
                         country_of_residence='', phone_number='')

    def test_empty_profile_returns_null(self):
        response = self.client.get('/profile/personal-info')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())
        self.db.commit.assert_not_called()

    def test_missing_profile_returns_null(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        response = self.client.get('/profile/personal-info')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())

    def test_first_put_then_get_returns_completed_information(self):
        payload = dict(first_name='Sara', last_name='Ahmad', email=self.user.email,
                       gender='FEMALE', birth_date='2000-01-15', nationality='PS',
                       country_of_residence='JO', financial_status='LIMITED')
        response = self.client.put('/profile/personal-info', json=payload)
        self.assertEqual(response.status_code, 200)
        self.db.commit.assert_called_once()
        loaded = self.client.get('/profile/personal-info')
        self.assertEqual(loaded.status_code, 200)
        for key, value in payload.items():
            self.assertEqual(loaded.json()[key], value)
        self.assertIsNone(loaded.json()['phone_number'])

    def test_put_without_financial_status_is_rejected(self):
        payload = dict(first_name='Sara', last_name='Ahmad', email=self.user.email,
                       gender='FEMALE', birth_date='2000-01-15', nationality='PS',
                       country_of_residence='JO')
        response = self.client.put('/profile/personal-info', json=payload)
        self.assertEqual(response.status_code, 422)
        self.db.commit.assert_not_called()

    def test_incomplete_put_is_still_rejected(self):
        response = self.client.put('/profile/personal-info', json={'first_name': 'Sara'})
        self.assertEqual(response.status_code, 422)
        self.db.commit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
