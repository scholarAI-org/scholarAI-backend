from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_upload import (
    DocumentUploadSession,
    DocumentUploadSessionStatus,
)
from app.models.profile import Profile
from app.models.user import User
from app.schemas.documents import ProfileDocumentType
from app.schemas.profile import Documents, UploadStatus
from app.services.s3 import StorageClient

# HeadObject checks stored object metadata only, not file bytes.
# Magic-byte inspection / malware scanning can be added later as an async
# worker or Lambda that reads the object after confirm, without changing
# the upload-url / confirm contract.

PDF_TYPES = {".pdf": {"application/pdf"}}
IMAGE_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}

DOCUMENT_RULES: dict[ProfileDocumentType, dict[str, Any]] = {
    ProfileDocumentType.CV: {"extensions": PDF_TYPES, "max_count": 1, "slot": "cv"},
    ProfileDocumentType.TRANSCRIPT: {
        "extensions": PDF_TYPES,
        "max_count": 1,
        "slot": "transcript",
    },
    ProfileDocumentType.GRADUATION_CERTIFICATE: {
        "extensions": PDF_TYPES,
        "max_count": 1,
        "slot": "graduation_certificate",
    },
    ProfileDocumentType.PASSPORT: {
        "extensions": {**PDF_TYPES, **IMAGE_TYPES},
        "max_count": 1,
        "slot": "passport",
    },
    ProfileDocumentType.RECOMMENDATION_LETTER: {
        "extensions": PDF_TYPES,
        "max_count": None,
        "slot": "recommendation_letters",
    },
    ProfileDocumentType.ENGLISH_TEST: {
        "extensions": {**PDF_TYPES, **IMAGE_TYPES},
        "max_count": 1,
        "slot": "english_test",
    },
}

UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def sanitize_file_name(file_name: str) -> str:
    name = Path(file_name.replace("\\", "/")).name.strip()
    name = unicodedata.normalize("NFKC", name)
    name = UNSAFE_FILENAME_CHARS.sub("_", name).strip("._")
    if not name:
        name = "document"
    return name[:255]


def _extension_for(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if not suffix or suffix == ".":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="امتداد الملف غير صالح.",
        )
    return suffix


def _normalize_content_type(content_type: str) -> str:
    return content_type.split(";")[0].strip().lower()


def validate_upload_intent(
    document_type: ProfileDocumentType,
    file_name: str,
    content_type: str,
    file_size: int,
) -> tuple[str, str, str]:
    rules = DOCUMENT_RULES[document_type]
    extension = _extension_for(file_name)
    allowed = rules["extensions"]
    if extension not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="امتداد الملف غير مسموح لهذا النوع من الوثائق.",
        )

    normalized_type = _normalize_content_type(content_type)
    if normalized_type not in allowed[extension]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نوع الملف غير مسموح لهذا الامتداد.",
        )

    max_bytes = int(rules.get("max_bytes") or settings.S3_MAX_FILE_BYTES)
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حجم الملف يتجاوز الحد المسموح.",
        )

    return sanitize_file_name(file_name), extension, normalized_type


def _json_clone(value: Any) -> Any:
    """Return a detached copy so JSON column assignment is always a new object."""
    return json.loads(json.dumps(value, default=str))


def _empty_slot(document_type: str) -> dict[str, Any]:
    return {
        "id": None,
        "document_type": document_type,
        "status": UploadStatus.NOT_UPLOADED.value,
        "file_name": None,
        "content_type": None,
        "file_size": None,
        "uploaded_at": None,
    }


def _empty_documents() -> dict[str, Any]:
    return {
        "cv": _empty_slot("cv"),
        "transcript": _empty_slot("transcript"),
        "graduation_certificate": _empty_slot("graduation_certificate"),
        "passport": _empty_slot("passport"),
        "english_test": _empty_slot("english_test"),
        "recommendation_letters": [],
    }


def save_documents(db: Session, profile: Profile, documents: dict[str, Any]) -> None:
    """Persist documents with a SQL UPDATE so PostgreSQL JSON actually changes.

    profiles.documents is a plain JSON column (not JSONB, not MutableDict).
    ORM attribute assignment often does not emit UPDATE for nested JSON.
    """
    payload = _json_clone(documents)
    db.execute(
        update(Profile.__table__)
        .where(Profile.__table__.c.id == profile.id)
        .values(documents=payload)
    )
    db.commit()
    db.expire_all()


