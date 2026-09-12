import pytest
from fastapi.openapi.models import OpenAPI

from app.core.security import create_access_token
from app.models.profile import Profile
from app.schemas.documents import ProfileDocumentType
from app.schemas.profile import (
    Documents,
    PreferencesResponse,
    SkillsAndLanguages,
    calculate_profile_completion,
)
from app.services.documents import DOCUMENT_RULES
from tests import test_document_uploads as existing

TYPE = "university_admission_letter"
MB = 1024 * 1024


@pytest.fixture
def case():
    fixture = existing.DocumentUploadTests(methodName="runTest")
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.client.close()
        fixture.unauth_client.close()
        fixture.tearDown()


def confirm(case, **kwargs):
    upload_id, session, _ = case._upload_and_store(document_type=TYPE, **kwargs)
    response = case.client.post(
        "/profile/documents/confirm", json={"upload_id": upload_id}
    )
    assert response.status_code == 200, response.text
    return upload_id, session, response.json()


@pytest.mark.parametrize(
    "extension,mime",
    [
        ("pdf", "application/pdf"),
        ("jpg", "image/jpeg"),
        ("jpeg", "image/jpeg"),
        ("png", "image/png"),
    ],
)
def test_upload_metadata_listing_download_and_duplicate_confirmation(
    case, extension, mime
):
    upload_id, session, record = confirm(
        case,
        file_name=f"../../admission.{extension}",
        content_type=mime,
        file_size=10 * MB,
    )
    assert record["document_type"] == TYPE
    assert record["status"] == "UPLOADED"
    assert record["file_name"] == f"admission.{extension}"
    assert record["file_size"] == 10 * MB
    assert record["content_type"] == mime
    assert record["uploaded_at"]
    assert "object_key" not in record
    assert "score" not in record
    assert "suggestions" not in record
    assert set(record) == {
        "id",
        "document_type",
        "status",
        "file_name",
        "content_type",
        "file_size",
        "uploaded_at",
    }
    assert case.client.get("/profile/documents").json()[TYPE] == record
    assert case.client.get("/profile").json()["documents"][TYPE] == record
    with case.Session() as db:
        stored = (
            db.query(Profile)
            .filter_by(user_id=case.owner_id)
            .one()
            .documents_data[TYPE]
        )
        assert stored["object_key"] == session.object_key
        assert stored["id"] == record["id"]
    assert f"users/{case.owner_id}/documents/{TYPE}/" in session.object_key
    download = case.client.get(f"/profile/documents/{record['id']}/download-url")
    assert download.status_code == 200
    assert session.object_key in download.json()["download_url"]
    duplicate = case.client.post(
        "/profile/documents/confirm", json={"upload_id": upload_id}
    )
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    "name,mime,size,status",
    [
        ("letter.pdf", "application/pdf", 10 * MB + 1, 400),
        ("letter.docx", existing.DOCX_MIME, 123, 400),
        ("letter.exe", "application/octet-stream", 123, 400),
        ("letter.pdf", "image/png", 123, 400),
        ("letter.png", "image/jpeg", 123, 400),
        ("letter", "application/pdf", 123, 400),
        ("letter.pdf", "application/pdf", 0, 422),
    ],
)
def test_invalid_intents(case, name, mime, size, status):
    response = case._request_upload(TYPE, name, mime, size)
    assert response.status_code == status
    assert "detail" in response.json()
    with case.Session() as db:
        assert db.query(existing.DocumentUploadSession).count() == 0


def test_real_token_authentication_and_ownership(case):
    assert (
        case._request_upload(document_type=TYPE, client=case.unauth_client).status_code
        == 401
    )
    token = create_access_token({"sub": str(case.owner_id)})
    case.unauth_client.headers["Authorization"] = f"Bearer {token}"
    response = case._request_upload(document_type=TYPE, client=case.unauth_client)
    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    session = case._session(upload_id)
    case.s3.put(session.object_key, "application/pdf", 123)
    other = create_access_token({"sub": str(case.other_id)})
    case.unauth_client.headers["Authorization"] = f"Bearer {other}"
    assert (
        case.unauth_client.post(
            "/profile/documents/confirm", json={"upload_id": upload_id}
        ).status_code
        == 404
    )
    case.unauth_client.headers["Authorization"] = f"Bearer {token}"
    record = case.unauth_client.post(
        "/profile/documents/confirm", json={"upload_id": upload_id}
    ).json()
    case.unauth_client.headers["Authorization"] = f"Bearer {other}"
    assert (
        case.unauth_client.get(
            f"/profile/documents/{record['id']}/download-url"
        ).status_code
        == 404
    )
    # Existing delete is idempotent: another user's ID is a no-op, never a deletion.
    assert (
        case.unauth_client.delete(f"/profile/documents/{record['id']}").status_code
        == 204
    )
    assert session.object_key not in case.s3.deleted
    assert case.unauth_client.get("/profile/documents").json()[TYPE]["id"] is None
    assert case.client.get("/profile/documents").json()[TYPE]["id"] == record["id"]


