from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, EmailStr


class ScholarshipBase(BaseModel):
    source: str
    source_id: Optional[str] = None
    title: str
    slug: Optional[str] = None
    source_url: Optional[str] = None

    organization_name: Optional[str] = None
    country: Optional[str] = None
    deadline: Optional[date] = None
    no_deadline: Optional[bool] = False
    image_url: Optional[str] = None

    description_html: Optional[str] = None
    benefits_html: Optional[str] = None
    qualifications_html: Optional[str] = None

    apply_link: Optional[str] = None
    apply_email: Optional[str] = None
    apply_phone: Optional[str] = None

    pdf_url: Optional[str] = None
    attachments: Optional[List[str]] = []
    is_extension: Optional[bool] = False

    status: Optional[str] = "pending"
    scraped_at: Optional[datetime] = None


class ScholarshipCreate(ScholarshipBase):
    pass 


class ScholarshipResponse(ScholarshipBase):
    id: int
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None

    class Config:
        from_attributes = True


class ScholarshipExistsResponse(BaseModel):
    exists: bool
    scholarship_id: Optional[int] = None