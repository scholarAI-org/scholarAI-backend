import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-notification-counter")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.admin_notification import AdminNotification, AdminNotificationRead
from app.models.user import User


class AdminNotificationCounterTests(unittest.TestCase):
    endpoint = "/admin/notifications/unread-count"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(bind=self.engine)

        AdminNotification.__table__.create(self.engine)
        User.__table__.create(self.engine)
        AdminNotificationRead.__table__.create(self.engine)

        def override_get_db():
            with self.Session() as db:
                yield db

        original_overrides = app.dependency_overrides.copy()
        self.addCleanup(self._restore_overrides, original_overrides)
        app.dependency_overrides[get_db] = override_get_db

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

        self.admin_token = self._add_user("admin")
        self.student_token = self._add_user("student")

    def _restore_overrides(self, overrides):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    def _add_user(self, role, *, is_active=True, is_email_verified=True):
        with self.Session() as db:
            user = User(
                full_name="Admin notification test user",
                email=f"user-{db.query(User).count()}@example.com",
                hashed_password="not-used",
                role=role,
                is_active=is_active,
                is_email_verified=is_email_verified,
            )
            db.add(user)
            db.commit()
            return create_access_token({"sub": str(user.id), "role": role})

    def _add_notifications(self, is_read_list: list[bool]):
        with self.Session() as db:
            for idx, is_read in enumerate(is_read_list):
                db.add(
                    AdminNotification(
                        title=f"Notification {idx}",
                        message=f"Message {idx}",
                        notification_type="scholarship",
                        is_read=is_read,
                    )
                )
            db.commit()

    def _get(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(self.endpoint, headers=headers)

    def test_admin_receives_correct_unread_count(self):
        # 3 unread, 2 read
        self._add_notifications([False, False, True, False, True])
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 3})

    def test_zero_unread_when_table_empty(self):
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 0})

    def test_zero_unread_when_all_are_read(self):
        self._add_notifications([True, True, True])
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 0})

    def test_all_unread_counted(self):
        self._add_notifications([False, False, False, False])
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 4})

    def test_unauthenticated_request_is_rejected(self):
        response = self._get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Not authenticated"})

    def test_invalid_token_is_rejected(self):
        response = self._get("invalid-bearer-token")
        self.assertEqual(response.status_code, 401)

    def test_non_admin_is_rejected_403(self):
        response = self._get(self.student_token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "This operation is restricted to administrators."},
        )

    def test_endpoint_does_not_mutate_records(self):
        self._add_notifications([False, True, False])
        with self.Session() as db:
            before_count = db.query(AdminNotification).count()

        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"unread_count": 2})

        with self.Session() as db:
            after_count = db.query(AdminNotification).count()
            self.assertEqual(before_count, after_count)


if __name__ == "__main__":
    unittest.main()
