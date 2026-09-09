import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-recommendations")

from app.core.database import get_db
from app.main import app


class RecommendationScholarshipsTests(unittest.TestCase):
    endpoint = "/api/scholarships/recommendations"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        session_factory = sessionmaker(bind=self.engine)
        # Only the feed columns are needed; PostgreSQL ARRAY fields are omitted.
        # Loading unrelated scholarship columns would fail these endpoint tests.
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE scholarships ("
                "id INTEGER PRIMARY KEY, title TEXT NOT NULL, slug VARCHAR(100), "
                "country VARCHAR(100), deadline DATE, description_html TEXT, "
                "apply_link TEXT, status VARCHAR(20))"
            ))

        def override_get_db():
            with session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _insert(self, scholarship_id=1, **overrides):
        values = {
            "id": scholarship_id,
            "title": f"Scholarship {scholarship_id}",
            "slug": f"scholarship-{scholarship_id}",
            "country": "Palestine",
            "deadline": "2026-10-01",
            "description_html": "<p>Full scholarship description.</p>",
            "apply_link": "https://example.com/apply",
            "status": "approved",
        }
        values.update(overrides)
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO scholarships (" + ", ".join(values) + ") VALUES ("
                + ", ".join(f":{key}" for key in values) + ")"
            ), values)

    def test_public_feed_returns_exact_required_fields(self):
        self._insert()
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{
            "id": 1,
            "title": "Scholarship 1",
            "slug": "scholarship-1",
            "country": "Palestine",
            "deadline": "2026-10-01",
            "description": "<p>Full scholarship description.</p>",
            "apply_link": "https://example.com/apply",
            "status": "approved",
        }])

    def test_all_statuses_are_returned_without_mapping(self):
        statuses = ("approved", "pending", "rejected", "archived", "published", "custom", "", None)
        for scholarship_id, stored_status in enumerate(
            statuses, start=1
        ):
            self._insert(scholarship_id, status=stored_status)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()], list(range(1, len(statuses) + 1))
        )
        self.assertEqual([item["status"] for item in response.json()], list(statuses))

    def test_nullable_fields_are_preserved(self):
        self._insert(**dict.fromkeys((
            "slug", "country", "deadline", "description_html", "apply_link"
        )))
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        item = response.json()[0]
        for field in ("slug", "country", "deadline", "description", "apply_link"):
            self.assertIsNone(item[field])

    def test_empty_database_returns_empty_list(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_all_rows_return_in_id_order_including_past_deadlines(self):
        for scholarship_id in range(110, 0, -1):
            self._insert(scholarship_id, deadline="2020-01-01")
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()], list(range(1, 111))
        )


if __name__ == "__main__":
    unittest.main()
