from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="unique_source_record"),
        Index("ix_scholarships_status", "status"),
        Index("ix_scholarships_source", "source"),
        Index("ix_scholarships_deadline", "deadline"),
        Index("ix_scholarships_country", "country"),
        {
            "comment": (
                "Scholarship listings ingested from scrapers (for9a, ministry) "
                "and held for review before publication."
            )
        },
    )

    id = Column(Integer, primary_key=True, index=True)

    # Identification & source
    source = Column(
        String(20),
        nullable=False,
        comment="Origin of the listing: 'for9a' or 'ministry'.",
    )
    source_id = Column(
        String(50),
        nullable=True,
        comment="Stable identifier from the source site, used with source to prevent duplicates.",
    )
    title = Column(Text, nullable=False, comment="Display title of the scholarship.")
    slug = Column(String(100), nullable=True, comment="URL-friendly identifier.")
    source_url = Column(Text, nullable=True, comment="Canonical page URL on the source site.")

    # Summary fields
    organization_name = Column(Text, nullable=True, comment="Granting organization.")
    country = Column(String(100), nullable=True, comment="Host or destination country.")
    deadline = Column(Date, nullable=True, comment="Application deadline when known.")
    no_deadline = Column(
        Boolean,
        default=False,
        server_default="false",
        comment="True when the listing has no fixed deadline.",
    )
    image_url = Column(Text, nullable=True, comment="Cover or listing image URL.")

    # Full details
    description_html = Column(Text, nullable=True, comment="Full description HTML from the source.")
    benefits_html = Column(Text, nullable=True, comment="Benefits / funding HTML.")
    qualifications_html = Column(Text, nullable=True, comment="Eligibility / qualifications HTML.")

    # Application info
    apply_link = Column(Text, nullable=True, comment="External application URL.")
    apply_email = Column(String(255), nullable=True, comment="Application contact email.")
    apply_phone = Column(String(50), nullable=True, comment="Application contact phone.")

    # Ministry-specific fields
    pdf_url = Column(Text, nullable=True, comment="Primary PDF attachment from ministry listings.")
    attachments = Column(
        ARRAY(Text),
        nullable=True,
        comment="Additional attachment URLs from ministry listings.",
    )
    is_extension = Column(
        Boolean,
        default=False,
        server_default="false",
        comment="True when the ministry listing extends an existing scholarship.",
    )

    # Review workflow
    status = Column(
        String(20),
        default="pending",
        server_default="pending",
        comment="Review workflow: pending, approved, or rejected.",
    )
    scraped_at = Column(DateTime(timezone=True), nullable=True, comment="When the listing was scraped.")
    reviewed_at = Column(DateTime(timezone=True), nullable=True, comment="When a reviewer last acted on the listing.")
    reviewed_by = Column(String(100), nullable=True, comment="Reviewer identifier (email or username).")