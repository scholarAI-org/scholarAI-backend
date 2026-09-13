import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "pending-review-test-key-at-least-32-bytes")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


class AdminPendingScholarshipsReviewTests(unittest.TestCase):
    endpoint = "/admin/scholarships/review"
    dashboard_endpoint = "/admin/dashboard/recent-pending-scholarships"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        self.session_factory = sessionmaker(bind=self.engine)
        # Keep only listing columns, so accidental full-model/detail loading fails.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                    "organization_name TEXT, country TEXT, deadline DATE, no_deadline BOOLEAN, "
                    "source TEXT NOT NULL, source_url TEXT, status TEXT, scraped_at TIMESTAMP, "
                    "reviewed_at TIMESTAMP, reviewed_by TEXT)"
                )
            )
        User.__table__.create(self.engine)
        with self.session_factory() as db:
            for role in ("admin", "student"):
                user = User(
                    full_name=role,
                    email=f"{role}@example.com",
                    hashed_password="x",
                    role=role,
                )
                db.add(user)
                db.flush()
                setattr(self, f"{role}_id", user.id)
                setattr(
                    self, f"{role}_token", create_access_token({"sub": str(user.id)})
                )
            db.commit()

        def override_get_db():
            with self.session_factory() as db:
                yield db

        previous = app.dependency_overrides.copy()
        self.addCleanup(self._restore_overrides, previous)
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _restore_overrides(self, previous):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    def _insert(self, row_id, **overrides):
        data = {
            "id": row_id,
            "title": f"Scholarship {row_id}",
            "organization_name": "Example University",
            "country": "Palestine",
            "deadline": "2026-10-01",
            "no_deadline": False,
            "source": "for9a",
            "source_url": "https://example.com/scholarship",
            "status": "pending",
            "scraped_at": "2026-09-09 10:00:00+00:00",
            "reviewed_at": None,
            "reviewed_by": None,
        }
        data.update(overrides)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO scholarships ("
                    + ", ".join(data)
                    + ") VALUES ("
                    + ", ".join(f":{key}" for key in data)
                    + ")"
                ),
                data,
            )

    def _get(self, **params):
        return self.client.get(
            self.endpoint,
            params=params,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )

    def test_only_pending_known_aggregator_sources_are_included(self):
        self._insert(1)
        self._insert(2, source="ministry")
        for row_id, source in enumerate(("manual", "admin", "unknown", ""), 3):
            self._insert(row_id, source=source)
        for row_id, stored_status in enumerate(
            ("approved", "rejected", "published", "PENDING", None), 7
        ):
            self._insert(row_id, status=stored_status)
        result = self._get().json()
        self.assertEqual(result["total"], 2)
        self.assertEqual([row["id"] for row in result["items"]], [2, 1])

    def test_pending_list_is_not_restricted_by_dashboard_review_metadata(self):
        self._insert(1, reviewed_at="2026-09-08 10:00:00+00:00")
        self._insert(2, reviewed_by="admin@example.com")
        self.assertEqual(self._get().json()["total"], 2)

    def test_newest_first_with_stable_ties_and_null_dates_last(self):
        self._insert(1, scraped_at="2026-09-09 12:00:00+00:00")
        self._insert(2, scraped_at="2026-09-08 12:00:00+00:00")
        self._insert(3, scraped_at="2026-09-09 12:00:00+00:00")
        self._insert(4, scraped_at=None)
        self._insert(5, scraped_at=None)
        ids = []
        for page in range(1, 4):
            response = self._get(page=page, page_size=2)
            self.assertEqual(response.status_code, 200)
            ids.extend(row["id"] for row in response.json()["items"])
        self.assertEqual(ids, [3, 1, 2, 5, 4])

    def test_default_pagination_and_last_page_metadata(self):
        for row_id in range(1, 46):
            self._insert(row_id)
        for page, expected_ids in (
            (1, list(range(45, 25, -1))),
            (2, list(range(25, 5, -1))),
            (3, list(range(5, 0, -1))),
            (4, []),
            (10**30, []),
        ):
            with self.subTest(page=page):
                response = self._get(page=page)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(
                    {
                        key: body[key]
                        for key in ("total", "page", "page_size", "total_pages")
                    },
                    {"total": 45, "page": page, "page_size": 20, "total_pages": 3},
                )
                self.assertEqual([row["id"] for row in body["items"]], expected_ids)
        for size in (1, 100):
            with self.subTest(page_size=size):
                body = self._get(page_size=size).json()
                self.assertEqual(len(body["items"]), min(size, 45))
                self.assertEqual(body["total_pages"], (45 + size - 1) // size)

    def test_empty_result(self):
        self._insert(1, source="manual")
        self.assertEqual(
            self._get().json(),
            {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0},
        )

    def test_nullable_table_fields(self):
        fields = (
            "organization_name",
            "country",
            "deadline",
            "no_deadline",
            "source_url",
            "scraped_at",
        )
        self._insert(1, **dict.fromkeys(fields))
        response = self._get()
        self.assertEqual(response.status_code, 200)
        for field in fields:
            self.assertIsNone(response.json()["items"][0][field])

    def test_pagination_validation(self):
        cases = [
            (name, value)
            for name in ("page", "page_size")
            for value in ("0", "-1", "abc", "1.5", "")
        ]
        cases.append(("page_size", "101"))
        for name, value in cases:
            with self.subTest(name=name, value=value):
                response = self._get(**{name: value})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"][0]["loc"], ["query", name])

    def test_admin_authorization_uses_stored_role(self):
        claimed_admin = create_access_token(
            {"sub": str(self.student_id), "role": "admin"}
        )
        for token, expected in (
            (None, 401),
            ("invalid", 401),
            (self.student_token, 403),
            (claimed_admin, 403),
        ):
            with self.subTest(expected=expected):
                response = self.client.get(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                )
                self.assertEqual(response.status_code, expected)

    def test_sql_paginates_without_loading_details_or_n_plus_one(self):
        for row_id in range(1, 6):
            self._insert(row_id)
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append((statement, parameters))

        event.listen(self.engine, "before_cursor_execute", record)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", record)
        self.assertEqual(self._get(page=2, page_size=2).status_code, 200)
        self.assertTrue(
            all(sql.lstrip().upper().startswith("SELECT") for sql, _ in statements)
        )
        queries = [
            (sql, params) for sql, params in statements if "FROM scholarships" in sql
        ]
        self.assertEqual(len(queries), 2)
        listing, params = next(
            (sql, params) for sql, params in queries if "count(" not in sql
        )
        self.assertIn("LIMIT", listing)
        self.assertIn("OFFSET", listing)
        self.assertEqual(params[-2:], (2, 2))
        self.assertNotIn("description_html", listing)
        self.assertNotIn("attachments", listing)

    def test_dashboard_latest_five_and_default_remain_unchanged(self):
        for row_id in range(1, 26):
            self._insert(row_id)
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        before = self.client.get(
            self.dashboard_endpoint, params={"limit": 5}, headers=headers
        ).json()
        review = self._get().json()
        self.assertEqual(len(review["items"]), 20)
        self.assertEqual(review["total"], 25)
        after = self.client.get(
            self.dashboard_endpoint, params={"limit": 5}, headers=headers
        ).json()
        self.assertEqual(before, after)
        self.assertEqual(set(after), {"items", "total"})
        self.assertEqual(after["total"], 25)
        self.assertEqual([row["id"] for row in after["items"]], [25, 24, 23, 22, 21])
        default = self.client.get(self.dashboard_endpoint, headers=headers).json()
        self.assertEqual(len(default["items"]), 10)

    def test_openapi_documents_pagination_auth_and_response(self):
        spec = app.openapi()
        operation = spec["paths"][self.endpoint]["get"]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        parameters = {
            param["name"]: param["schema"] for param in operation["parameters"]
        }
        self.assertEqual(parameters["page"]["default"], 1)
        self.assertEqual(parameters["page_size"]["default"], 20)
        self.assertEqual(parameters["page_size"]["maximum"], 100)
        self.assertEqual(parameters["status"]["default"], "pending")
        self.assertEqual(
            spec["components"]["schemas"]["ScholarshipReviewStatus"]["enum"],
            ["pending", "approved", "rejected"],
        )
        self.assertNotIn("issue_status", parameters)
        schema = spec["components"]["schemas"]["AdminScholarshipsReviewResponse"]
        self.assertEqual(
            set(schema["required"]),
            {"items", "total", "page", "page_size", "total_pages"},
        )

    def test_each_status_filters_items_and_pagination_totals(self):
        for offset, stored_status in enumerate(("pending", "approved", "rejected")):
            for index in range(1, 4):
                self._insert(offset * 10 + index, status=stored_status)
            self._insert(offset * 10 + 4, status=stored_status, source="manual")
            self._insert(offset * 10 + 5, status=stored_status, source="ministry")
        for offset, stored_status in enumerate(("pending", "approved", "rejected")):
            with self.subTest(status=stored_status):
                response = self._get(status=stored_status, page=2, page_size=3)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["total"], 4)
                self.assertEqual(body["total_pages"], 2)
                self.assertEqual(body["page"], 2)
                self.assertEqual(body["page_size"], 3)
                self.assertEqual(
                    [row["id"] for row in body["items"]], [offset * 10 + 1]
                )
                self.assertEqual(body["items"][0]["status"], stored_status)

    def test_status_with_no_matches_returns_successful_empty_page(self):
        self._insert(1)
        response = self._get(status="rejected")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0},
        )

    def test_invalid_status_uses_standard_enum_validation(self):
        for value in ("PENDING", "published", "unknown", "all", "", "pending,approved"):
            with self.subTest(status=value):
                response = self._get(status=value)
                self.assertEqual(response.status_code, 422)
                error = response.json()["detail"][0]
                self.assertEqual(error["loc"], ["query", "status"])
                self.assertEqual(error["type"], "enum")

    def test_review_table_response_has_exact_fields(self):
        self._insert(1)
        response = self._get()
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
                        "scraped_at": "2026-09-09T10:00:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "total_pages": 1,
            },
        )
