import os
import unittest
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-audit-logging-actions-key")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.Scholarship import Scholarship
from app.models.user import User


import json
import sqlite3

sqlite3.register_adapter(list, json.dumps)


class AdminAuditLoggingActionsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        self.session_factory = sessionmaker(bind=self.engine)

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "title TEXT NOT NULL, "
                    "slug TEXT, "
                    "organization_name TEXT, "
                    "country TEXT, "
                    "deadline DATE, "
                    "no_deadline BOOLEAN DEFAULT 0, "
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
                    "study_level TEXT, "
                    "funding_type TEXT, "
                    "majors JSON, "
                    "required_documents JSON, "
                    "status TEXT DEFAULT 'pending', "
                    "scraped_at TIMESTAMP, "
                    "reviewed_at TIMESTAMP, "
                    "reviewed_by TEXT, "
                    "updated_at TIMESTAMP"
                    ")"
                )
            )

        User.__table__.create(self.engine)
        AuditLog.__table__.create(self.engine)

        with self.session_factory() as db:
            self.admin = User(
                full_name="م. خالد النجار",
                email="admin@scholarai.com",
                hashed_password="mock-hashed-password",
                role="admin",
            )
            self.student = User(
                full_name="طالب مجتهد",
                email="student@scholarai.com",
                hashed_password="mock-hashed-password",
                role="student",
            )
            db.add_all([self.admin, self.student])
            db.flush()

            self.admin_id = self.admin.id
            self.admin_name = self.admin.full_name
            self.admin_token = create_access_token({"sub": str(self.admin.id)})
            self.student_token = create_access_token({"sub": str(self.student.id)})

            # Seed a pending scholarship
            self.scholarship = Scholarship(
                title="منحة جامعة النجاح",
                organization_name="جامعة النجاح الوطنية",
                country="فلسطين",
                source="for9a",
                source_id="for9a-najah-1",
                status="pending",
                scraped_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            )
            db.add(self.scholarship)
            db.commit()
            self.scholarship_id = self.scholarship.id

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_create_scholarship_records_audit_log(self):
        payload = {
            "title": "منحة إسطنبول التقنية",
            "source": "ministry",
            "source_id": "min-itu-100",
            "country": "تركيا",
            "organization_name": "جامعة إسطنبول التقنية",
            "status": "pending",
        }
        response = self.client.post(
            "/api/scholarships/",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 201)
        created_id = response.json()["id"]

        with self.session_factory() as db:
            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == created_id, AuditLog.action == "create")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.admin_id, self.admin_id)
            self.assertEqual(log.admin_name, self.admin_name)
            self.assertEqual(log.action_display, "إضافة منحة")
            self.assertEqual(log.entity_name, "منحة إسطنبول التقنية")

    def test_update_scholarship_records_audit_log(self):
        update_payload = {
            "title": "منحة جامعة النجاح - محدثة",
            "country": "فلسطين المحتلة",
        }
        response = self.client.put(
            f"/admin/scholarships/{self.scholarship_id}",
            json=update_payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "منحة جامعة النجاح - محدثة")

        with self.session_factory() as db:
            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.scholarship_id, AuditLog.action == "edit")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "تعديل")
            self.assertEqual(log.entity_name, "منحة جامعة النجاح - محدثة")
            self.assertIn("changes", log.details)
            self.assertIn("title", log.details["changes"])
            self.assertEqual(log.details["changes"]["title"]["old"], "منحة جامعة النجاح")
            self.assertEqual(log.details["changes"]["title"]["new"], "منحة جامعة النجاح - محدثة")

    def test_change_status_to_approved_records_publish_audit_log(self):
        response = self.client.patch(
            f"/admin/scholarships/{self.scholarship_id}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "approved")
        self.assertIn("اعتماد ونشر", data["message"])

        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.scholarship_id).first()
            self.assertEqual(sch.status, "approved")
            self.assertIsNotNone(sch.reviewed_at)
            self.assertEqual(sch.reviewed_by, "admin@scholarai.com")

            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.scholarship_id, AuditLog.action == "publish")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "اعتماد ونشر")
            self.assertEqual(log.details["old_status"], "pending")
            self.assertEqual(log.details["new_status"], "approved")

    def test_change_status_to_rejected_records_reject_audit_log(self):
        response = self.client.patch(
            f"/admin/scholarships/{self.scholarship_id}/status",
            json={"status": "rejected", "reason": "منحة مصدر غير موثوق"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "rejected")

        with self.session_factory() as db:
            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.scholarship_id, AuditLog.action == "reject")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "رفض")
            self.assertEqual(log.details["reason"], "منحة مصدر غير موثوق")

    def test_delete_scholarship_records_audit_log(self):
        response = self.client.delete(
            f"/admin/scholarships/{self.scholarship_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)

        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.scholarship_id).first()
            self.assertIsNone(sch)

            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.scholarship_id, AuditLog.action == "delete")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "حذف")
            self.assertEqual(log.entity_name, "منحة جامعة النجاح")

    def test_audit_logs_dashboard_feed_integration(self):
        # 1. Edit
        self.client.put(
            f"/admin/scholarships/{self.scholarship_id}",
            json={"title": "منحة جامعة النجاح المعدلة"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        # 2. Approve
        self.client.patch(
            f"/admin/scholarships/{self.scholarship_id}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )

        # 3. Read audit logs feed
        response = self.client.get(
            "/admin/dashboard/audit-logs",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        logs = response.json()["items"]
        self.assertGreaterEqual(len(logs), 2)
        # Newest first
        self.assertEqual(logs[0]["action"], "publish")
        self.assertEqual(logs[0]["action_display"], "اعتماد ونشر")
        self.assertEqual(logs[1]["action"], "edit")
        self.assertEqual(logs[1]["action_display"], "تعديل")

    def test_action_endpoints_permissions(self):
        # 401 when no token
        res_no_auth = self.client.put(
            f"/admin/scholarships/{self.scholarship_id}", json={"title": "test"}
        )
        self.assertEqual(res_no_auth.status_code, 401)

        # 403 when student token
        res_forbidden = self.client.put(
            f"/admin/scholarships/{self.scholarship_id}",
            json={"title": "test"},
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(res_forbidden.status_code, 403)

        res_delete_forbidden = self.client.delete(
            f"/admin/scholarships/{self.scholarship_id}",
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(res_delete_forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
