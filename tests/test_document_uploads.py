import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "document-upload-test-key")
os.environ.setdefault("AWS_S3_BUCKET", "test-bucket")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.profile import router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document_upload import (
    DocumentUploadSession,
    DocumentUploadSessionStatus,
)
from app.models.profile import Experience, Profile
from app.models.user import User
from app.services.s3 import ObjectHead, generate_object_key, get_s3_storage

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MB = 1024 * 1024


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.last_get_expires = None

    def generate_object_key(self, user_id, document_type, extension):
        return generate_object_key(user_id, document_type, extension)

    def presign_put(self, object_key, content_type, expires_in):
        return f"https://s3.test/put/{object_key}"

    def presign_get(self, object_key, expires_in):
        self.last_get_expires = expires_in
        return f"https://s3.test/get/{object_key}?exp={expires_in}"

    def head_object(self, object_key):
        obj = self.objects.get(object_key)
        if not obj:
            return ObjectHead(exists=False)
        return ObjectHead(
            exists=True,
            content_type=obj["content_type"],
            content_length=obj["content_length"],
        )

    def delete_object(self, object_key):
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)

    def put(self, object_key, content_type, size):
        self.objects[object_key] = {
            "content_type": content_type,
            "content_length": size,
        }


class DocumentUploadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        User.__table__.create(self.engine)
        Profile.__table__.create(self.engine)
        Experience.__table__.create(self.engine)
        DocumentUploadSession.__table__.create(self.engine)

        with self.Session() as db:
            owner = User(
                full_name="Owner",
                email="owner@example.com",
                hashed_password="x",
                is_email_verified=True,
            )
            other = User(
                full_name="Other",
                email="other@example.com",
                hashed_password="x",
                is_email_verified=True,
            )
            db.add_all([owner, other])
            db.flush()
            db.add_all(
                [
                    Profile(user_id=owner.id),
                    Profile(user_id=other.id),
                ]
            )
            db.commit()
            self.owner_id = owner.id
            self.other_id = other.id

        self.owner = SimpleNamespace(id=self.owner_id, email="owner@example.com")
        self.other = SimpleNamespace(id=self.other_id, email="other@example.com")
        self.current_user = self.owner
        self.s3 = FakeS3()

        app = FastAPI()
        app.include_router(router)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        app.dependency_overrides[get_s3_storage] = lambda: self.s3
        self.app = app
        self.client = TestClient(app)

        self.auth_app = FastAPI()
        self.auth_app.include_router(router)
        self.auth_app.dependency_overrides[get_db] = override_get_db
        self.auth_app.dependency_overrides[get_s3_storage] = lambda: self.s3
        self.unauth_client = TestClient(self.auth_app)

    def tearDown(self):
        self.engine.dispose()

    def _session(self, upload_id: str) -> DocumentUploadSession:
        with self.Session() as db:
            return db.query(DocumentUploadSession).filter_by(id=upload_id).one()

    def _request_upload(
        self,
        document_type="cv",
        file_name="cv.pdf",
        content_type="application/pdf",
        file_size=123,
        client=None,
    ):
        http = client or self.client
        return http.post(
            "/profile/documents/upload-url",
            json={
                "document_type": document_type,
                "file_name": file_name,
                "content_type": content_type,
                "file_size": file_size,
            },
        )

    def _upload_and_store(
        self,
        document_type="cv",
        file_name="cv.pdf",
        content_type="application/pdf",
        file_size=123,
        mutate=None,
    ):
        response = self._request_upload(
            document_type=document_type,
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
        )
        self.assertEqual(response.status_code, 200, response.text)
        upload_id = response.json()["upload_id"]
        session = self._session(upload_id)
        stored_type = content_type
        stored_size = file_size
        if mutate:
            stored_type, stored_size = mutate(session)
        self.s3.put(session.object_key, stored_type, stored_size)
        return upload_id, session, response.json()

    def test_unauthenticated_requests_rejected(self):
        cases = [
            ("get", "/profile/documents", None),
            ("post", "/profile/documents/upload-url", {"document_type": "cv", "file_name": "cv.pdf", "content_type": "application/pdf", "file_size": 1}),
            ("post", "/profile/documents/confirm", {"upload_id": "x"}),
            ("get", "/profile/documents/doc/download-url", None),
            ("delete", "/profile/documents/doc", None),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                caller = getattr(self.unauth_client, method)
                response = caller(path, json=body) if body else caller(path)
                self.assertIn(response.status_code, (401, 403))

    def test_upload_url_rejects_invalid_inputs(self):
        invalid = [
            dict(document_type="resume", file_name="cv.pdf", content_type="application/pdf", file_size=10),
            dict(document_type="cv", file_name="cv.exe", content_type="application/pdf", file_size=10),
            dict(document_type="cv", file_name="cv.pdf", content_type="image/png", file_size=10),
            dict(document_type="cv", file_name="cv.pdf", content_type="application/pdf", file_size=5 * MB + 1),
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post("/profile/documents/upload-url", json=payload)
                self.assertIn(response.status_code, (400, 422))

    def test_upload_url_creates_session_and_user_prefixed_key(self):
        response = self._request_upload()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("upload_id", body)
        self.assertNotIn("object_key", body)
        self.assertEqual(body["headers"]["Content-Type"], "application/pdf")
        session = self._session(body["upload_id"])
        self.assertEqual(session.status, DocumentUploadSessionStatus.PENDING.value)
        self.assertTrue(
            session.object_key.startswith(f"users/{self.owner_id}/documents/cv/")
        )
        self.assertTrue(session.object_key.endswith(".pdf"))

    def test_confirm_rejects_invalid_expired_foreign_and_mismatch(self):
        missing = self.client.post(
            "/profile/documents/confirm", json={"upload_id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(missing.status_code, 404)

        upload_id, session, _ = self._upload_and_store()
        self.s3.objects.pop(session.object_key)
        missing_object = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(missing_object.status_code, 400)

        upload_id, session, _ = self._upload_and_store(
            mutate=lambda _s: ("image/png", 123)
        )
        wrong_type = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(wrong_type.status_code, 400)

        upload_id, session, _ = self._upload_and_store(
            mutate=lambda _s: ("application/pdf", 999)
        )
        wrong_size = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(wrong_size.status_code, 400)

        upload_id, session, _ = self._upload_and_store()
        with self.Session() as db:
            row = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        expired = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(expired.status_code, 400)

        upload_id, session, _ = self._upload_and_store()
        self.current_user = self.other
        foreign = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(foreign.status_code, 404)
        self.current_user = self.owner

    def test_confirm_writes_public_metadata_to_profile(self):
        upload_id, session, _ = self._upload_and_store()
        confirmed = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(confirmed.status_code, 200)
        body = confirmed.json()
        self.assertEqual(body["status"], "UPLOADED")
        self.assertEqual(body["document_type"], "cv")
        self.assertEqual(body["file_name"], "cv.pdf")
        self.assertNotIn("object_key", body)
        self.assertNotIn("file_url", body)
        self.assertNotIn("download_url", body)

        profile = self.client.get("/profile")
        self.assertEqual(profile.status_code, 200)
        cv = profile.json()["documents"]["cv"]
        self.assertEqual(cv["id"], body["id"])
        self.assertEqual(cv["status"], "UPLOADED")
        self.assertNotIn("object_key", cv)
        self.assertNotIn("file_url", cv)
        self.assertNotIn("download_url", cv)

        with self.Session() as db:
            stored = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(stored.documents_data["cv"]["object_key"], session.object_key)
            row = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            self.assertEqual(row.status, DocumentUploadSessionStatus.CONFIRMED.value)

    def test_recommendation_letters_append_with_ids_and_max(self):
        ids = []
        for index in range(settings.S3_MAX_RECOMMENDATION_LETTERS):
            upload_id, _, _ = self._upload_and_store(
                document_type="recommendation_letter",
                file_name=f"letter-{index}.pdf",
            )
            confirmed = self.client.post(
                "/profile/documents/confirm", json={"upload_id": upload_id}
            )
            self.assertEqual(confirmed.status_code, 200)
            ids.append(confirmed.json()["id"])

        self.assertEqual(len(set(ids)), 3)
        letters = self.client.get("/profile").json()["documents"]["recommendation_letters"]
        self.assertEqual(len(letters), 3)

        blocked = self._request_upload(
            document_type="recommendation_letter",
            file_name="letter-extra.pdf",
        )
        self.assertEqual(blocked.status_code, 400)

    def test_download_owner_only_and_expiry_from_config(self):
        upload_id, _, _ = self._upload_and_store()
        confirmed = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        document_id = confirmed.json()["id"]

        download = self.client.get(f"/profile/documents/{document_id}/download-url")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(
            download.json()["expires_in"], settings.S3_PRESIGN_GET_EXPIRE_SECONDS
        )
        self.assertEqual(self.s3.last_get_expires, settings.S3_PRESIGN_GET_EXPIRE_SECONDS)
        self.assertTrue(download.json()["download_url"].startswith("https://s3.test/get/"))

        self.current_user = self.other
        forbidden = self.client.get(f"/profile/documents/{document_id}/download-url")
        self.assertEqual(forbidden.status_code, 404)
        self.current_user = self.owner

    def test_delete_removes_object_and_metadata_and_is_idempotent(self):
        upload_id, session, _ = self._upload_and_store()
        confirmed = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        document_id = confirmed.json()["id"]

        deleted = self.client.delete(f"/profile/documents/{document_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertIn(session.object_key, self.s3.deleted)
        self.assertNotIn(session.object_key, self.s3.objects)

        profile = self.client.get("/profile").json()
        self.assertEqual(profile["documents"]["cv"]["status"], "NOT_UPLOADED")
        self.assertIsNone(profile["documents"]["cv"]["id"])

        again = self.client.delete(f"/profile/documents/{document_id}")
        self.assertEqual(again.status_code, 204)

        upload_id, session, _ = self._upload_and_store(file_name="second.pdf")
        confirmed = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        )
        document_id = confirmed.json()["id"]
        self.s3.objects.pop(session.object_key)
        missing_object = self.client.delete(f"/profile/documents/{document_id}")
        self.assertEqual(missing_object.status_code, 204)

        with self.Session() as db:
            stored = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(stored.documents_data["cv"]["status"], "NOT_UPLOADED")

    def test_delete_persists_empty_cv_on_fresh_db_query(self):
        document_id = "cv-doc-1"
        object_key = f"users/{self.owner_id}/documents/cv/{document_id}.pdf"
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            profile.documents_data = {
                "cv": {
                    "id": document_id,
                    "document_type": "cv",
                    "object_key": object_key,
                    "file_name": "cv.pdf",
                    "content_type": "application/pdf",
                    "file_size": 12,
                    "status": "UPLOADED",
                    "uploaded_at": "2026-09-06T10:00:00+00:00",
                }
            }
            db.add(profile)
            db.add(
                DocumentUploadSession(
                    id="session-cv-1",
                    user_id=self.owner_id,
                    document_type="cv",
                    object_key=object_key,
                    original_file_name="cv.pdf",
                    expected_content_type="application/pdf",
                    expected_file_size=12,
                    status=DocumentUploadSessionStatus.CONFIRMED.value,
                    expires_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        self.s3.put(object_key, "application/pdf", 12)

        response = self.client.delete(f"/profile/documents/{document_id}")
        self.assertEqual(response.status_code, 204)

        with self.Session() as db:
            reloaded = db.query(Profile).filter_by(user_id=self.owner_id).one()
            cv = reloaded.documents_data["cv"]
            self.assertEqual(cv["status"], "NOT_UPLOADED")
            self.assertIsNone(cv.get("id"))
            self.assertIsNone(cv.get("file_name"))
            self.assertNotIn("object_key", cv)
            raw = db.execute(
                Profile.__table__.select().where(
                    Profile.__table__.c.user_id == self.owner_id
                )
            ).mappings().one()["documents"]
            self.assertEqual(raw["cv"]["status"], "NOT_UPLOADED")
            self.assertFalse(
                db.query(DocumentUploadSession)
                .filter_by(object_key=object_key)
                .count()
            )

        profile = self.client.get("/profile").json()
        self.assertEqual(profile["documents"]["cv"]["status"], "NOT_UPLOADED")
        self.assertIsNone(profile["documents"]["cv"]["id"])

    def test_delete_persists_recommendation_letter_removal_on_fresh_db_query(self):
        keep_id = "letter-keep"
        drop_id = "letter-drop"
        keep_key = f"users/{self.owner_id}/documents/recommendation_letter/{keep_id}.pdf"
        drop_key = f"users/{self.owner_id}/documents/recommendation_letter/{drop_id}.pdf"
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            profile.documents_data = {
                "recommendation_letters": [
                    {
                        "id": keep_id,
                        "document_type": "recommendation_letter",
                        "object_key": keep_key,
                        "file_name": "keep.pdf",
                        "content_type": "application/pdf",
                        "file_size": 10,
                        "status": "UPLOADED",
                    },
                    {
                        "id": drop_id,
                        "document_type": "recommendation_letter",
                        "object_key": drop_key,
                        "file_name": "drop.pdf",
                        "content_type": "application/pdf",
                        "file_size": 11,
                        "status": "UPLOADED",
                    },
                ]
            }
            db.add(profile)
            db.commit()
        self.s3.put(keep_key, "application/pdf", 10)
        self.s3.put(drop_key, "application/pdf", 11)

        response = self.client.delete(f"/profile/documents/{drop_id}")
        self.assertEqual(response.status_code, 204)

        with self.Session() as db:
            reloaded = db.query(Profile).filter_by(user_id=self.owner_id).one()
            letters = reloaded.documents_data["recommendation_letters"]
            self.assertEqual([letter["id"] for letter in letters], [keep_id])
            self.assertEqual(letters[0]["object_key"], keep_key)

        profile = self.client.get("/profile").json()
        letters = profile["documents"]["recommendation_letters"]
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["id"], keep_id)
        self.assertEqual(letters[0]["status"], "UPLOADED")

    def test_legacy_client_cannot_write_storage_references(self):
        put_legacy = self.client.put(
            "/profile/documents",
            json={
                "cv": {
                    "status": "UPLOADED",
                    "file_url": "https://evil.example/cv.pdf",
                    "object_key": "users/999/documents/cv/stolen.pdf",
                }
            },
        )
        self.assertEqual(put_legacy.status_code, 405)

        old_upload = self.client.post("/profile/documents/upload")
        self.assertIn(old_upload.status_code, (404, 405))

        profile = self.client.get("/profile").json()
        self.assertNotEqual(
            profile["documents"]["cv"].get("file_url"),
            "https://evil.example/cv.pdf",
        )

    def test_allowed_formats_complete_upload_at_size_limit(self):
        cases = [
            ("cv", "PDF", "application/pdf", 5),
            ("cv", "docx", DOCX_MIME, 5),
            ("transcript", "pdf", "application/pdf", 10),
            ("graduation_certificate", "pdf", "application/pdf", 10),
            ("graduation_certificate", "jpg", "image/jpeg", 10),
            ("graduation_certificate", "jpeg", "image/jpeg", 10),
            ("graduation_certificate", "png", "image/png", 10),
            ("passport", "pdf", "application/pdf", 5),
            ("passport", "jpg", "image/jpeg", 5),
            ("passport", "jpeg", "image/jpeg", 5),
            ("passport", "png", "image/png", 5),
            ("recommendation_letter", "pdf", "application/pdf", 5),
            ("recommendation_letter", "docx", DOCX_MIME, 5),
            ("english_test", "pdf", "application/pdf", 5),
            ("english_test", "jpg", "image/jpeg", 5),
            ("english_test", "jpeg", "image/jpeg", 5),
            ("english_test", "png", "image/png", 5),
        ]
        for document_type, extension, mime, max_mb in cases:
            with self.subTest(document_type=document_type, extension=extension):
                upload_id, session, body = self._upload_and_store(
                    document_type, f"FILE.{extension}", mime, max_mb * MB
                )
                self.assertTrue(session.object_key.endswith(f".{extension.lower()}"))
                self.assertEqual(body["headers"], {"Content-Type": mime})
                response = self.client.post(
                    "/profile/documents/confirm", json={"upload_id": upload_id}
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["file_size"], max_mb * MB)
                self.assertEqual(response.json()["content_type"], mime)

    def test_invalid_metadata_has_no_session_key_or_presign_side_effects(self):
        cases = [
            ("cv", "cv.pdf", "application/pdf", 5 * MB + 1),
            ("transcript", "transcript.pdf", "application/pdf", 10 * MB + 1),
            ("graduation_certificate", "certificate.png", "image/png", 10 * MB + 1),
            ("passport", "passport.png", "image/png", 5 * MB + 1),
            ("recommendation_letter", "letter.docx", DOCX_MIME, 5 * MB + 1),
            ("english_test", "test.jpg", "image/jpeg", 5 * MB + 1),
            ("cv", "cv.png", "image/png", 100),
            ("transcript", "transcript.png", "image/png", 100),
            ("recommendation_letter", "letter.exe", "application/x-msdownload", 100),
            ("cv", "cv.pdf", "application/x-msdownload", 100),
            ("cv", "cv.pdf", DOCX_MIME, 100),
            ("passport", "passport.jpg", "image/png", 100),
            ("unknown", "file.pdf", "application/pdf", 100),
            ("cv", "file.pdf", "application/pdf", 0),
            ("cv", "file.pdf", "application/pdf", -1),
            ("cv", "file.pdf", "application/pdf", 1.5),
            ("cv", "a" * 256 + ".pdf", "application/pdf", 100),
        ]
        for extension in ("js", "html", "sh", "zip", "py", "php", "bat", "cmd"):
            cases.append(("cv", f"file.{extension}", "application/pdf", 100))
        for document_type, name, mime, size in cases:
            with self.subTest(document_type=document_type, name=name, size=size):
                with patch.object(self.s3, "generate_object_key") as key_mock, patch.object(
                    self.s3, "presign_put"
                ) as presign_mock:
                    response = self._request_upload(document_type, name, mime, size)
                    self.assertIn(response.status_code, (400, 422), response.text)
                    key_mock.assert_not_called()
                    presign_mock.assert_not_called()
                with self.Session() as db:
                    self.assertEqual(db.query(DocumentUploadSession).count(), 0)

    def test_filename_sanitization_cannot_control_storage_path(self):
        for name in ("../../secret.pdf", "folder/file.Pdf", r"..\..\secret.pdf", "bad\x00\nname.pdf"):
            with self.subTest(name=name):
                response = self._request_upload(file_name=name)
                self.assertEqual(response.status_code, 200, response.text)
                session = self._session(response.json()["upload_id"])
                self.assertRegex(session.original_file_name, r"^[A-Za-z0-9._-]{1,255}$")
                self.assertRegex(
                    session.object_key,
                    rf"^users/{self.owner_id}/documents/cv/[0-9a-f-]{{36}}\.pdf$",
                )

    def test_invalid_s3_metadata_is_deleted_and_old_document_is_preserved(self):
        upload_id, old_session, _ = self._upload_and_store()
        old = self.client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        ).json()
        for mime, size in (
            ("application/pdf", 5 * MB + 1),
            ("application/pdf", 999),
            ("application/pdf", 0),
            ("application/pdf", None),
            ("image/png", 123),
            (DOCX_MIME, 123),
            (None, 123),
        ):
            with self.subTest(mime=mime, size=size):
                new_id, session, _ = self._upload_and_store(
                    mutate=lambda _session, mime=mime, size=size: (mime, size)
                )
                response = self.client.post(
                    "/profile/documents/confirm", json={"upload_id": new_id}
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self._session(new_id).status, "FAILED")
                self.assertIn(session.object_key, self.s3.deleted)
                self.assertNotIn(session.object_key, self.s3.objects)
                self.assertNotIn(old_session.object_key, self.s3.deleted)
                with self.Session() as db:
                    profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
                    self.assertEqual(profile.documents_data["cv"]["id"], old["id"])
                retry = self.client.post(
                    "/profile/documents/confirm", json={"upload_id": new_id}
                )
                self.assertEqual(retry.status_code, 400)

    def test_confirm_reapplies_policy_to_legacy_sessions(self):
        for mime, name, size in (
            ("application/pdf", "cv.pdf", 6 * MB),
            ("image/png", "cv.png", 123),
        ):
            with self.subTest(mime=mime, size=size):
                upload_id, session, _ = self._upload_and_store()
                with self.Session() as db:
                    row = db.get(DocumentUploadSession, upload_id)
                    row.expected_file_size = size
                    row.expected_content_type = mime
                    row.original_file_name = name
                    db.commit()
                self.s3.put(session.object_key, mime, size)
                response = self.client.post(
                    "/profile/documents/confirm", json={"upload_id": upload_id}
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(session.object_key, self.s3.deleted)
                self.assertEqual(self._session(upload_id).status, "FAILED")

    def test_valid_replacement_and_confirm_replay(self):
        old_id, old_session, _ = self._upload_and_store()
        old = self.client.post(
            "/profile/documents/confirm", json={"upload_id": old_id}
        ).json()
        new_id, new_session, _ = self._upload_and_store(
            file_name="new.docx", content_type=DOCX_MIME
        )
        self.assertEqual(self.client.get("/profile/documents").json()["cv"]["id"], old["id"])
        response = self.client.post(
            "/profile/documents/confirm", json={"upload_id": new_id}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()["id"], old["id"])
        self.assertIn(old_session.object_key, self.s3.deleted)
        self.assertIn(new_session.object_key, self.s3.objects)
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(profile.documents_data["cv"]["id"], response.json()["id"])
        replay = self.client.post(
            "/profile/documents/confirm", json={"upload_id": new_id}
        )
        self.assertEqual(replay.status_code, 409)

    def test_client_fields_cannot_override_session_or_ownership(self):
        upload_id, session, _ = self._upload_and_store()
        arbitrary_key = "users/999/documents/cv/stolen.pdf"
        self.s3.put(arbitrary_key, "application/pdf", 123)
        response = self.client.post("/profile/documents/confirm", json={
            "upload_id": upload_id,
            "user_id": self.other_id,
            "document_type": "passport",
            "object_key": arbitrary_key,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document_type"], "cv")
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(profile.documents_data["cv"]["object_key"], session.object_key)
        self.current_user = self.other
        self.client.delete(f"/profile/documents/{response.json()['id']}")
        self.assertIn(session.object_key, self.s3.objects)
        self.assertIsNone(self.client.get("/profile/documents").json()["cv"]["id"])

    def test_foreign_session_cannot_trigger_s3_validation_or_cleanup(self):
        upload_id, session, _ = self._upload_and_store(mutate=lambda _s: ("image/png", 123))
        self.current_user = self.other
        with patch.object(self.s3, "head_object") as head:
            response = self.client.post(
                "/profile/documents/confirm", json={"upload_id": upload_id}
            )
            self.assertEqual(response.status_code, 404)
            head.assert_not_called()
        self.assertIn(session.object_key, self.s3.objects)
        self.assertEqual(self._session(upload_id).status, "PENDING")

    def test_storage_errors_are_safe_and_cleanup_failure_does_not_accept_file(self):
        with patch.object(self.s3, "presign_put", side_effect=RuntimeError("private AWS details")):
            response = self._request_upload()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private AWS details", response.text)
        with self.Session() as db:
            self.assertEqual(db.query(DocumentUploadSession).count(), 0)
        upload_id, _session, _ = self._upload_and_store(mutate=lambda _s: ("image/png", 123))
        with patch.object(self.s3, "head_object", side_effect=RuntimeError("private AWS details")):
            response = self.client.post(
                "/profile/documents/confirm", json={"upload_id": upload_id}
            )
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private AWS details", response.text)
        self.assertEqual(self._session(upload_id).status, "PENDING")
        with patch.object(self.s3, "delete_object", side_effect=RuntimeError("private AWS details")):
            response = self.client.post(
                "/profile/documents/confirm", json={"upload_id": upload_id}
            )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("private AWS details", response.text)
        self.assertEqual(self._session(upload_id).status, "FAILED")
        self.assertIsNone(self.client.get("/profile/documents").json()["cv"]["id"])


if __name__ == "__main__":
    unittest.main()
