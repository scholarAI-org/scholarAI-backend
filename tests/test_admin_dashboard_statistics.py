import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-dashboard-statistics")

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.main import app
from app.models.user import User


class AdminDashboardStatisticsTests(unittest.TestCase):
    endpoint = "/admin/dashboard/statistics"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(bind=self.engine)
        # The full Scholarship model has PostgreSQL ARRAY fields; only the columns
        # used by these count queries are needed in the isolated SQLite database.
        with self.engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE scholarships (id INTEGER PRIMARY KEY, status VARCHAR(20))")
            )
        User.__table__.create(self.engine)

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
                full_name="Dashboard test user",
                email=f"user-{db.query(User).count()}@example.com",
                hashed_password="not-used",
                role=role,
                is_active=is_active,
                is_email_verified=is_email_verified,
            )
            db.add(user)
            db.commit()
            return create_access_token({"sub": str(user.id), "role": role})

    def _insert_statuses(self, statuses):
        with self.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO scholarships (status) VALUES (:status)"),
                [{"status": value} for value in statuses],
            )

    def _get(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(self.endpoint, headers=headers)

    def test_admin_receives_correct_counts_and_response_structure(self):
        self._insert_statuses(
            ["pending", "pending", "approved", "approved", "approved", "rejected", None]
        )
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"pending_scholarships": 2, "published_scholarships": 3, "users": 2},
        )

    def test_only_pending_scholarships_are_counted_as_pending(self):
        self._insert_statuses(["pending", "pending", "rejected", None])
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending_scholarships"], 2)
        self.assertEqual(response.json()["published_scholarships"], 0)

    def test_only_approved_scholarships_are_counted_as_published(self):
        self._insert_statuses(["approved", "approved", "rejected", "archived", None])
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["published_scholarships"], 2)
        self.assertEqual(response.json()["pending_scholarships"], 0)

    def test_users_includes_admins_inactive_and_unverified_accounts(self):
        self._add_user("admin")
        self._add_user("student", is_active=False)
        self._add_user("student", is_email_verified=False)
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], 5)

    def test_no_scholarships_returns_zero_counts(self):
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"pending_scholarships": 0, "published_scholarships": 0, "users": 2},
        )

    def test_empty_database_returns_all_zero_counts(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM users"))
        # A real authenticated admin requires a stored user. Override only auth
        # for this edge case, keeping the real database count queries in place.
        app.dependency_overrides[get_current_user] = lambda: User(id=1, role="admin")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"pending_scholarships": 0, "published_scholarships": 0, "users": 0},
        )

    def test_unauthenticated_request_is_rejected(self):
        response = self._get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Not authenticated"})

    def test_invalid_token_is_rejected(self):
        response = self._get("invalid-token")
        self.assertEqual(response.status_code, 401)

    def test_non_admin_is_rejected_even_with_admin_role_in_token(self):
        with self.Session() as db:
            student = db.query(User).filter(User.role == "student").one()
            misleading_token = create_access_token({"sub": str(student.id), "role": "admin"})
        for token in [self.student_token, misleading_token]:
            with self.subTest(token_role="student" if token == self.student_token else "admin"):
                response = self._get(token)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json(),
                    {"detail": "This operation is restricted to administrators."},
                )


if __name__ == "__main__":
    unittest.main()
