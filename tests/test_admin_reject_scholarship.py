import json
import os
import sqlite3
import unittest
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-reject-scholarship")

sqlite3.register_adapter(list, json.dumps)

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.Scholarship import Scholarship
from app.models.user import User


class AdminRejectScholarshipTests(unittest.TestCase):
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
                    "study_level TEXT, "
                    "deadline DATE, "
                    "no_deadline BOOLEAN DEFAULT 0, "
                    "funding_type TEXT, "
                    "majors JSON, "
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
                full_name="طالب مسجل",
                email="student@scholarai.com",
                hashed_password="mock-hashed-password",
                role="student",
            )
            db.add_all([self.admin, self.student])
            db.flush()

            self.admin_id = self.admin.id
            self.admin_token = create_access_token({"sub": str(self.admin.id)})
            self.student_token = create_access_token({"sub": str(self.student.id)})

            # 1. Pending scholarship to reject
            self.pending_sch = Scholarship(
                title="منحة جامعة إسطنبول التقنية المعلقة",
                organization_name="ITU",
                country="تركيا",
                study_level="ماجستير",
                deadline=date(2027, 1, 15),
                source="for9a",
                source_id="for9a-rej-1",
                source_url="https://itu.edu.tr/tr/burslar",
                status="pending",
                scraped_at=datetime(2026, 9, 10, 8, 40, tzinfo=timezone.utc),
            )

            # 2. Already rejected scholarship
            self.already_rejected_sch = Scholarship(
                title="منحة مرفوضة مسبقاً",
                organization_name="جامعة أنقرة",
                country="تركيا",
                source="ministry",
                source_id="min-rej-2",
                status="rejected",
                rejection_reason="الرابط لا يعمل والمنحة وهمية",
                admin_id=self.admin_id,
                rejected_at=datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc),
            )

            # 3. Approved scholarship to revoke/reject
            self.approved_sch = Scholarship(
                title="منحة منشورة يراد إلغاؤها ورفضها",
                organization_name="جامعة أكسفورد",
                country="بريطانيا",
                deadline=date(2026, 11, 30),
                source="for9a",
                source_id="for9a-ox-3",
                source_url="https://ox.ac.uk",
                apply_link="https://ox.ac.uk/apply",
                image_url="https://ox.ac.uk/cover.jpg",
                status="approved",
            )

            db.add_all([self.pending_sch, self.already_rejected_sch, self.approved_sch])
            db.commit()

            self.pending_id = self.pending_sch.id
            self.already_rejected_id = self.already_rejected_sch.id
            self.approved_id = self.approved_sch.id

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_reject_pending_scholarship_success(self):
        payload = {"reason": "رابط المصدر معطل ومعلومات المنحة غير موثوقة"}
        response = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["rejection_reason"], "رابط المصدر معطل ومعلومات المنحة غير موثوقة")
        self.assertEqual(data["admin_id"], self.admin_id)
        self.assertEqual(data["reviewed_by"], "admin@scholarai.com")
        self.assertIsNotNone(data["rejected_at"])
        self.assertIsNotNone(data["updated_at"])
        self.assertIsNotNone(data["audit_log_id"])
        self.assertIn("رفض وأرشفة", data["message"])

        # Verify in DB
        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.pending_id).first()
            self.assertEqual(sch.status, "rejected")
            self.assertEqual(sch.rejection_reason, "رابط المصدر معطل ومعلومات المنحة غير موثوقة")
            self.assertEqual(sch.admin_id, self.admin_id)
            self.assertEqual(sch.reviewed_by, "admin@scholarai.com")
            self.assertIsNotNone(sch.rejected_at)
            self.assertIsNotNone(sch.reviewed_at)
            self.assertIsNotNone(sch.updated_at)

            # Verify audit log
            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.pending_id, AuditLog.action == "reject")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "رفض")
            self.assertEqual(log.entity_name, "منحة جامعة إسطنبول التقنية المعلقة")
            self.assertEqual(log.admin_id, self.admin_id)
            self.assertEqual(log.details["reason"], "رابط المصدر معطل ومعلومات المنحة غير موثوقة")
            self.assertEqual(log.details["old_status"], "pending")
            self.assertEqual(log.details["new_status"], "rejected")

    def test_reject_without_reason_fails_422(self):
        # 1. Empty string
        res1 = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json={"reason": ""},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res1.status_code, 422)

        # 2. Whitespace only
        res2 = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json={"reason": "   "},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res2.status_code, 422)

        # 3. Missing reason key
        res3 = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json={},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res3.status_code, 422)

        # 4. Less than 3 characters
        res4 = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json={"reason": "ab"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res4.status_code, 422)

    def test_reject_already_rejected_scholarship_fails_409(self):
        response = self.client.post(
            f"/admin/scholarships/{self.already_rejected_id}/reject",
            json={"reason": "محاولة رفض منحة مرفوضة مرة أخرى"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("مرفوضة بالفعل", response.json()["detail"])

    def test_reject_approved_scholarship_success(self):
        payload = {"reason": "تم إلغاء المنحة بسبب اكتشاف شروط احتيالية على موقع الجهة"}
        response = self.client.post(
            f"/admin/scholarships/{self.approved_id}/reject",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "rejected")

        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.approved_id).first()
            self.assertEqual(sch.status, "rejected")
            self.assertEqual(sch.rejection_reason, payload["reason"])
            self.assertEqual(sch.admin_id, self.admin_id)

            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == self.approved_id, AuditLog.action == "reject")
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.details["old_status"], "approved")
            self.assertEqual(log.details["new_status"], "rejected")

    def test_modal_detail_endpoint_returns_rejection_data(self):
        # 1. Check detail for already rejected scholarship
        response = self.client.get(
            f"/admin/scholarships/{self.already_rejected_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["rejection_reason"], "الرابط لا يعمل والمنحة وهمية")
        self.assertEqual(data["admin_id"], self.admin_id)
        self.assertIsNotNone(data["rejected_at"])

    def test_soft_delete_alias_endpoint_success(self):
        payload = {"reason": "أرشفة منحة منتهية الموعد النهائي بواسطة زر رفض / حذف"}
        response = self.client.post(
            f"/admin/scholarships/{self.pending_id}/soft-delete",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "rejected")
        self.assertEqual(response.json()["rejection_reason"], payload["reason"])

    def test_reject_permissions(self):
        payload = {"reason": "سبب رفض اختباري"}

        # 401 unauthenticated
        res_no_auth = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json=payload,
        )
        self.assertEqual(res_no_auth.status_code, 401)

        # 403 student
        res_student = self.client.post(
            f"/admin/scholarships/{self.pending_id}/reject",
            json=payload,
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(res_student.status_code, 403)

        # 404 not found
        res_404 = self.client.post(
            "/admin/scholarships/999999/reject",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