def load_documents_dict(profile: Optional[Profile]) -> dict[str, Any]:
    stored = _json_clone(profile.documents_data or {}) if profile else {}
    base = _empty_documents()
    for key in (
        "cv",
        "transcript",
        "graduation_certificate",
        "passport",
        "english_test",
    ):
        if isinstance(stored.get(key), dict):
            merged = {**base[key], **stored[key]}
            merged["document_type"] = key
            base[key] = merged
    letters = stored.get("recommendation_letters") or []
    if isinstance(letters, list):
        base["recommendation_letters"] = [
            {**item, "document_type": "recommendation_letter"}
            for item in letters
            if isinstance(item, dict)
        ]
    return base


def public_documents(profile: Optional[Profile]) -> Documents:
    return Documents.model_validate(load_documents_dict(profile))


def _iter_stored_documents(data: dict[str, Any]):
    for key in (
        "cv",
        "transcript",
        "graduation_certificate",
        "passport",
        "english_test",
    ):
        item = data.get(key) or {}
        if isinstance(item, dict):
            yield key, item, False
    letters = data.get("recommendation_letters") or []
    if isinstance(letters, list):
        for item in letters:
            if isinstance(item, dict):
                yield "recommendation_letters", item, True


def find_document(
    data: dict[str, Any], document_id: str
) -> Optional[tuple[str, dict[str, Any], bool]]:
    target = str(document_id)
    for slot, item, is_list in _iter_stored_documents(data):
        item_id = item.get("id")
        if item_id is not None and str(item_id) == target:
            return slot, item, is_list
    return None


def _count_pending_letters(db: Session, user_id: int) -> int:
    now = _utc_now()
    return (
        db.query(DocumentUploadSession)
        .filter(
            DocumentUploadSession.user_id == user_id,
            DocumentUploadSession.document_type
            == ProfileDocumentType.RECOMMENDATION_LETTER.value,
            DocumentUploadSession.status == DocumentUploadSessionStatus.PENDING.value,
            DocumentUploadSession.expires_at > now,
        )
        .count()
    )


def _ensure_recommendation_capacity(db: Session, user_id: int, data: dict[str, Any]) -> None:
    max_letters = settings.S3_MAX_RECOMMENDATION_LETTERS
    current = len(data.get("recommendation_letters") or [])
    pending = _count_pending_letters(db, user_id)
    if current + pending >= max_letters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"لا يمكن رفع أكثر من {max_letters} خطابات توصية.",
        )


def _get_or_create_profile(db: Session, user: User) -> Profile:
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def create_upload_session(
    db: Session,
    user: User,
    storage: StorageClient,
    document_type: ProfileDocumentType,
    file_name: str,
    content_type: str,
    file_size: int,
) -> DocumentUploadSession:
    safe_name, extension, normalized_type = validate_upload_intent(
        document_type, file_name, content_type, file_size
    )
    profile = _get_or_create_profile(db, user)
    data = load_documents_dict(profile)
    if document_type is ProfileDocumentType.RECOMMENDATION_LETTER:
        _ensure_recommendation_capacity(db, user.id, data)

    object_key = storage.generate_object_key(
        user.id, document_type.value, extension
    )
    expires_at = _utc_now() + timedelta(
        seconds=settings.S3_PRESIGN_PUT_EXPIRE_SECONDS
    )
    session = DocumentUploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        document_type=document_type.value,
        object_key=object_key,
        original_file_name=safe_name,
        expected_content_type=normalized_type,
        expected_file_size=file_size,
        status=DocumentUploadSessionStatus.PENDING.value,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _record_from_session(
    session: DocumentUploadSession, document_id: str
) -> dict[str, Any]:
    return {
        "id": document_id,
        "document_type": session.document_type,
        "object_key": session.object_key,
        "file_name": session.original_file_name,
        "content_type": session.expected_content_type,
        "file_size": session.expected_file_size,
        "status": UploadStatus.UPLOADED.value,
        "uploaded_at": _utc_now().isoformat(),
    }


