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
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-approve-scholarship")

sqlite3.register_adapter(list, json.dumps)

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.Scholarship import Scholarship
from app.models.user import User


class AdminApproveScholarshipTests(unittest.TestCase):
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
            self.admin_name = self.admin.full_name
            self.admin_token = create_access_token({"sub": str(self.admin.id)})
            self.student_token = create_access_token({"sub": str(self.student.id)})

            # 1. Complete pending scholarship
            self.pending_complete = Scholarship(
                title="منحة جامعة إسطنبول التقنية",
                organization_name="ITU",
                country="تركيا",
                study_level="ماجستير",
                deadline=date(2027, 1, 15),
                no_deadline=False,
                funding_type="راتب شهري + رسوم",
                majors=["هندسة", "حاسوب"],
                required_documents=["خطاب دافع", "CV"],
                scraped_at=datetime(2026, 9, 10, 8, 40, tzinfo=timezone.utc),
                source="for9a",
                source_id="for9a-itu-1",
                source_url="https://itu.edu.tr/tr/burslar",
                apply_link="https://itu.edu.tr/tr/burslar",
                image_url="https://example.com/image.png",
                status="pending",
            )

            # 2. Incomplete pending scholarship (missing image_url and apply_link)
            self.pending_incomplete = Scholarship(
                title="منحة ناقصة الروابط",
                organization_name="جامعة أنقرة",
                country="تركيا",
                deadline=date(2026, 12, 1),
                source="ministry",
                source_id="min-ank-2",
                source_url="https://ankara.edu.tr",
                apply_link=None,
                image_url=None,
                status="pending",
            )

            # 3. Already approved scholarship
            self.already_approved = Scholarship(
                title="منحة منشورة مسبقاً",
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

            # 4. Rejected scholarship
            self.rejected_scholarship = Scholarship(
                title="منحة مرفوضة",
                organization_name="جهة غير موثوقة",
                country="دولة مجهولة",
                source="ministry",
                source_id="min-rej-4",
                status="rejected",
            )

            db.add_all(
                [
                    self.pending_complete,
                    self.pending_incomplete,
                    self.already_approved,
                    self.rejected_scholarship,
                ]
            )
            db.commit()

            self.pending_complete_id = self.pending_complete.id
            self.pending_incomplete_id = self.pending_incomplete.id
            self.already_approved_id = self.already_approved.id
            self.rejected_id = self.rejected_scholarship.id

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_get_scholarship_detail_for_modal(self):
        response = self.client.get(
            f"/admin/scholarships/{self.pending_complete_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "منحة جامعة إسطنبول التقنية")
        self.assertEqual(data["organization_name"], "ITU")
        self.assertEqual(data["country"], "تركيا")
        self.assertEqual(data["study_level"], "ماجستير")
        self.assertEqual(data["funding_type"], "راتب شهري + رسوم")
        self.assertEqual(data["majors"], ["هندسة", "حاسوب"])
        self.assertEqual(data["required_documents"], ["خطاب دافع", "CV"])
        self.assertEqual(data["source_url"], "https://itu.edu.tr/tr/burslar")
        self.assertEqual(data["apply_link"], "https://itu.edu.tr/tr/burslar")
        self.assertEqual(data["image_url"], "https://example.com/image.png")
        self.assertEqual(data["status"], "pending")

    def test_approve_scholarship_success(self):
        response = self.client.post(
            f"/admin/scholarships/{self.pending_complete_id}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "approved")
        self.assertTrue(data["is_published"])
        self.assertEqual(data["reviewed_by"], "admin@scholarai.com")
        self.assertIsNotNone(data["reviewed_at"])
        self.assertIsNotNone(data["updated_at"])
        self.assertIn("اعتماد ونشر", data["message"])

        # Check DB updates
        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.pending_complete_id).first()
            self.assertEqual(sch.status, "approved")
            self.assertEqual(sch.reviewed_by, "admin@scholarai.com")
            self.assertIsNotNone(sch.reviewed_at)
            self.assertIsNotNone(sch.updated_at)

            # Check audit log
            log = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_id == self.pending_complete_id,
                    AuditLog.action == "publish",
                )
                .first()
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.action_display, "اعتماد ونشر")
            self.assertEqual(log.entity_name, "منحة جامعة إسطنبول التقنية")

    def test_approve_with_modal_inputs_payload(self):
        payload = {
            "apply_link": "https://ankara.edu.tr/apply-now",
            "image_url": "https://ankara.edu.tr/images/scholarship.png",
            "study_level": "بكالوريوس",
            "funding_type": "ممولة بالكامل",
            "notes": "تم تدقيق الروابط والتحقق من التخصصات بواسطة الإدارة",
        }
        response = self.client.post(
            f"/admin/scholarships/{self.pending_incomplete_id}/approve",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "approved")

        with self.session_factory() as db:
            sch = db.query(Scholarship).filter(Scholarship.id == self.pending_incomplete_id).first()
            self.assertEqual(sch.status, "approved")
            self.assertEqual(sch.apply_link, "https://ankara.edu.tr/apply-now")
            self.assertEqual(sch.image_url, "https://ankara.edu.tr/images/scholarship.png")
            self.assertEqual(sch.study_level, "بكالوريوس")

            # Check audit log notes
            log = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_id == self.pending_incomplete_id,
                    AuditLog.action == "publish",
                )
                .first()
            )
            self.assertIsNotNone(log)
            self.assertIn("notes", log.details)
            self.assertEqual(log.details["notes"], "تم تدقيق الروابط والتحقق من التخصصات بواسطة الإدارة")

    def test_validation_error_on_missing_mandatory_fields(self):
        # pending_incomplete has no apply_link and no image_url
        response = self.client.post(
            f"/admin/scholarships/{self.pending_incomplete_id}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertIn("errors", detail)
        errors = detail["errors"]
        self.assertTrue(any("apply_link" in e for e in errors))
        self.assertTrue(any("image_url" in e for e in errors))

    def test_validation_error_on_invalid_url_format(self):
        payload = {
            "apply_link": "ftp://invalid-protocol.com",
            "image_url": "not-a-valid-url-at-all",
        }
        response = self.client.post(
            f"/admin/scholarships/{self.pending_incomplete_id}/approve",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 422)

    def test_conflict_when_already_approved(self):
        response = self.client.post(
            f"/admin/scholarships/{self.already_approved_id}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("معتمدة ومنشورة بالفعل", response.json()["detail"])

    def test_bad_request_when_rejected(self):
        response = self.client.post(
            f"/admin/scholarships/{self.rejected_id}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ليست قيد المراجعة", response.json()["detail"])

    def test_alias_publish_endpoint(self):
        # Same operation via /publish alias
        response = self.client.post(
            f"/admin/scholarships/{self.pending_complete_id}/publish",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")

    def test_permissions(self):
        # 401 unauthenticated
        res_no_auth = self.client.post(f"/admin/scholarships/{self.pending_complete_id}/approve")
        self.assertEqual(res_no_auth.status_code, 401)

        # 403 student
        res_student = self.client.post(
            f"/admin/scholarships/{self.pending_complete_id}/approve",
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(res_student.status_code, 403)

        # 404 not found
        res_404 = self.client.post(
            "/admin/scholarships/999999/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
