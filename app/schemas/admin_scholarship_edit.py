from pydantic import ConfigDict, Field, field_validator

from app.schemas.Scholarship import ScholarshipUpdate


class AdminScholarshipUpdate(ScholarshipUpdate):
    """Partial content corrections; identifiers and workflow fields are excluded."""

    model_config = ConfigDict(extra="forbid")

    country: str | None = Field(default=None, max_length=100)
    apply_email: str | None = Field(default=None, max_length=255)
    apply_phone: str | None = Field(default=None, max_length=50)
    study_level: str | None = Field(default=None, max_length=100)
    funding_type: str | None = Field(default=None, max_length=100)
    pdf_url: str | None = None
    attachments: list[str] | None = None
    is_extension: bool | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Title cannot be null.")
        return value
