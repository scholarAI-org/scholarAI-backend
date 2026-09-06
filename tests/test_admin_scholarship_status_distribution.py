import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-status-distribution")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


class ScholarshipStatusDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS scholarships"))
            connection.execute(text("DROP TABLE IF EXISTS users"))
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY, "
                    "status VARCHAR(20)"
                    ")"
                )
            )
        User.__table__.create(self.engine)

        with self.Session() as db:
            admin = User(
                full_name="Admin User",
                email="admin@example.com",
                hashed_password="not-used",
                role="admin",
                is_email_verified=True,
            )
            student = User(
                full_name="Student User",
                email="student@example.com",
                hashed_password="not-used",
                role="student",
                is_email_verified=True,
            )
            db.add_all([admin, student])
            db.commit()
            db.refresh(admin)
            db.refresh(student)
            self.admin_token = create_access_token(
                {"sub": str(admin.id), "role": admin.role}
            )
            self.student_token = create_access_token(
                {"sub": str(student.id), "role": student.role}
            )

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _insert_statuses(self, statuses: list[str]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO scholarships (status) VALUES (:status)"),
                [{"status": status_value} for status_value in statuses],
            )

    def _scholarship_rows(self) -> list[tuple[int, str]]:
        with self.engine.connect() as connection:
            return [
                tuple(row)
                for row in connection.execute(
                    text("SELECT id, status FROM scholarships ORDER BY id")
                ).all()
            ]

    def test_admin_receives_counts_zero_status_and_ignores_unrelated_status(self):
        self._insert_statuses(["approved", "approved", "pending", "archived"])

        response = self.client.get(
            "/api/scholarships/status-distribution",
            headers=self._headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"published": 2, "pending": 1, "rejected": 0},
        )

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/scholarships/status-distribution")

        self.assertIn(response.status_code, (401, 403))

    def test_non_admin_request_is_rejected(self):
        response = self.client.get(
            "/api/scholarships/status-distribution",
            headers=self._headers(self.student_token),
        )

        self.assertEqual(response.status_code, 403)

    def test_endpoint_does_not_modify_scholarships(self):
        self._insert_statuses(["approved", "pending", "rejected", "archived"])
        before = self._scholarship_rows()

        response = self.client.get(
            "/api/scholarships/status-distribution",
            headers=self._headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"published": 1, "pending": 1, "rejected": 1},
        )
        self.assertEqual(self._scholarship_rows(), before)


if __name__ == "__main__":
    unittest.main()
