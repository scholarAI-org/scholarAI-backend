from pydantic import BaseModel, ConfigDict, Field


class ScholarshipReviewDetailsResponse(BaseModel):
    title: str | None = None
    organization_name: str | None = None
    country: str | None = None
    description: str | None = Field(
        default=None, description="Full source HTML from description_html."
    )
    additional_details: str | None = Field(
        default=None,
        description="Null: no separate additional details are stored in the current schema.",
    )

    model_config = ConfigDict(from_attributes=True)
