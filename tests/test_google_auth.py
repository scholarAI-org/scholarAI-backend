import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "google-auth-test-key")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.auth_account import AuthAccount
from app.models.profile import Profile
from app.models.user import User
from app.services.google_auth import GoogleCredentialError, GoogleIdentity


class GoogleAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

        def override_get_db():
            with cls.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        AuthAccount.__table__.drop(self.engine, checkfirst=True)
        Profile.__table__.drop(self.engine, checkfirst=True)
        User.__table__.drop(self.engine, checkfirst=True)
        User.__table__.create(self.engine)
        Profile.__table__.create(self.engine)
        AuthAccount.__table__.create(self.engine)

    def authenticate(self, identity=None):
        identity = identity or GoogleIdentity(
            subject="google-123",
            email="student@example.com",
            full_name="Student Name",
            picture="https://example.com/photo.jpg",
        )
        with patch("app.api.auth.verify_google_id_token", return_value=identity):
            return self.client.post("/auth/google", json={"credential": "mock-id-token"})

    def test_new_google_user_gets_profile_and_application_jwt(self):
        response = self.authenticate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token_type"], "bearer")
        self.assertEqual(response.json()["user"]["email"], "student@example.com")
        token = response.json()["access_token"]
        protected = self.client.get(
            "/profile/personal-info", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertNotEqual(protected.status_code, 401)

        with self.Session() as db:
            user = db.query(User).one()
            self.assertTrue(user.is_email_verified)
            self.assertIsNotNone(db.query(Profile).filter_by(user_id=user.id).one_or_none())
            self.assertIsNotNone(db.query(AuthAccount).filter_by(user_id=user.id).one_or_none())

    def test_existing_google_identity_logs_in_without_duplicates(self):
        self.assertEqual(self.authenticate().status_code, 200)
        self.assertEqual(self.authenticate().status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(AuthAccount).count(), 1)

    def test_verified_google_email_links_existing_password_user(self):
        with self.Session() as db:
            user = User(
                full_name="Password User",
                email="student@example.com",
                hashed_password=hash_password("Pass123!"),
                role="student",
                is_email_verified=False,
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id))
            original_id = user.id
            db.commit()

        self.assertEqual(self.authenticate().status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual(db.query(AuthAccount).one().user_id, original_id)
            self.assertTrue(db.get(User, original_id).is_email_verified)

    def test_bad_google_credentials_are_rejected(self):
        messages = (
            "Invalid Google credential",
            "Google credential has expired",
            "Invalid Google credential audience",
            "Google email is not verified",
        )
        for message in messages:
            with self.subTest(message=message), patch(
                "app.api.auth.verify_google_id_token",
                side_effect=GoogleCredentialError(message),
            ):
                response = self.client.post(
                    "/auth/google", json={"credential": "bad-token"}
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], message)


if __name__ == "__main__":
    unittest.main()