def persist_confirmed_document(
    data: dict[str, Any], session: DocumentUploadSession
) -> tuple[dict[str, Any], dict[str, Any], Optional[str]]:
    document_id = str(uuid.uuid4())
    record = _record_from_session(session, document_id)
    previous_key = None
    if session.document_type == ProfileDocumentType.RECOMMENDATION_LETTER.value:
        letters = list(data.get("recommendation_letters") or [])
        letters.append(record)
        data["recommendation_letters"] = letters
        return data, record, None

    slot = DOCUMENT_RULES[ProfileDocumentType(session.document_type)]["slot"]
    previous = data.get(slot) or {}
    if isinstance(previous, dict):
        previous_key = previous.get("object_key")
    data[slot] = record
    return data, record, previous_key


def confirm_upload_session(
    db: Session,
    user: User,
    storage: StorageClient,
    upload_id: str,
) -> dict[str, Any]:
    session = (
        db.query(DocumentUploadSession)
        .filter(DocumentUploadSession.id == upload_id)
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="جلسة الرفع غير موجودة.",
        )
    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="جلسة الرفع غير موجودة.",
        )

    if session.status == DocumentUploadSessionStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="تم تأكيد هذا الرفع مسبقاً.",
        )

    if session.status != DocumentUploadSessionStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="جلسة الرفع لم تعد صالحة.",
        )

    if _as_utc(session.expires_at) <= _utc_now():
        session.status = DocumentUploadSessionStatus.EXPIRED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="انتهت صلاحية جلسة الرفع.",
        )

    head = storage.head_object(session.object_key)
    if not head.exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لم يتم العثور على الملف المرفوع.",
        )

    actual_type = _normalize_content_type(head.content_type or "")
    if actual_type != session.expected_content_type:
        session.status = DocumentUploadSessionStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نوع الملف المرفوع لا يطابق النوع المتوقع.",
        )

    if head.content_length != session.expected_file_size:
        session.status = DocumentUploadSessionStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حجم الملف المرفوع لا يطابق الحجم المتوقع.",
        )

    profile = _get_or_create_profile(db, user)
    data = load_documents_dict(profile)
    if session.document_type == ProfileDocumentType.RECOMMENDATION_LETTER.value:
        max_letters = settings.S3_MAX_RECOMMENDATION_LETTERS
        current = len(data.get("recommendation_letters") or [])
        if current >= max_letters:
            session.status = DocumentUploadSessionStatus.FAILED.value
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"لا يمكن رفع أكثر من {max_letters} خطابات توصية.",
            )

    data, record, previous_key = persist_confirmed_document(data, session)
    session.status = DocumentUploadSessionStatus.CONFIRMED.value
    save_documents(db, profile, data)

    if previous_key and previous_key != session.object_key:
        try:
            storage.delete_object(previous_key)
        except Exception:
            # Replacement already persisted; leftover object can be cleaned later.
            pass

    return record


def create_download_url(
    db: Session,
    user: User,
    storage: StorageClient,
    document_id: str,
) -> tuple[str, int]:
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    data = load_documents_dict(profile)
    found = find_document(data, document_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="الوثيقة غير موجودة.",
        )
    _slot, item, _is_list = found
    object_key = item.get("object_key")
    if not object_key or item.get("status") != UploadStatus.UPLOADED.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="الوثيقة غير موجودة.",
        )
    expires_in = settings.S3_PRESIGN_GET_EXPIRE_SECONDS
    return storage.presign_get(object_key, expires_in), expires_in


def delete_document(
    db: Session,
    user: User,
    storage: StorageClient,
    document_id: str,
) -> None:
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    if profile is None:
        return

    documents = load_documents_dict(profile)
    found = find_document(documents, document_id)
    if found is None:
        return

    slot, item, is_list = found
    object_key = item.get("object_key")
    if object_key:
        try:
            storage.delete_object(object_key)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="تعذر حذف الملف من التخزين. لم يتم تعديل بيانات الملف الشخصي.",
            ) from exc

    if is_list:
        letters = list(documents.get("recommendation_letters") or [])
        documents["recommendation_letters"] = [
            letter for letter in letters if str(letter.get("id")) != str(document_id)
        ]
    else:
        documents[slot] = _empty_slot(slot)

    if object_key:
        db.query(DocumentUploadSession).filter(
            DocumentUploadSession.user_id == user.id,
            DocumentUploadSession.object_key == object_key,
        ).delete(synchronize_session=False)

    save_documents(db, profile, documents)

