from datetime import date, datetime
from sqlalchemy import (
    ARRAY,
    BOOLEAN,
    DATE,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from app.core.database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"

    id = Column(Integer, primary_key=True, index=True)

    # Identification & source
    source = Column(String(20), nullable=False)  # 'for9a' or 'ministry'
    source_id = Column(String(50), nullable=True)
    title = Column(Text, nullable=False)
    slug = Column(String(100), nullable=True)
    source_url = Column(Text, nullable=True)

    # Summary fields
    organization_name = Column(Text, nullable=True)
    country = Column(String(100), nullable=True)
    deadline = Column(DATE, nullable=True)
    no_deadline = Column(BOOLEAN, default=False)
    image_url = Column(Text, nullable=True)

    # Full details
    description_html = Column(Text, nullable=True)
    benefits_html = Column(Text, nullable=True)
    qualifications_html = Column(Text, nullable=True)

    # Application info
    apply_link = Column(Text, nullable=True)
    apply_email = Column(String(255), nullable=True)
    apply_phone = Column(String(50), nullable=True)

    # Ministry-source-specific fields
    pdf_url = Column(Text, nullable=True)
    attachments = Column(ARRAY(Text), nullable=True)
    is_extension = Column(BOOLEAN, default=False)

    # Review workflow
    status = Column(String(20), default="pending")  # 'pending' | 'published' | 'rejected'
    scraped_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="unique_source_record"),
    )