def test_replacement_and_deletion(case):
    _, first_session, first = confirm(case)
    _, second_session, second = confirm(case, file_name="replacement.pdf")
    assert first["id"] != second["id"]
    assert first_session.object_key in case.s3.deleted
    assert case.client.get("/profile/documents").json()[TYPE] == second
    assert (
        case.client.get(f"/profile/documents/{first['id']}/download-url").status_code
        == 404
    )
    assert case.client.delete(f"/profile/documents/{second['id']}").status_code == 204
    assert second_session.object_key in case.s3.deleted
    assert case.client.delete(f"/profile/documents/{second['id']}").status_code == 204
    assert (
        case.client.get("/profile/documents").json()[TYPE]["status"] == "NOT_UPLOADED"
    )
    with case.Session() as db:
        stored = (
            db.query(Profile)
            .filter_by(user_id=case.owner_id)
            .one()
            .documents_data[TYPE]
        )
        assert stored["id"] is None


@pytest.mark.parametrize(
    "actual_mime,actual_size",
    [
        ("image/png", 123),
        ("application/pdf", 124),
        ("application/pdf", 10 * MB + 1),
    ],
)
def test_invalid_replacement_keeps_existing_document(case, actual_mime, actual_size):
    _, original_session, original = confirm(case)
    upload_id, session, _ = case._upload_and_store(
        document_type=TYPE, mutate=lambda _: (actual_mime, actual_size)
    )
    response = case.client.post(
        "/profile/documents/confirm", json={"upload_id": upload_id}
    )
    assert response.status_code == 400
    assert "detail" in response.json()
    assert case._session(upload_id).status == "FAILED"
    assert session.object_key in case.s3.deleted
    assert original_session.object_key not in case.s3.deleted
    assert case.client.get("/profile/documents").json()[TYPE] == original


def test_capability_and_profile_completion(case):
    document_type = ProfileDocumentType.UNIVERSITY_ADMISSION_LETTER
    assert document_type.value == TYPE
    assert DOCUMENT_RULES[document_type]["is_improvable"] is False
    _, _, record = confirm(case)
    args = {
        "personal_info": None,
        "academic_info": None,
        "skills_and_languages": SkillsAndLanguages(),
        "experiences": [],
        "preferences": PreferencesResponse(),
    }
    assert calculate_profile_completion(
        documents=Documents(**{TYPE: record}), **args
    ) == calculate_profile_completion(documents=Documents(), **args)
    # No improvement/rewriting API exists for any document in this repository.
    response = case.client.post(f"/profile/documents/{record['id']}/improve")
    assert response.status_code == 404
    assert case.client.get("/profile/documents").json()[TYPE]["status"] == "UPLOADED"


def test_openapi_and_legacy_documents(case):
    schema = case.app.openapi()
    OpenAPI.model_validate(schema)
    assert TYPE in schema["components"]["schemas"]["ProfileDocumentType"]["enum"]
    assert (
        schema["components"]["schemas"]["Documents"]["properties"][TYPE]["title"]
        == "University Admission Letter"
    )
    assert (
        "is_improvable"
        not in schema["components"]["schemas"]["UploadedFile"]["properties"]
    )
    documents = case.client.get("/profile/documents").json()
    assert documents[TYPE]["status"] == "NOT_UPLOADED"
    assert documents["cv"]["status"] == "NOT_UPLOADED"


@pytest.mark.parametrize(
    "arabic_filename",
    [
        "قبول_جامعي.pdf",
        "إشعار قبول.pdf",
        "رسالة_القبول_الجامعي (1).pdf",
        "مستند قبول النهائي.PDF",
    ],
)
def test_arabic_and_unicode_filenames_valid(case, arabic_filename):
    upload_id, session, record = confirm(
        case,
        file_name=arabic_filename,
        content_type="application/pdf",
        file_size=2 * MB,
    )
    assert record["document_type"] == TYPE
    assert record["status"] == "UPLOADED"

