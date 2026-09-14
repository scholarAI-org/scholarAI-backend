import json
import os
import sqlite3
import unittest
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-review-details-only")

sqlite3.register_adapter(list, json.dumps)

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


class ScholarshipReviewDetailsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        factory = sessionmaker(bind=self.engine)
        User.__table__.create(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "title TEXT NOT NULL, "
                    "slug TEXT, "
                    "organization_name TEXT, "
                    "country TEXT, "
                    "study_level TEXT, "
                    "deadline DATE, "
                    "no_deadline BOOLEAN DEFAULT 0, "
                    "funding_type TEXT, "
                    "majors JSON, "
                    "eligibility_criteria JSON, "
                    "required_documents JSON, "
                    "image_url TEXT, "
                    "description_html TEXT, "
                    "apply_link TEXT, "
                    "apply_email TEXT, "
                    "apply_phone TEXT, "
                    "pdf_url TEXT, "
                    "attachments JSON, "
                    "is_extension BOOLEAN DEFAULT 0, "
                    "source TEXT NOT NULL, "
                    "source_id TEXT, "
                    "source_url TEXT, "
                    "status TEXT DEFAULT 'pending', "
                    "scraped_at TIMESTAMP, "
                    "reviewed_at TIMESTAMP, "
                    "reviewed_by TEXT, "
                    "rejection_reason TEXT, "
                    "admin_id INTEGER, "
                    "rejected_at TIMESTAMP, "
                    "updated_at TIMESTAMP"
                    ")"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO scholarships ("
                    "id, title, organization_name, country, study_level, deadline, no_deadline, "
                    "funding_type, majors, eligibility_criteria, required_documents, image_url, "
                    "description_html, apply_link, source, source_id, source_url, status, scraped_at"
                    ") VALUES ("
                    "1, "
                    "'منحة معهد العالم العربي للدراسات العليا', "
                    "'معهد العالم العربي', "
                    "'فرنسا', "
                    "'دراسات عليا', "
                    "'2026-11-20', "
                    "0, "
                    "'رسوم + منحة شهرية 800 يورو', "
                    "json('[\"العلوم الإنسانية\", \"الفنون\", \"العمارة\"]'), "
                    "json('[\"درجة جامعية في مجال ذي صلة\", \"إتقان الفرنسية أو الإنجليزية\", \"مشروع بحثي واضح\"]'), "
                    "json('[\"توصيتان\", \"مشروع بحث\", \"خطاب تحفيز\", \"كشف علامات\", \"سيرة ذاتية\"]'), "
                    "'https://example.com/cover.jpg', "
                    "'<p>منح دراسية كاملة لمتابعة دراسات عليا في معهد العالم العربي بباريس</p>', "
                    "'https://www.imarabe.org', "
                    "'for9a', "
                    "'for9a-ima-1', "
                    "'https://www.imarabe.org', "
                    "'pending', "
                    "'2026-08-10 10:00:00'"
                    "), ("
                    "2, "
                    "'Second scholarship', "
                    "'Second organization', "
                    "'Turkey', "
                    "'ماجستير', "
                    "'2027-01-15', "
                    "0, "
                    "'راتب شهري + رسوم', "
                    "json('[\"هندسة\", \"حاسوب\"]'), "
                    "NULL, "
                    "json('[\"خطاب دافع\", \"CV\"]'), "
                    "NULL, "
                    "'<p>Second</p>', "
                    "'https://example.com/apply', "
                    "'for9a', "
                    "'for9a-2', "
                    "'https://example.com/source', "
                    "'pending', "
                    "'2026-09-10 08:40:00'"
                    "), ("
                    "3, 'Missing details', NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, "
                    "NULL, NULL, NULL, 'for9a', 'for9a-3', NULL, 'pending', NULL"
                    ")"
                )
            )
        with factory() as db:
            db.add_all(
                [
                    User(
                        id=1,
                        full_name="Admin",
                        email="admin@example.com",
                        hashed_password="unused",
                        role="admin",
                    ),
                    User(
                        id=2,
                        full_name="Student",
                        email="student@example.com",
                        hashed_password="unused",
                        role="student",
                    ),
                ]
            )
            db.commit()

        def override_db():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.queries = []
        event.listen(self.engine, "before_cursor_execute", self.record_query)

    def record_query(self, conn, cursor, statement, parameters, context, executemany):
        self.queries.append(statement)

    def get_details(self, scholarship_id=1, user_id=1):
        # A claimed admin role must never override the actual user's stored role.
        token = create_access_token({"sub": str(user_id), "role": "admin"})
        return self.client.get(
            f"/admin/scholarships/{scholarship_id}/review-details",
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_admin_gets_all_review_details_for_requested_id(self):
        response = self.get_details(1)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["title"], "منحة معهد العالم العربي للدراسات العليا")
        self.assertEqual(data["organization_name"], "معهد العالم العربي")
        self.assertEqual(data["country"], "فرنسا")
        self.assertEqual(data["study_level"], "دراسات عليا")
        self.assertEqual(data["funding_type"], "رسوم + منحة شهرية 800 يورو")
        self.assertEqual(data["deadline"], "2026-11-20")
        self.assertEqual(data["no_deadline"], False)
        self.assertEqual(
            data["majors"], ["العلوم الإنسانية", "الفنون", "العمارة"]
        )
        self.assertEqual(
            data["eligibility_criteria"],
            [
                "درجة جامعية في مجال ذي صلة",
                "إتقان الفرنسية أو الإنجليزية",
                "مشروع بحثي واضح",
            ],
        )
        self.assertEqual(
            data["required_documents"],
            ["توصيتان", "مشروع بحث", "خطاب تحفيز", "كشف علامات", "سيرة ذاتية"],
        )
        self.assertEqual(
            data["description"],
            "<p>منح دراسية كاملة لمتابعة دراسات عليا في معهد العالم العربي بباريس</p>",
        )
        self.assertEqual(
            data["description_html"],
            "<p>منح دراسية كاملة لمتابعة دراسات عليا في معهد العالم العربي بباريس</p>",
        )
        self.assertEqual(data["source"], "for9a")
        self.assertEqual(data["source_url"], "https://www.imarabe.org")
        self.assertEqual(data["apply_link"], "https://www.imarabe.org")
        self.assertEqual(data["status"], "pending")

    def test_second_scholarship_review_details(self):
        response = self.get_details(2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Second scholarship")
        self.assertEqual(data["organization_name"], "Second organization")
        self.assertEqual(data["country"], "Turkey")
        self.assertEqual(data["study_level"], "ماجستير")
        self.assertEqual(data["funding_type"], "راتب شهري + رسوم")
        self.assertEqual(data["deadline"], "2027-01-15")
        self.assertEqual(data["majors"], ["هندسة", "حاسوب"])
        self.assertIsNone(data["eligibility_criteria"])
        self.assertEqual(data["required_documents"], ["خطاب دافع", "CV"])
        self.assertEqual(data["description"], "<p>Second</p>")
        self.assertEqual(data["status"], "pending")

    def test_null_values(self):
        response = self.get_details(3)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], 3)
        self.assertEqual(data["title"], "Missing details")
        self.assertIsNone(data["organization_name"])
        self.assertIsNone(data["country"])
        self.assertIsNone(data["study_level"])
        self.assertIsNone(data["funding_type"])
        self.assertIsNone(data["deadline"])
        self.assertIsNone(data["majors"])
        self.assertIsNone(data["eligibility_criteria"])
        self.assertIsNone(data["required_documents"])
        self.assertIsNone(data["description"])
        self.assertIsNone(data["description_html"])
        self.assertIsNone(data["additional_details"])

    def test_missing_scholarship(self):
        response = self.get_details(999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Scholarship not found"})

    def test_unauthenticated(self):
        response = self.client.get("/admin/scholarships/1/review-details")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.queries, [])

    def test_invalid_token(self):
        response = self.client.get(
            "/admin/scholarships/1/review-details",
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(response.status_code, 401)

    def test_student_rejected_even_with_admin_claim(self):
        for scholarship_id in (1, 999):
            self.assertEqual(
                self.get_details(scholarship_id, user_id=2).status_code, 403
            )
        self.assertFalse(any("scholarships" in query for query in self.queries))

    def test_single_scholarship_query(self):
        self.assertEqual(self.get_details().status_code, 200)
        self.assertEqual(sum("FROM scholarships" in query for query in self.queries), 1)

    def test_invalid_id(self):
        self.assertEqual(self.get_details("invalid").status_code, 422)

    def test_openapi_contract(self):
        from fastapi.openapi.models import OpenAPI

        schema = self.client.get("/openapi.json").json()
        OpenAPI.model_validate(schema)
        operation = schema["paths"][
            "/admin/scholarships/{scholarship_id}/review-details"
        ]["get"]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        self.assertEqual(
            [(p["name"], p["in"]) for p in operation["parameters"]],
            [("scholarship_id", "path")],
        )
        properties = schema["components"]["schemas"][
            "ScholarshipReviewDetailsResponse"
        ]["properties"]
        expected_fields = {
            "id",
            "title",
            "organization_name",
            "country",
            "study_level",
            "funding_type",
            "deadline",
            "no_deadline",
            "majors",
            "eligibility_criteria",
            "required_documents",
            "description",
            "description_html",
            "additional_details",
            "source",
            "source_id",
            "source_url",
            "apply_link",
            "apply_email",
            "apply_phone",
            "image_url",
            "pdf_url",
            "attachments",
            "is_extension",
            "status",
            "scraped_at",
            "reviewed_at",
            "reviewed_by",
            "rejection_reason",
            "admin_id",
            "rejected_at",
            "updated_at",
        }
        self.assertTrue(expected_fields <= set(properties))
        self.assertTrue(
            {"200", "401", "403", "404", "422"} <= set(operation["responses"])
        )
