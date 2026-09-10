from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ScholarshipBase(BaseModel):
    source: str = Field(..., description="Origin of the listing, e.g. for9a or ministry.")
    source_id: Optional[str] = Field(
        default=None,
        description="Stable identifier from the source site. Used with source to prevent duplicates.",
    )
    title: str = Field(..., description="Display title of the scholarship.")
    slug: Optional[str] = Field(default=None, description="URL-friendly identifier.")
    source_url: Optional[str] = Field(
        default=None, description="Canonical page URL on the source site."
    )

    organization_name: Optional[str] = Field(default=None, description="Granting organization.")
    country: Optional[str] = Field(default=None, description="Host or destination country.")
    deadline: Optional[date] = Field(default=None, description="Application deadline when known.")
    no_deadline: Optional[bool] = Field(
        default=False, description="True when the listing has no fixed deadline."
    )
    image_url: Optional[str] = None

    description_html: Optional[str] = None

    apply_link: Optional[str] = None
    apply_email: Optional[str] = None
    apply_phone: Optional[str] = None

    pdf_url: Optional[str] = Field(
        default=None, description="Primary PDF attachment from ministry listings."
    )
    attachments: Optional[List[str]] = Field(
        default_factory=list,
        description="Additional attachment URLs from ministry listings.",
    )
    is_extension: Optional[bool] = Field(
        default=False,
        description="True when the ministry listing extends an existing scholarship.",
    )

    status: Optional[str] = Field(
        default="pending",
        description="Review workflow: pending, approved, or rejected.",
    )
    scraped_at: Optional[datetime] = Field(
        default=None, description="When the listing was scraped."
    )


class ScholarshipCreate(ScholarshipBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "for9a",
                "source_id": "12345",
                "title": "Chevening Scholarship",
                "country": "United Kingdom",
                "status": "pending",
            }
        }
    )


class ScholarshipUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, description="Display title of the scholarship.")
    organization_name: Optional[str] = Field(None, description="Granting organization.")
    country: Optional[str] = Field(None, description="Host or destination country.")
    deadline: Optional[date] = Field(None, description="Application deadline when known.")
    no_deadline: Optional[bool] = Field(None, description="True when the listing has no fixed deadline.")
    image_url: Optional[str] = None
    description_html: Optional[str] = None
    apply_link: Optional[str] = None
    apply_email: Optional[str] = None
    apply_phone: Optional[str] = None
    source_url: Optional[str] = None



class ScholarshipResponse(ScholarshipBase):
    id: int
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RecommendationScholarshipResponse(BaseModel):
    id: int
    title: str
    slug: Optional[str] = None
    country: Optional[str] = None
    deadline: Optional[date] = None
    description: Optional[str] = Field(
        default=None, description="Full description HTML from the source."
    )
    apply_link: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ScholarshipStatusDistribution(BaseModel):
    published: int = 0
    pending: int = 0
    rejected: int = 0


class ScholarshipExistsResponse(BaseModel):
    exists: bool
    scholarship_id: Optional[int] = None
