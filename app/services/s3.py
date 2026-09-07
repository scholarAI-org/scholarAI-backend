from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Protocol

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import settings


@dataclass(frozen=True)
class ObjectHead:
    exists: bool
    content_type: Optional[str] = None
    content_length: Optional[int] = None


class StorageClient(Protocol):
    def generate_object_key(
        self, user_id: int, document_type: str, extension: str
    ) -> str:
        ...

    def presign_put(self, object_key: str, content_type: str, expires_in: int) -> str:
        ...

    def presign_get(self, object_key: str, expires_in: int) -> str:
        ...

    def head_object(self, object_key: str) -> ObjectHead:
        ...

    def get_object_bytes(self, object_key: str, max_bytes: int) -> bytes:
        ...

    def delete_object(self, object_key: str) -> None:
        ...


def generate_object_key(user_id: int, document_type: str, extension: str) -> str:
    safe_ext = extension.lower().lstrip(".")
    if document_type == "avatar":
        return f"users/{user_id}/avatar/{uuid.uuid4()}.{safe_ext}"
    return f"users/{user_id}/documents/{document_type}/{uuid.uuid4()}.{safe_ext}"


class S3Storage:
    """Thin S3 adapter. Business rules live in the documents service."""

    def __init__(self):
        client_kwargs = {
            "region_name": settings.AWS_REGION,
            "config": BotoConfig(signature_version="s3v4"),
        }
        if settings.AWS_S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        self._client = boto3.client("s3", **client_kwargs)
        self._bucket = settings.AWS_S3_BUCKET

    def generate_object_key(
        self, user_id: int, document_type: str, extension: str
    ) -> str:
        return generate_object_key(user_id, document_type, extension)

    def presign_put(self, object_key: str, content_type: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )

    def presign_get(self, object_key: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )

    def head_object(self, object_key: str) -> ObjectHead:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return ObjectHead(exists=False)
            raise
        return ObjectHead(
            exists=True,
            content_type=response.get("ContentType"),
            content_length=response.get("ContentLength"),
        )

    def get_object_bytes(self, object_key: str, max_bytes: int) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        stream = response["Body"]
        try:
            return stream.read(max_bytes + 1)
        finally:
            stream.close()

    def delete_object(self, object_key: str) -> None:
        """Idempotent delete. Missing objects are not an error."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return
            raise


_s3_storage: Optional[S3Storage] = None


def get_s3_storage() -> S3Storage:
    global _s3_storage
    if _s3_storage is None:
        _s3_storage = S3Storage()
    return _s3_storage
