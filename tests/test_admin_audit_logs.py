from datetime import datetime, timezone, timedelta
import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-audit-logs")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit import create_audit_log


class AdminAuditLogsEndpointTests(unittest.TestCase):
    endpoint = "/admin/dashboard/audit-logs"
    alias_endpoint = "/admin/audit-logs"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        User.__table__.create(self.engine)
        AuditLog.__table__.create(self.engine)

        def override_get_db():
            with self.Session() as db:
                yield db

        original_overrides = app.dependency_overrides.copy()
        self.addCleanup(self._restore_overrides, original_overrides)
        app.dependency_overrides[get_db] = override_get_db

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

        self.admin_id, self.admin_token = self._create_user("admin", "م. خالد النجار", "admin@example.com")
        self.student_id, self.student_token = self._create_user("student", "طالب تجريبي", "student@example.com")

    def _restore_overrides(self, overrides):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    def _create_user(self, role: str, full_name: str, email: str) -> tuple[int, str]:
        with self.Session() as db:
            user = User(
                full_name=full_name,
                email=email,
                hashed_password="hashed_pwd_test",
                role=role,
                is_active=True,
                is_email_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            token = create_access_token({"sub": str(user.id), "role": role})
            return user.id, token

    def _add_log(self, action: str, action_display: str, entity_name: str, created_at: datetime, admin_name: str = "م. خالد النجار") -> int:
        with self.Session() as db:
            log = AuditLog(
                admin_id=self.admin_id,
                admin_name=admin_name,
                action=action,
                action_display=action_display,
                entity_type="scholarship",
                entity_id=1,
                entity_name=entity_name,
                created_at=created_at,
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id

    def test_unauthenticated_request_returns_401(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 401)

    def test_student_request_returns_403(self):
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "This operation is restricted to administrators.")

    def test_empty_audit_logs(self):
        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)

    def test_audit_logs_ordering_newest_first(self):
        base_time = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
        self._add_log("publish", "اعتماد ونشر", "منحة إسطنبول التقنية", base_time + timedelta(hours=2))
        self._add_log("edit", "تعديل", "منحة جامعة النجاح", base_time + timedelta(hours=1))
        self._add_log("delete", "حذف", "منحة ملغاة", base_time)

        response = self.client.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["items"]), 3)

        # Newest first
        self.assertEqual(data["items"][0]["entity_name"], "منحة إسطنبول التقنية")
        self.assertEqual(data["items"][0]["action"], "publish")
        self.assertEqual(data["items"][0]["action_display"], "اعتماد ونشر")

        self.assertEqual(data["items"][1]["entity_name"], "منحة جامعة النجاح")
        self.assertEqual(data["items"][1]["action"], "edit")
        self.assertEqual(data["items"][1]["action_display"], "تعديل")

        self.assertEqual(data["items"][2]["entity_name"], "منحة ملغاة")
        self.assertEqual(data["items"][2]["action"], "delete")
        self.assertEqual(data["items"][2]["action_display"], "حذف")

    def test_pagination_limit_and_offset(self):
        base_time = datetime(2026, 9, 9, 8, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            self._add_log("edit", "تعديل", f"منحة رقم {i}", base_time + timedelta(minutes=i))

        response = self.client.get(
            f"{self.endpoint}?limit=2&offset=0",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["entity_name"], "منحة رقم 4")

        # Offset page 2
        response_page2 = self.client.get(
            f"{self.endpoint}?limit=2&offset=2",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        data_page2 = response_page2.json()
        self.assertEqual(data_page2["total"], 5)
        self.assertEqual(len(data_page2["items"]), 2)
        self.assertEqual(data_page2["items"][0]["entity_name"], "منحة رقم 2")

    def test_filter_by_action(self):
        base_time = datetime(2026, 9, 9, 9, 0, 0, tzinfo=timezone.utc)
        self._add_log("publish", "اعتماد ونشر", "منحة 1", base_time)
        self._add_log("edit", "تعديل", "منحة 2", base_time + timedelta(minutes=1))
        self._add_log("publish", "اعتماد ونشر", "منحة 3", base_time + timedelta(minutes=2))

        response = self.client.get(
            f"{self.endpoint}?action=publish",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertTrue(all(item["action"] == "publish" for item in data["items"]))

    def test_alias_endpoint(self):
        base_time = datetime(2026, 9, 9, 9, 0, 0, tzinfo=timezone.utc)
        self._add_log("delete", "حذف", "منحة محذوفة", base_time)

        response = self.client.get(
            self.alias_endpoint,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["entity_name"], "منحة محذوفة")

    def test_service_create_audit_log_helper(self):
        with self.Session() as db:
            admin_user = db.query(User).filter(User.id == self.admin_id).first()
            log = create_audit_log(
                db=db,
                admin=admin_user,
                action="publish",
                entity_name="منحة تجريبية عبر الخدمة",
                entity_id=10,
            )
            self.assertEqual(log.action, "publish")
            self.assertEqual(log.action_display, "اعتماد ونشر")
            self.assertEqual(log.admin_name, "م. خالد النجار")
            self.assertEqual(log.entity_name, "منحة تجريبية عبر الخدمة")


if __name__ == "__main__":
    unittest.main()
