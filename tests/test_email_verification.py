import os
import importlib.util
import unittest
from unittest.mock import patch
from datetime import UTC, datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-email-verification")

from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_api
from app.core import mailer
from app.core.config import settings
from app.core.database import get_db
from app.core.mailer import EmailDeliveryError
from app.core.security import create_reset_token
from app.main import app
from app.models.profile import Profile
from app.models.user import User


class EmailVerificationFlowTests(unittest.TestCase):
    @staticmethod
    def utc_now_naive() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(
            bind=cls.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.original_email_sender = auth_api.send_verification_otp_email
        cls.original_email_verification_enabled = settings.EMAIL_VERIFICATION_ENABLED

    @classmethod
    def tearDownClass(cls):
        auth_api.send_verification_otp_email = cls.original_email_sender
        settings.EMAIL_VERIFICATION_ENABLED = cls.original_email_verification_enabled
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        settings.EMAIL_VERIFICATION_ENABLED = True
        Profile.__table__.drop(self.engine, checkfirst=True)
        User.__table__.drop(self.engine, checkfirst=True)
        User.__table__.create(self.engine)
        Profile.__table__.create(self.engine)
        self.mailbox: list[tuple[str, str]] = []
        auth_api.send_verification_otp_email = (
            lambda email, otp: self.mailbox.append((email, otp))
        )

    def register(self, email: str = "user@example.com"):
        return self.client.post(
            "/auth/register",
            json={
                "full_name": "Test User",
                "email": email,
                "password": "Pass123!",
            },
        )

    def get_user(self, email: str = "user@example.com") -> User:
        with self.Session() as db:
            return db.query(User).filter(User.email == email).one()

    def register_and_verify(self) -> str:
        self.assertEqual(self.register().status_code, 201)
        otp = self.mailbox[-1][1]
        response = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": otp},
        )
        self.assertEqual(response.status_code, 200)
        login = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Pass123!"},
        )
        self.assertEqual(login.status_code, 200)
        return login.json()["access_token"]

    def test_register_creates_unverified_user_and_sends_hashed_otp(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {"message": "Registration successful. Verification OTP sent to your email."},
        )
        self.assertEqual(len(self.mailbox), 1)
        email, otp = self.mailbox[0]
        self.assertEqual(email, "user@example.com")
        self.assertRegex(otp, r"^\d{6}$")

        user = self.get_user()
        self.assertFalse(user.is_email_verified)
        self.assertNotEqual(user.email_verification_otp_hash, otp)
        self.assertGreater(user.email_verification_otp_expires_at, self.utc_now_naive())
        with self.Session() as db:
            profile = db.query(Profile).filter(Profile.user_id == user.id).one()
            self.assertEqual(profile.user_id, user.id)

    def test_registration_and_login_skip_otp_when_verification_is_disabled(self):
        settings.EMAIL_VERIFICATION_ENABLED = False

        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"message": "Registration successful."})
        self.assertEqual(self.mailbox, [])

        user = self.get_user()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_otp_hash)

        login = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Pass123!"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access_token", login.json())

    def test_unverified_user_cannot_login_then_can_login_after_verification(self):
        self.register()
        otp = self.mailbox[-1][1]

        blocked = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Pass123!"},
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["detail"], "Email verification required")

        verified = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": otp},
        )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json(), {"message": "Email verified successfully"})

        user = self.get_user()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_otp_hash)
        self.assertIsNone(user.email_verification_otp_expires_at)

        reused = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": otp},
        )
        self.assertEqual(reused.status_code, 400)
        self.assertIsNone(self.get_user().email_verification_otp_hash)

        login = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Pass123!"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access_token", login.json())

    def test_wrong_and_expired_otp_fail(self):
        self.register()

        wrong = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": "000000"},
        )
        self.assertEqual(wrong.status_code, 400)

        with self.Session() as db:
            user = db.query(User).filter(User.email == "user@example.com").one()
            user.email_verification_otp_expires_at = self.utc_now_naive() - timedelta(seconds=1)
            db.commit()

        expired = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": self.mailbox[-1][1]},
        )
        self.assertEqual(expired.status_code, 400)
        self.assertIsNone(self.get_user().email_verification_otp_hash)

    def test_resend_replaces_old_otp_and_new_otp_works(self):
        self.register()
        old_otp = self.mailbox[-1][1]

        with self.Session() as db:
            user = db.query(User).filter(User.email == "user@example.com").one()
            user.email_verification_otp_sent_at = self.utc_now_naive() - timedelta(seconds=61)
            db.commit()

        resent = self.client.post(
            "/auth/resend-verification-otp",
            json={"email": "user@example.com"},
        )
        self.assertEqual(resent.status_code, 200)
        new_otp = self.mailbox[-1][1]
        self.assertNotEqual(old_otp, new_otp)

        old_result = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": old_otp},
        )
        self.assertEqual(old_result.status_code, 400)

        new_result = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": new_otp},
        )
        self.assertEqual(new_result.status_code, 200)

    def test_resend_is_rate_limited_and_verified_user_gets_no_new_otp(self):
        self.register()
        otp = self.mailbox[-1][1]

        limited = self.client.post(
            "/auth/resend-verification-otp",
            json={"email": "user@example.com"},
        )
        self.assertEqual(limited.status_code, 429)
        self.assertIn("retry-after", limited.headers)

        self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": otp},
        )
        sent_count = len(self.mailbox)
        already_verified = self.client.post(
            "/auth/resend-verification-otp",
            json={"email": "user@example.com"},
        )
        self.assertEqual(already_verified.status_code, 200)
        self.assertEqual(already_verified.json(), {"message": "Email is already verified"})
        self.assertEqual(len(self.mailbox), sent_count)

    def test_invalid_input_unknown_email_and_registration_cooldown(self):
        invalid_email = self.client.post(
            "/auth/verify-email",
            json={"email": "not-an-email", "otp": "123456"},
        )
        invalid_otp = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": "12345a"},
        )
        unknown = self.client.post(
            "/auth/verify-email",
            json={"email": "unknown@example.com", "otp": "123456"},
        )
        self.assertEqual(invalid_email.status_code, 422)
        self.assertEqual(invalid_otp.status_code, 422)
        self.assertEqual(unknown.status_code, 400)

        self.assertEqual(self.register().status_code, 201)
        repeated = self.register()
        self.assertEqual(repeated.status_code, 429)
        self.assertIn("retry-after", repeated.headers)

        unknown_resend = self.client.post(
            "/auth/resend-verification-otp",
            json={"email": "missing@example.com"},
        )
        self.assertEqual(unknown_resend.status_code, 200)

    def test_reregister_unverified_user_resends_without_duplicate(self):
        self.assertEqual(self.register().status_code, 201)
        old_otp = self.mailbox[-1][1]

        with self.Session() as db:
            user = db.query(User).filter(User.email == "user@example.com").one()
            user.email_verification_otp_sent_at = self.utc_now_naive() - timedelta(seconds=61)
            db.commit()

        repeated = self.register()
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(len(self.mailbox), 2)
        new_otp = self.mailbox[-1][1]
        self.assertNotEqual(old_otp, new_otp)

        with self.Session() as db:
            count = db.query(User).filter(User.email == "user@example.com").count()
        self.assertEqual(count, 1)

        old_result = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": old_otp},
        )
        self.assertEqual(old_result.status_code, 400)
        new_result = self.client.post(
            "/auth/verify-email",
            json={"email": "user@example.com", "otp": new_otp},
        )
        self.assertEqual(new_result.status_code, 200)

    def test_verified_email_cannot_register_again(self):
        self.register_and_verify()
        sent_count = len(self.mailbox)

        repeated = self.register()

        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(repeated.json()["detail"], "Email already registered")
        self.assertEqual(len(self.mailbox), sent_count)

    def test_password_reset_change_password_jwt_and_profile_still_work(self):
        token = self.register_and_verify()

        missing_profile = self.client.get(
            "/profile/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(missing_profile.status_code, 404)

        reset_mailbox: list[tuple[str, str]] = []
        original_reset_sender = auth_api.send_reset_password_email
        auth_api.send_reset_password_email = (
            lambda email, reset_token: reset_mailbox.append((email, reset_token))
        )
        try:
            forgot = self.client.post(
                "/auth/forgot-password",
                json={"email": "user@example.com"},
            )
        finally:
            auth_api.send_reset_password_email = original_reset_sender
        self.assertEqual(forgot.status_code, 200)
        self.assertEqual(len(reset_mailbox), 1)

        reset = self.client.post(
            "/auth/reset-password",
            json={
                "token": create_reset_token("user@example.com"),
                "new_password": "Reset123!",
            },
        )
        self.assertEqual(reset.status_code, 200)

        login = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Reset123!"},
        )
        self.assertEqual(login.status_code, 200)
        reset_token = login.json()["access_token"]

        changed = self.client.post(
            "/auth/change-password",
            json={"old_password": "Reset123!", "new_password": "Changed123!"},
            headers={"Authorization": f"Bearer {reset_token}"},
        )
        self.assertEqual(changed.status_code, 200)
        final_login = self.client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "Changed123!"},
        )
        self.assertEqual(final_login.status_code, 200)

    def test_logout_success(self):
        token = self.register_and_verify()
        response = self.client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "تم تسجيل الخروج بنجاح!"})

    def test_logout_unauthorized_without_token(self):
        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 401)


    def test_email_failure_keeps_account_recoverable(self):
        def fail_to_send(_email: str, _otp: str):
            raise RuntimeError("mail service unavailable")

        auth_api.send_verification_otp_email = fail_to_send
        response = self.register()
        self.assertEqual(response.status_code, 503)

        user = self.get_user()
        self.assertFalse(user.is_email_verified)
        self.assertIsNone(user.email_verification_otp_hash)
        self.assertIsNone(user.email_verification_otp_sent_at)

        auth_api.send_verification_otp_email = (
            lambda email, otp: self.mailbox.append((email, otp))
        )
        resend = self.client.post(
            "/auth/resend-verification-otp",
            json={"email": "user@example.com"},
        )
        self.assertEqual(resend.status_code, 200)
        self.assertEqual(len(self.mailbox), 1)

    def test_migration_preserves_existing_accounts_and_defaults_new_ones_to_unverified(self):
        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "alembic",
            "versions",
            "20260827_add_email_verification_otp.py",
        )
        spec = importlib.util.spec_from_file_location("email_otp_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(migration)

        engine = create_engine("sqlite://")
        metadata = MetaData()
        legacy_users = Table(
            "users",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("email", String, nullable=False),
        )
        metadata.create_all(engine)

        with engine.begin() as connection:
            connection.execute(
                legacy_users.insert().values(id=1, email="existing@example.com")
            )
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            self.assertIn("is_email_verified", columns)
            self.assertIn("email_verification_otp_hash", columns)
            existing_verified = connection.execute(
                text("SELECT is_email_verified FROM users WHERE id = 1")
            ).scalar_one()
            self.assertTrue(existing_verified)

            connection.execute(
                text("INSERT INTO users (id, email) VALUES (2, 'new@example.com')")
            )
            new_verified = connection.execute(
                text("SELECT is_email_verified FROM users WHERE id = 2")
            ).scalar_one()
            self.assertFalse(new_verified)

        engine.dispose()


class MailerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_api_key = settings.RESEND_API_KEY
        self.original_sender = settings.RESEND_FROM_EMAIL
        self.original_legacy_sender = settings.MAIL_FROM
        self.original_sender_name = settings.MAIL_FROM_NAME
        settings.RESEND_API_KEY = "re_test_key"
        settings.RESEND_FROM_EMAIL = "auth@scholarai.example"
        settings.MAIL_FROM = "legacy@scholarai.example"
        settings.MAIL_FROM_NAME = "Scholar AI"

    def tearDown(self):
        settings.RESEND_API_KEY = self.original_api_key
        settings.RESEND_FROM_EMAIL = self.original_sender
        settings.MAIL_FROM = self.original_legacy_sender
        settings.MAIL_FROM_NAME = self.original_sender_name

    def test_resend_from_email_is_used_for_otp_and_reset_mail(self):
        with patch.object(
            mailer.resend.Emails,
            "send",
            return_value={"id": "email_test"},
        ) as send:
            mailer.send_verification_otp_email("recipient@example.net", "123456")
            otp_payload = send.call_args.args[0]
            mailer.send_reset_password_email("recipient@example.net", "reset-token")
            reset_payload = send.call_args.args[0]

        self.assertEqual(
            otp_payload["from"],
            "Scholar AI <auth@scholarai.example>",
        )
        self.assertEqual(reset_payload["from"], otp_payload["from"])

    def test_provider_error_is_redacted_and_preserves_diagnostics(self):
        settings.RESEND_API_KEY = "re_secret_do_not_log"
        provider_error = mailer.ResendError(
            403,
            "validation_error",
            "Could not deliver to person@example.net with re_secret_do_not_log",
            "Verify the sender domain",
        )

        with patch.object(mailer.resend.Emails, "send", side_effect=provider_error):
            with self.assertRaises(EmailDeliveryError) as raised:
                mailer.send_verification_otp_email("person@example.net", "123456")

        error = raised.exception
        self.assertEqual(error.status_code, 403)
        self.assertEqual(error.error_type, "validation_error")
        self.assertNotIn("re_secret_do_not_log", str(error))
        self.assertNotIn("person@example.net", str(error))
        self.assertIn("[redacted-email]", str(error))


if __name__ == "__main__":
    unittest.main()
