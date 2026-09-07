import os
import unittest
from io import BytesIO
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "avatar-upload-test-key")
os.environ.setdefault("AWS_S3_BUCKET", "test-bucket")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.profile import router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document_upload import DocumentUploadSession
from app.models.profile import Experience, Profile
from app.models.user import User
from app.services.s3 import get_s3_storage
from tests.test_document_uploads import FakeS3


def _image_bytes(content_type: str) -> bytes:
    image_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[
        content_type
    ]
    output = BytesIO()
    Image.new("RGB", (2, 2), color="blue").save(output, format=image_format)
    return output.getvalue()


class AvatarUploadTests(unittest.TestCase):
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
            db.add(owner)
            db.flush()
            db.add(Profile(user_id=owner.id))
            db.commit()
            self.owner_id = owner.id

        self.owner = SimpleNamespace(id=self.owner_id, email="owner@example.com")
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
        app.dependency_overrides[get_current_user] = lambda: self.owner
        app.dependency_overrides[get_s3_storage] = lambda: self.s3
        self.client = TestClient(app)

        self.unauth_app = FastAPI()
        self.unauth_app.include_router(router)
        self.unauth_app.dependency_overrides[get_db] = override_get_db
        self.unauth_app.dependency_overrides[get_s3_storage] = lambda: self.s3
        self.unauth_client = TestClient(self.unauth_app)

    def tearDown(self):
        self.engine.dispose()

    def _request_upload(
        self,
        file_name="avatar.jpg",
        content_type="image/jpeg",
        file_size=None,
        client=None,
    ):
        if file_size is None:
            file_size = (
                len(_image_bytes(content_type))
                if content_type in {"image/jpeg", "image/png", "image/webp"}
                else 123
            )
        http = client or self.client
        return http.post(
            "/profile/avatar/upload-url",
            json={
                "file_name": file_name,
                "content_type": content_type,
                "file_size": file_size,
            },
        )

    def _upload_and_store(self, **kwargs):
        response = self._request_upload(**kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        upload_id = response.json()["upload_id"]
        with self.Session() as db:
            session = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            object_key = session.object_key
            content_type = session.expected_content_type
            size = session.expected_file_size
        body = _image_bytes(content_type)
        self.assertEqual(len(body), size)
        self.s3.put(object_key, content_type, size, body=body)
        return upload_id, object_key

    def test_unauthenticated_upload_url_rejected(self):
        response = self._request_upload(client=self.unauth_client)
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_mime_rejected(self):
        response = self._request_upload(
            file_name="avatar.jpg", content_type="application/pdf"
        )
        self.assertEqual(response.status_code, 400)

    def test_oversized_image_rejected(self):
        response = self._request_upload(file_size=settings.S3_MAX_AVATAR_BYTES + 1)
        self.assertEqual(response.status_code, 400)

    def test_confirm_missing_object_rejected(self):
        upload_id, object_key = self._upload_and_store()
        self.s3.objects.pop(object_key)
        response = self.client.post(
            "/profile/avatar/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(response.status_code, 400)

    def test_confirm_success_persists_and_profile_returns_url(self):
        upload_id, object_key = self._upload_and_store()
        confirmed = self.client.post(
            "/profile/avatar/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        body = confirmed.json()
        self.assertTrue(body["avatar_url"].startswith("https://s3.test/get/"))
        self.assertNotIn("object_key", body)

        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(profile.avatar_object_key, object_key)
            self.assertEqual(profile.avatar_content_type, "image/jpeg")
            self.assertEqual(profile.avatar_file_size, len(_image_bytes("image/jpeg")))

        loaded = self.client.get("/profile")
        self.assertEqual(loaded.status_code, 200)
        self.assertTrue(
            loaded.json()["avatar_url"].startswith("https://s3.test/get/")
        )
        self.assertIn(object_key, loaded.json()["avatar_url"])

    def test_confirm_rejects_invalid_image_content(self):
        invalid_body = b"not an image"
        response = self._request_upload(file_size=len(invalid_body))
        upload_id = response.json()["upload_id"]
        with self.Session() as db:
            session = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            self.s3.put(
                session.object_key,
                session.expected_content_type,
                len(invalid_body),
                body=invalid_body,
            )

        confirmed = self.client.post(
            "/profile/avatar/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(confirmed.status_code, 400)

    def test_confirm_rejects_image_content_type_mismatch(self):
        png_body = _image_bytes("image/png")
        response = self._request_upload(file_size=len(png_body))
        upload_id = response.json()["upload_id"]
        with self.Session() as db:
            session = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            self.s3.put(
                session.object_key,
                "image/jpeg",
                len(png_body),
                body=png_body,
            )

        confirmed = self.client.post(
            "/profile/avatar/confirm", json={"upload_id": upload_id}
        )
        self.assertEqual(confirmed.status_code, 400)

    def test_replacing_avatar_deletes_old_object(self):
        first_id, first_key = self._upload_and_store(file_name="one.png", content_type="image/png")
        self.client.post("/profile/avatar/confirm", json={"upload_id": first_id})
        second_id, second_key = self._upload_and_store()
        self.client.post("/profile/avatar/confirm", json={"upload_id": second_id})

        self.assertIn(first_key, self.s3.deleted)
        self.assertNotIn(first_key, self.s3.objects)
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(profile.avatar_object_key, second_key)

    def test_replacing_avatar_does_not_delete_shared_default(self):
        shared_key = "shared/default-avatar.png"
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            profile.avatar_object_key = shared_key
            db.commit()

        upload_id, new_key = self._upload_and_store()
        confirmed = self.client.post(
            "/profile/avatar/confirm", json={"upload_id": upload_id}
        )

        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertNotIn(shared_key, self.s3.deleted)
        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertEqual(profile.avatar_object_key, new_key)

    def test_delete_clears_avatar_and_profile_url_is_null(self):
        upload_id, object_key = self._upload_and_store()
        self.client.post("/profile/avatar/confirm", json={"upload_id": upload_id})
        deleted = self.client.delete("/profile/avatar")
        self.assertEqual(deleted.status_code, 204)
        self.assertIn(object_key, self.s3.deleted)

        with self.Session() as db:
            profile = db.query(Profile).filter_by(user_id=self.owner_id).one()
            self.assertIsNone(profile.avatar_object_key)

        loaded = self.client.get("/profile")
        self.assertIsNone(loaded.json()["avatar_url"])

        again = self.client.delete("/profile/avatar")
        self.assertEqual(again.status_code, 204)

    def test_generated_key_uses_avatar_prefix(self):
        response = self._request_upload()
        upload_id = response.json()["upload_id"]
        with self.Session() as db:
            session = db.query(DocumentUploadSession).filter_by(id=upload_id).one()
            self.assertTrue(
                session.object_key.startswith(f"users/{self.owner_id}/avatar/")
            )


if __name__ == "__main__":
    unittest.main()
