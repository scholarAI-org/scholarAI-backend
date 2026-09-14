from datetime import date, datetime
from typing import Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScholarshipReviewDetailsResponse(BaseModel):
    id: int | None = None
    title: str | None = None
    slug: str | None = None
    organization_name: str | None = None
    country: str | None = None
    study_level: str | None = Field(None, description="المستوى الدراسي (بكالوريوس، ماجستير، دكتوراه)")
    funding_type: str | None = Field(None, description="التغطية المالية (ممولة بالكامل، راتب شهري + رسوم)")
    deadline: date | None = None
    no_deadline: bool | None = False
    majors: Union[list[str], str] | None = Field(None, description="التخصصات المتاحة")
    eligibility_criteria: Union[list[str], str] | None = Field(None, description="شروط الأهلية")
    required_documents: Union[list[str], str] | None = Field(None, description="المستندات المطلوبة")
    description_html: str | None = Field(
        default=None, description="Full source HTML from description_html."
    )
    description: str | None = Field(
        default=None, description="Full source HTML from description_html for the overview card."
    )
    additional_details: str | None = Field(
        default=None,
        description="Additional details if available.",
    )
    source: str | None = None
    source_id: str | None = None
    source_url: str | None = None
    apply_link: str | None = None
    apply_email: str | None = None
    apply_phone: str | None = None
    image_url: str | None = None
    pdf_url: str | None = None
    attachments: list[str] | None = None
    is_extension: bool | None = False
    status: str | None = None
    scraped_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    rejection_reason: str | None = None
    admin_id: int | None = None
    rejected_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def populate_description_alias(self):
        if self.description is None and self.description_html is not None:
            self.description = self.description_html
        return self
