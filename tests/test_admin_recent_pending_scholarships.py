import os
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-recent-pending-scholarships")

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.main import app
from app.models import Scholarship
from app.models.user import User


class AdminRecentPendingScholarshipsTests(unittest.TestCase):
    endpoint = "/admin/dashboard/recent-pending-scholarships"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(bind=self.engine)
        # As in the other admin tests, omit PostgreSQL ARRAY/detail columns.
        # This also catches accidental loading of the full Scholarship model.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                    "organization_name TEXT, country VARCHAR(100), deadline DATE, "
                    "no_deadline BOOLEAN, source VARCHAR(20) NOT NULL, source_url TEXT, "
                    "status VARCHAR(20), scraped_at TIMESTAMP, "
                    "reviewed_at TIMESTAMP, reviewed_by VARCHAR(100))"
                )
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
        with self.Session() as db:
            for role in ("admin", "student"):
                user = User(
                    full_name="Pending scholarships test user",
                    email=f"{role}@example.com",
                    hashed_password="not-used",
                    role=role,
                    is_email_verified=True,
                )
                db.add(user)
                db.commit()
                setattr(self, f"{role}_id", user.id)
                setattr(
                    self,
                    f"{role}_token",
                    create_access_token({"sub": str(user.id), "role": role}),
                )

    def _restore_overrides(self, overrides):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    def _insert(self, scholarship_id, **overrides):
        values = {
            "id": scholarship_id,
            "title": f"Scholarship {scholarship_id}",
            "organization_name": "Example University",
            "country": "Palestine",
            "deadline": "2026-10-01",
            "no_deadline": False,
            "source": "for9a",
            "source_url": "https://example.com/scholarship",
            "status": "pending",
            "scraped_at": "2026-09-08 10:00:00+00:00",
            "reviewed_at": None,
            "reviewed_by": None,
        }
        values.update(overrides)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO scholarships ("
                    + ", ".join(values)
                    + ") VALUES ("
                    + ", ".join(f":{key}" for key in values)
                    + ")"
                ),
                values,
            )

    def _get(self, token=None, **params):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(self.endpoint, headers=headers, params=params)

    def test_admin_receives_exact_table_response(self):
        self._insert(1)
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {
                        "id": 1,
                        "title": "Scholarship 1",
                        "organization_name": "Example University",
                        "country": "Palestine",
                        "deadline": "2026-10-01",
                        "no_deadline": False,
                        "source": "for9a",
                        "source_url": "https://example.com/scholarship",
                        "status": "pending",
                        "scraped_at": "2026-09-08T10:00:00Z",
                    }
                ],
                "total": 1,
            },
        )

    def test_only_documented_scraper_sources_are_returned(self):
        for scholarship_id, source in enumerate(
            ("for9a", "ministry", "manual", "admin", "unknown", ""), start=1
        ):
            self._insert(scholarship_id, source=source)
        result = self._get(self.admin_token, limit=1).json()
        self.assertEqual(result["total"], 2)
        self.assertEqual([item["id"] for item in result["items"]], [2])
        result = self._get(self.admin_token).json()
        self.assertEqual(
            {item["source"] for item in result["items"]}, {"for9a", "ministry"}
        )

    def test_reviewed_and_non_pending_listings_are_excluded(self):
        self._insert(1)
        excluded = [
            {"status": value}
            for value in (
                "approved",
                "rejected",
                "published",
                "reviewed",
                "archived",
                None,
            )
        ] + [
            {"reviewed_at": "2026-09-08 11:00:00+00:00"},
            {"reviewed_by": "admin@example.com"},
            {"reviewed_by": ""},
        ]
        for scholarship_id, values in enumerate(excluded, start=2):
            self._insert(scholarship_id, **values)
        result = self._get(self.admin_token).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual([item["id"] for item in result["items"]], [1])

    def test_newest_first_with_stable_ties_and_unknown_dates_last(self):
        self._insert(1, scraped_at="2026-09-08 12:00:00+00:00")
        self._insert(2, scraped_at="2026-09-08 09:00:00+00:00")
        self._insert(3, scraped_at="2026-09-08 12:00:00+00:00")
        self._insert(4, scraped_at=None)
        self._insert(5, scraped_at=None)
        result = self._get(self.admin_token).json()
        self.assertEqual([item["id"] for item in result["items"]], [3, 1, 2, 5, 4])

    def test_default_and_limit_boundaries_keep_full_matching_total(self):
        for scholarship_id in range(1, 61):
            self._insert(scholarship_id)
        for params, expected_size in (({}, 10), ({"limit": 1}, 1), ({"limit": 50}, 50)):
            with self.subTest(params=params):
                response = self._get(self.admin_token, **params)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["total"], 60)
                self.assertEqual(
                    [item["id"] for item in result["items"]],
                    list(range(60, 60 - expected_size, -1)),
                )

    def test_limit_is_applied_in_sql_and_get_is_read_only(self):
        for scholarship_id in range(1, 4):
            self._insert(scholarship_id)
        statements = []

        def record_query(conn, cursor, statement, parameters, context, executemany):
            statements.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", record_query)
        self.addCleanup(
            event.remove, self.engine, "before_cursor_execute", record_query
        )
        response = self._get(self.admin_token, limit=2)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(sql.lstrip().upper().startswith("SELECT") for sql, _ in statements)
        )
        listing_queries = [
            (sql, params)
            for sql, params in statements
            if "FROM scholarships" in sql and "count(" not in sql
        ]
        self.assertEqual(len(listing_queries), 1)
        sql, params = listing_queries[0]
        self.assertIn("LIMIT", sql)
        self.assertEqual(params[-2:], (2, 0))
        self.assertNotIn("description_html", sql)
        self.assertNotIn("attachments", sql)

    def test_nullable_table_fields_are_preserved(self):
        nullable_fields = (
            "organization_name",
            "country",
            "deadline",
            "no_deadline",
            "source_url",
            "scraped_at",
        )
        self._insert(1, **dict.fromkeys(nullable_fields))
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        for field in nullable_fields:
            self.assertIsNone(response.json()["items"][0][field])

    def test_no_matching_scholarships_returns_empty_result(self):
        self._insert(1, status="approved")
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_empty_database_returns_valid_empty_result(self):
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM users"))
        app.dependency_overrides[get_current_user] = lambda: User(id=1, role="admin")
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_unauthenticated_request_is_rejected(self):
        response = self._get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Not authenticated"})

    def test_invalid_token_is_rejected(self):
        self.assertEqual(self._get("invalid-token").status_code, 401)

    def test_non_admin_is_rejected_even_with_admin_claim(self):
        misleading_token = create_access_token(
            {"sub": str(self.student_id), "role": "admin"}
        )
        for token in (self.student_token, misleading_token):
            with self.subTest(token=token):
                response = self._get(token)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json(),
                    {"detail": "This operation is restricted to administrators."},
                )

    def test_invalid_limits_use_standard_validation_response(self):
        for value, error_type in (
            ("0", "greater_than_equal"),
            ("-1", "greater_than_equal"),
            ("51", "less_than_equal"),
            ("abc", "int_parsing"),
            ("1.5", "int_parsing"),
            ("", "int_parsing"),
        ):
            with self.subTest(limit=value):
                response = self._get(self.admin_token, limit=value)
                self.assertEqual(response.status_code, 422)
                error = response.json()["detail"][0]
                self.assertEqual(error["loc"], ["query", "limit"])
                self.assertEqual(error["type"], error_type)

    def test_openapi_documents_auth_limit_and_response(self):
        operation = self.client.get("/openapi.json").json()["paths"][self.endpoint][
            "get"
        ]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        limit = next(
            param for param in operation["parameters"] if param["name"] == "limit"
        )
        self.assertEqual(limit["schema"]["minimum"], 1)
        self.assertEqual(limit["schema"]["maximum"], 50)
        self.assertEqual(limit["schema"]["default"], 10)
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"][
                "$ref"
            ],
            "#/components/schemas/AdminRecentPendingScholarshipsResponse",
        )

    @unittest.skipUnless(
        os.getenv("PENDING_TEST_DATABASE_URL"),
        "Requires a migrated disposable local PostgreSQL database.",
    )
    def test_query_against_migrated_postgres_with_timezone_ordering(self):
        engine = create_engine(os.environ["PENDING_TEST_DATABASE_URL"])
        self.addCleanup(engine.dispose)
        self.assertIn(engine.url.host, {"localhost", "127.0.0.1"})
        self.assertTrue(engine.url.database.startswith("scholarai_academic_test_"))
        with (
            engine.connect() as connection,
            connection.begin(),
            Session(bind=connection) as db,
        ):
            admin = User(
                full_name="Postgres admin",
                email="pending-pg@example.com",
                hashed_password="not-used",
                role="admin",
                is_email_verified=True,
            )
            db.add(admin)
            db.flush()
            token = create_access_token({"sub": str(admin.id), "role": "admin"})
            rows = [
                Scholarship(
                    source="for9a",
                    title="Older",
                    status="pending",
                    scraped_at=datetime.fromisoformat("2026-09-08T13:00:00+03:00"),
                ),
                Scholarship(
                    source="ministry",
                    title="Newer",
                    status="pending",
                    scraped_at=datetime.fromisoformat("2026-09-08T11:00:00+00:00"),
                ),
                Scholarship(source="for9a", title="Unknown date", status="pending"),
                Scholarship(source="manual", title="Manual", status="pending"),
                Scholarship(
                    source="for9a",
                    title="Reviewed",
                    status="pending",
                    reviewed_by="admin",
                ),
                Scholarship(source="ministry", title="Approved", status="approved"),
                Scholarship(source="ministry", title="Rejected", status="rejected"),
            ]
            db.add_all(rows)
            db.flush()

            def override_get_db():
                yield db

            app.dependency_overrides[get_db] = override_get_db
            response = self._get(token, limit=2)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total"], 3)
            self.assertEqual(
                [item["title"] for item in response.json()["items"]], ["Newer", "Older"]
            )
            self.assertEqual(
                [item["title"] for item in self._get(token).json()["items"]],
                ["Newer", "Older", "Unknown date"],
            )
            # Keep this integration test repeatable without changing persisted data.
            db.rollback()


if __name__ == "__main__":
    unittest.main()
