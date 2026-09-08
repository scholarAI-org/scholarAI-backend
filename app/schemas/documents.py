from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProfileDocumentType(str, Enum):
    CV = "cv"
    TRANSCRIPT = "transcript"
    GRADUATION_CERTIFICATE = "graduation_certificate"
    PASSPORT = "passport"
    RECOMMENDATION_LETTER = "recommendation_letter"
    ENGLISH_TEST = "english_test"
    MOTIVATION_LETTER = "motivation_letter"


class UploadUrlRequest(BaseModel):
    document_type: ProfileDocumentType
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=128)
    file_size: int = Field(..., gt=0)


class UploadUrlResponse(BaseModel):
    upload_id: str
    upload_url: str
    headers: Dict[str, str]
    expires_in: int


class ConfirmUploadRequest(BaseModel):
    upload_id: str = Field(..., min_length=1, max_length=36)


class AvatarUploadUrlRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=128)
    file_size: int = Field(..., gt=0)


class AvatarConfirmResponse(BaseModel):
    file_name: str
    content_type: str
    file_size: int
    uploaded_at: datetime
    avatar_url: str
    expires_in: int


class DownloadUrlResponse(BaseModel):
    download_url: str
    expires_in: int


class MessageResponse(BaseModel):
    message: str


class DocumentPublic(BaseModel):
    """Frontend-safe document metadata. Never includes object keys or URLs."""

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    document_type: Optional[str] = None
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    status: str = "NOT_UPLOADED"
    uploaded_at: Optional[datetime] = None
