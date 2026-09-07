from __future__ import annotations

import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_upload import (
    DocumentUploadSession,
    DocumentUploadSessionStatus,
)
from app.models.profile import Profile
from app.models.user import User
from app.services.documents import (
    _as_utc,
    _get_or_create_profile,
    _normalize_content_type,
    _utc_now,
    sanitize_file_name,
)
from app.services.s3 import StorageClient

AVATAR_DOCUMENT_TYPE = "avatar"

AVATAR_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}

PIL_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _is_managed_avatar_key(user_id: int, object_key: Optional[str]) -> bool:
    return bool(object_key) and object_key.startswith(f"users/{user_id}/avatar/")


def _validate_avatar_intent(
    file_name: str, content_type: str, file_size: int
) -> tuple[str, str, str]:
    extension = Path(file_name).suffix.lower()
    if extension not in AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="امتداد صورة الأفاتار غير مسموح.",
        )
    normalized_type = _normalize_content_type(content_type)
    if normalized_type not in AVATAR_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نوع صورة الأفاتار غير مسموح.",
        )
    if file_size > settings.S3_MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حجم صورة الأفاتار يتجاوز الحد المسموح.",
        )
    return sanitize_file_name(file_name), extension, normalized_type


def create_avatar_upload_session(
    db: Session,
    user: User,
    storage: StorageClient,
    file_name: str,
    content_type: str,
    file_size: int,
) -> DocumentUploadSession:
    safe_name, extension, normalized_type = _validate_avatar_intent(
        file_name, content_type, file_size
    )
    _get_or_create_profile(db, user)
    object_key = storage.generate_object_key(user.id, AVATAR_DOCUMENT_TYPE, extension)
    session = DocumentUploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        document_type=AVATAR_DOCUMENT_TYPE,
        object_key=object_key,
        original_file_name=safe_name,
        expected_content_type=normalized_type,
        expected_file_size=file_size,
        status=DocumentUploadSessionStatus.PENDING.value,
        expires_at=_utc_now() + timedelta(seconds=settings.S3_PRESIGN_PUT_EXPIRE_SECONDS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _load_pending_avatar_session(
    db: Session, user: User, upload_id: str
) -> DocumentUploadSession:
    session = (
        db.query(DocumentUploadSession)
        .filter(DocumentUploadSession.id == upload_id)
        .first()
    )
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="جلسة الرفع غير موجودة.",
        )
    if session.document_type != AVATAR_DOCUMENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="جلسة الرفع ليست لأفاتار.",
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
    return session


def _validate_avatar_content(
    storage: StorageClient, session: DocumentUploadSession
) -> None:
    try:
        body = storage.get_object_bytes(
            session.object_key, settings.S3_MAX_AVATAR_BYTES
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تعذر قراءة صورة الأفاتار من التخزين.",
        ) from exc

    if len(body) != session.expected_file_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حجم محتوى صورة الأفاتار لا يطابق الحجم المتوقع.",
        )

    try:
        with Image.open(BytesIO(body)) as image:
            detected_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="الملف المرفوع ليس صورة صالحة.",
        ) from exc

    detected_type = PIL_IMAGE_TYPES.get(detected_format or "")
    extension = Path(session.original_file_name).suffix.lower()
    if (
        detected_type != session.expected_content_type
        or detected_type not in AVATAR_TYPES.get(extension, set())
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="محتوى الصورة لا يطابق نوع الملف وامتداده.",
        )


def confirm_avatar_upload(
    db: Session,
    user: User,
    storage: StorageClient,
    upload_id: str,
) -> tuple[Profile, str, int]:
    session = _load_pending_avatar_session(db, user, upload_id)
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

    try:
        _validate_avatar_content(storage, session)
    except HTTPException as exc:
        if exc.status_code < 500:
            session.status = DocumentUploadSessionStatus.FAILED.value
            db.commit()
        raise

    profile = _get_or_create_profile(db, user)
    previous_key = profile.avatar_object_key
    profile.avatar_object_key = session.object_key
    profile.avatar_file_name = session.original_file_name
    profile.avatar_content_type = session.expected_content_type
    profile.avatar_file_size = session.expected_file_size
    profile.avatar_uploaded_at = _utc_now()
    session.status = DocumentUploadSessionStatus.CONFIRMED.value
    db.commit()
    db.refresh(profile)

    if (
        previous_key
        and previous_key != session.object_key
        and _is_managed_avatar_key(user.id, previous_key)
    ):
        try:
            storage.delete_object(previous_key)
        except Exception:
            pass
        db.query(DocumentUploadSession).filter(
            DocumentUploadSession.user_id == user.id,
            DocumentUploadSession.object_key == previous_key,
        ).delete(synchronize_session=False)
        db.commit()

    expires_in = settings.S3_PRESIGN_GET_EXPIRE_SECONDS
    avatar_url = storage.presign_get(profile.avatar_object_key, expires_in)
    return profile, avatar_url, expires_in


def avatar_presigned_url(
    profile: Optional[Profile], storage: StorageClient
) -> Optional[str]:
    if not profile or not profile.avatar_object_key:
        return None
    return storage.presign_get(
        profile.avatar_object_key, settings.S3_PRESIGN_GET_EXPIRE_SECONDS
    )


def delete_avatar(
    db: Session,
    user: User,
    storage: StorageClient,
) -> None:
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    if profile is None or not profile.avatar_object_key:
        return

    object_key = profile.avatar_object_key
    if _is_managed_avatar_key(user.id, object_key):
        try:
            storage.delete_object(object_key)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="تعذر حذف الأفاتار من التخزين. لم يتم تعديل بيانات الملف الشخصي.",
            ) from exc

    profile.avatar_object_key = None
    profile.avatar_file_name = None
    profile.avatar_content_type = None
    profile.avatar_file_size = None
    profile.avatar_uploaded_at = None
    if _is_managed_avatar_key(user.id, object_key):
        db.query(DocumentUploadSession).filter(
            DocumentUploadSession.user_id == user.id,
            DocumentUploadSession.object_key == object_key,
        ).delete(synchronize_session=False)
    db.commit()
