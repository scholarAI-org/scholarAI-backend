import json
import os
import sqlite3
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-admin-scholarship-edit")
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_converter("SCHOLARSHIP_ATTACHMENTS", json.loads)

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.Scholarship import Scholarship
from app.models.user import User
from app.services.audit import create_audit_log


class AdminScholarshipEditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={
                "check_same_thread": False,
                "detect_types": sqlite3.PARSE_DECLTYPES,
            },
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.session_factory = sessionmaker(bind=self.engine)
        # Match the existing SQLite fixtures for PostgreSQL's ARRAY column.
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "slug TEXT, organization_name TEXT, country TEXT, deadline TEXT, "
                    "no_deadline BOOLEAN DEFAULT 0, image_url TEXT, description_html TEXT, "
                    "apply_link TEXT, apply_email TEXT, apply_phone TEXT, pdf_url TEXT, "
                    "attachments SCHOLARSHIP_ATTACHMENTS, is_extension BOOLEAN DEFAULT 0, "
                    "source TEXT NOT NULL, source_id TEXT, source_url TEXT, study_level TEXT, "
                    "funding_type TEXT, majors JSON, required_documents JSON, "
                    "eligibility_criteria JSON, "
                    "status TEXT DEFAULT 'pending', scraped_at TEXT, "
                    "reviewed_at TEXT, reviewed_by TEXT, rejection_reason TEXT, "
                    "admin_id INTEGER, rejected_at TEXT, updated_at TEXT)"
                )
            )
        from app.models.auth_account import AuthAccount
        User.__table__.create(self.engine)
        AuthAccount.__table__.create(self.engine)
        AuditLog.__table__.create(self.engine)
        with self.session_factory() as db:
            admin = User(
                full_name="Admin",
                email="admin@example.com",
                hashed_password="unused",
                role="admin",
            )
            student = User(
                full_name="Student",
                email="student@example.com",
                hashed_password="unused",
                role="student",
            )
            db.add_all([admin, student])
            db.flush()
            self.admin_id = admin.id
            self.headers = {
                "Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"
            }
            self.student_headers = {
                "Authorization": f"Bearer {create_access_token({'sub': str(student.id)})}"
            }
            scholarship = Scholarship(
                title="Original scholarship",
                source="ministry",
                source_id="source-1",
                slug="original-scholarship",
                organization_name="Original organization",
                country="France",
                deadline=date(2027, 1, 1),
                description_html="<p>Original description</p>",
                source_url="https://example.com/source",
                apply_link="https://example.com/apply",
                image_url="https://example.com/image.jpg",
                status="pending",
                majors=["Physics"],
                required_documents=["CV"],
                scraped_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            )
            db.add(scholarship)
            db.commit()
            self.scholarship_id = scholarship.id
            self.original = self.snapshot(scholarship)
        self.url = f"/admin/scholarships/{self.scholarship_id}"

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    @staticmethod
    def snapshot(scholarship):
        return {
            column.name: getattr(scholarship, column.name)
            for column in Scholarship.__table__.columns
        }

    def assert_unchanged(self):
        with self.session_factory() as db:
            self.assertEqual(
                self.snapshot(db.get(Scholarship, self.scholarship_id)), self.original
            )
            self.assertEqual(db.query(AuditLog).count(), 0)

    def test_admin_partial_update_and_audit_only_actual_changes(self):
        response = self.client.patch(
            self.url,
            headers=self.headers,
            json={
                "title": "Updated scholarship",
                "country": "Germany",
                "organization_name": "Original organization",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["title"], "Updated scholarship")
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(response.json()["id"], self.scholarship_id)
        with self.session_factory() as db:
            scholarship = db.get(Scholarship, self.scholarship_id)
            for key, value in self.original.items():
                if key not in {"title", "country", "updated_at"}:
                    self.assertEqual(getattr(scholarship, key), value, key)
            self.assertGreater(scholarship.updated_at, self.original["updated_at"])
            log = db.query(AuditLog).one()
            self.assertEqual(log.admin_id, self.admin_id)
            self.assertEqual(log.admin_name, "Admin")
            self.assertEqual(log.action, "edit")
            self.assertEqual(log.entity_type, "scholarship")
            self.assertEqual(log.entity_id, self.scholarship_id)
            self.assertEqual(log.entity_name, "Updated scholarship")
            self.assertIsNotNone(log.created_at)
            self.assertEqual(
                log.details,
                {
                    "changes": {
                        "title": {
                            "old": "Original scholarship",
                            "new": "Updated scholarship",
                        },
                        "country": {"old": "France", "new": "Germany"},
                    }
                },
            )

    def test_dates_booleans_lists_and_explicit_null_keep_audit_types(self):
        response = self.client.patch(
            self.url,
            headers=self.headers,
            json={
                "deadline": "2027-02-01",
                "no_deadline": True,
                "majors": ["Math", "Physics"],
                "required_documents": "CV and transcript",
                "organization_name": None,
                "pdf_url": "https://example.com/info.pdf",
                "is_extension": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["organization_name"])
        with self.session_factory() as db:
            changes = db.query(AuditLog).one().details["changes"]
            self.assertEqual(
                changes["deadline"], {"old": "2027-01-01", "new": "2027-02-01"}
            )
            self.assertEqual(changes["no_deadline"], {"old": False, "new": True})
            self.assertEqual(
                changes["majors"], {"old": ["Physics"], "new": ["Math", "Physics"]}
            )
            self.assertEqual(
                changes["organization_name"],
                {"old": "Original organization", "new": None},
            )

    def test_empty_and_identical_payloads_do_not_write(self):
        for payload in (
            {},
            {"title": self.original["title"]},
            {"deadline": "2027-01-01", "majors": ["Physics"], "no_deadline": False},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    self.url, headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 200)
                self.assert_unchanged()

    def test_immutable_and_unknown_fields_are_rejected(self):
        for field in (
            "id",
            "source",
            "source_id",
            "slug",
            "created_at",
            "created_by",
            "updated_at",
            "scraped_at",
            "reviewed_at",
            "reviewed_by",
            "admin_id",
            "rejection_reason",
            "rejected_at",
            "status",
            "additional_details",
            "description",
        ):
            with self.subTest(field=field):
                response = self.client.patch(
                    self.url,
                    headers=self.headers,
                    json={"title": "Must not persist", field: 123},
                )
                self.assertEqual(response.status_code, 422)
                self.assert_unchanged()

    def test_invalid_payloads_are_rejected(self):
        for payload in (
            {"title": None},
            {"title": "x"},
            {"title": 123},
            {"deadline": "2027-02-30"},
            {"no_deadline": "maybe"},
            {"majors": {"invalid": True}},
            {"attachments": [123]},
            {"country": "x" * 101},
            {"apply_email": "x" * 256},
            {"apply_phone": "x" * 51},
            {"study_level": "x" * 101},
            {"funding_type": "x" * 101},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    self.url, headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 422)
                self.assert_unchanged()

    def test_authentication_and_authorization(self):
        for headers, expected in (
            ({}, 401),
            ({"Authorization": "Bearer invalid"}, 401),
            (self.student_headers, 403),
        ):
            with self.subTest(expected=expected):
                response = self.client.patch(
                    self.url, headers=headers, json={"title": "Updated"}
                )
                self.assertEqual(response.status_code, expected)
                self.assert_unchanged()

    def test_missing_scholarship_and_invalid_id(self):
        for path, expected in (
            ("/admin/scholarships/99999", 404),
            ("/admin/scholarships/invalid", 422),
        ):
            response = self.client.patch(
                path, headers=self.headers, json={"country": "Germany"}
            )
            self.assertEqual(response.status_code, expected)
        self.assert_unchanged()

    def test_non_pending_statuses_cannot_be_edited(self):
        for stored_status in ("approved", "rejected", "published", "draft", None):
            with self.subTest(status=stored_status):
                with self.session_factory() as db:
                    scholarship = db.get(Scholarship, self.scholarship_id)
                    scholarship.status = stored_status
                    db.commit()
                    self.original = self.snapshot(scholarship)
                for payload in ({"title": "Changed"}, {}):
                    response = self.client.patch(
                        self.url, headers=self.headers, json=payload
                    )
                    self.assertEqual(response.status_code, 409)
                    self.assert_unchanged()

    def test_database_update_failure_rolls_back_without_audit(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TRIGGER fail_edit BEFORE UPDATE ON scholarships "
                    "BEGIN SELECT RAISE(ABORT, 'private database update error'); END"
                )
            )
        with self.assertLogs("uvicorn.error", level="ERROR"):
            response = self.client.patch(
                self.url, headers=self.headers, json={"title": "Changed"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private database", response.text)
        self.assert_unchanged()

    def test_audit_insert_failure_rolls_back_flushed_scholarship(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs "
                    "BEGIN SELECT RAISE(ABORT, 'private database audit error'); END"
                )
            )

        def flush_then_audit(**kwargs):
            # Ensure UPDATE has reached the database before the failing audit INSERT.
            kwargs["db"].flush()
            return create_audit_log(**kwargs)

        with (
            patch(
                "app.services.admin_scholarship_edit.create_audit_log",
                side_effect=flush_then_audit,
            ),
            self.assertLogs("uvicorn.error", level="ERROR"),
        ):
            response = self.client.patch(
                self.url, headers=self.headers, json={"title": "Changed"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private database", response.text)
        self.assert_unchanged()

    def test_attachments_round_trip_and_no_change(self):
        attachments = [
            "https://example.com/first.pdf",
            "https://example.com/second.pdf",
        ]
        for _ in range(2):
            response = self.client.patch(
                self.url, headers=self.headers, json={"attachments": attachments}
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["attachments"], attachments)
        with self.session_factory() as db:
            log = db.query(AuditLog).one()
            self.assertEqual(
                log.details["changes"],
                {"attachments": {"old": None, "new": attachments}},
            )

    def test_audit_helper_failure_rolls_back(self):
        with (
            patch(
                "app.services.admin_scholarship_edit.create_audit_log",
                side_effect=RuntimeError("Audit unavailable"),
            ),
            self.assertRaisesRegex(RuntimeError, "Audit unavailable"),
        ):
            self.client.patch(self.url, headers=self.headers, json={"title": "Changed"})
        self.assert_unchanged()

    def test_failed_commit_rolls_back_both_records(self):
        def fail_commit(session):
            session.flush()
            raise RuntimeError("Commit unavailable")

        with (
            patch.object(self.session_factory.class_, "commit", fail_commit),
            self.assertRaisesRegex(RuntimeError, "Commit unavailable"),
        ):
            self.client.patch(self.url, headers=self.headers, json={"title": "Changed"})
        self.assert_unchanged()

    def test_long_title_fits_audit_name_without_losing_changed_value(self):
        title = "A" * 300
        response = self.client.patch(
            self.url, headers=self.headers, json={"title": title}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], title)
        with self.session_factory() as db:
            log = db.query(AuditLog).one()
            self.assertEqual(log.entity_name, title[:255])
            self.assertEqual(log.details["changes"]["title"]["new"], title)

    def test_edit_remains_compatible_with_review_and_publication(self):
        response = self.client.patch(
            self.url, headers=self.headers, json={"title": "Corrected title"}
        )
        self.assertEqual(response.status_code, 200)
        details = self.client.get(self.url, headers=self.headers)
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["title"], "Corrected title")
        approved = self.client.post(
            f"{self.url}/approve", headers=self.headers, json={}
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        # Preserve the legacy PUT contract, including its existing status policy.
        legacy = self.client.put(
            self.url, headers=self.headers, json={"country": "Germany"}
        )
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.json()["status"], "approved")

    def test_openapi_patch_contract(self):
        document = self.client.get("/openapi.json").json()
        operation = document["paths"]["/admin/scholarships/{scholarship_id}"]["patch"]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        schema = document["components"]["schemas"]["AdminScholarshipUpdate"]
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema.get("required"))
        self.assertNotIn("id", schema["properties"])
        self.assertNotIn("status", schema["properties"])
        for code in ("401", "403", "404", "409", "422"):
            self.assertIn(code, operation["responses"])


if __name__ == "__main__":
    unittest.main()
