import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-profile")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.profile import Profile
from app.models.user import User
from app.services.s3 import get_s3_storage
from tests.test_document_uploads import FakeS3


class AdminProfileEndpointTests(unittest.TestCase):
    endpoint = "/admin/profile"
    alias_endpoint = "/admin/me"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        User.__table__.create(self.engine)
        Profile.__table__.create(self.engine)

        def override_get_db():
            with self.Session() as db:
                yield db

        self.fake_s3 = FakeS3()

        original_overrides = app.dependency_overrides.copy()
        self.addCleanup(self._restore_overrides, original_overrides)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_s3_storage] = lambda: self.fake_s3

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _restore_overrides(self, overrides):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    def _create_user(self, role: str, full_name: str, email: str, *, with_profile: bool = True, avatar_key: str = None) -> tuple[int, str]:
        with self.Session() as db:
            user = User(
                full_name=full_name,
                email=email,
                hashed_password="hashed_pwd_test",
                role=role,
                is_active=True,
                is_email_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            if with_profile:
                profile = Profile(
                    user_id=user.id,
                    avatar_object_key=avatar_key,
                )
                db.add(profile)
                db.commit()

            token = create_access_token({"sub": str(user.id), "role": role})
            return user.id, token

    def test_unauthenticated_request_returns_401(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 401)

    def test_student_request_returns_403(self):
        _, student_token = self._create_user(
            role="student",
            full_name="Student User",
            email="student@example.com",
        )
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {student_token}"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "This operation is restricted to administrators.")

    def test_admin_profile_without_avatar(self):
        user_id, admin_token = self._create_user(
            role="admin",
            full_name="Admin Name",
            email="admin@example.com",
            with_profile=True,
            avatar_key=None,
        )
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], user_id)
        self.assertEqual(data["full_name"], "Admin Name")
        self.assertEqual(data["email"], "admin@example.com")
        self.assertEqual(data["role"], "admin")
        self.assertIsNone(data["avatar_url"])

    def test_admin_profile_with_avatar(self):
        user_id, admin_token = self._create_user(
            role="admin",
            full_name="Super Admin",
            email="superadmin@example.com",
            with_profile=True,
            avatar_key="users/1/avatar/pic.png",
        )
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], user_id)
        self.assertEqual(data["full_name"], "Super Admin")
        self.assertEqual(data["email"], "superadmin@example.com")
        self.assertEqual(data["role"], "admin")
        self.assertIsNotNone(data["avatar_url"])
        self.assertIn("users/1/avatar/pic.png", data["avatar_url"])

    def test_admin_profile_alias_me_endpoint(self):
        user_id, admin_token = self._create_user(
            role="admin",
            full_name="Alias Admin",
            email="alias@example.com",
            with_profile=True,
            avatar_key=None,
        )
        response = self.client.get(
            self.alias_endpoint,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], user_id)
        self.assertEqual(data["full_name"], "Alias Admin")
        self.assertIsNone(data["avatar_url"])

    def test_admin_profile_graceful_when_no_profile_record_exists(self):
        user_id, admin_token = self._create_user(
            role="admin",
            full_name="No Profile Admin",
            email="noprofile@example.com",
            with_profile=False,
        )
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], user_id)
        self.assertEqual(data["full_name"], "No Profile Admin")
        self.assertIsNone(data["avatar_url"])


if __name__ == "__main__":
    unittest.main()
