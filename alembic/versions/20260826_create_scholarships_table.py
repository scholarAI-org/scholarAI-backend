"""create scholarships table

Revision ID: 20260826_01
Revises:
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260826_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scholarships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            comment="Origin of the listing: 'for9a' or 'ministry'.",
        ),
        sa.Column(
            "source_id",
            sa.String(length=50),
            nullable=True,
            comment="Stable identifier from the source site, used with source to prevent duplicates.",
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
            comment="Display title of the scholarship.",
        ),
        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=True,
            comment="URL-friendly identifier.",
        ),
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=True,
            comment="Canonical page URL on the source site.",
        ),
        sa.Column(
            "organization_name",
            sa.Text(),
            nullable=True,
            comment="Granting organization.",
        ),
        sa.Column(
            "country",
            sa.String(length=100),
            nullable=True,
            comment="Host or destination country.",
        ),
        sa.Column(
            "deadline",
            sa.Date(),
            nullable=True,
            comment="Application deadline when known.",
        ),
        sa.Column(
            "no_deadline",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="True when the listing has no fixed deadline.",
        ),
        sa.Column(
            "image_url",
            sa.Text(),
            nullable=True,
            comment="Cover or listing image URL.",
        ),
        sa.Column(
            "description_html",
            sa.Text(),
            nullable=True,
            comment="Full description HTML from the source.",
        ),
        sa.Column(
            "benefits_html",
            sa.Text(),
            nullable=True,
            comment="Benefits / funding HTML.",
        ),
        sa.Column(
            "qualifications_html",
            sa.Text(),
            nullable=True,
            comment="Eligibility / qualifications HTML.",
        ),
        sa.Column(
            "apply_link",
            sa.Text(),
            nullable=True,
            comment="External application URL.",
        ),
        sa.Column(
            "apply_email",
            sa.String(length=255),
            nullable=True,
            comment="Application contact email.",
        ),
        sa.Column(
            "apply_phone",
            sa.String(length=50),
            nullable=True,
            comment="Application contact phone.",
        ),
        sa.Column(
            "pdf_url",
            sa.Text(),
            nullable=True,
            comment="Primary PDF attachment from ministry listings.",
        ),
        sa.Column(
            "attachments",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Additional attachment URLs from ministry listings.",
        ),
        sa.Column(
            "is_extension",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="True when the ministry listing extends an existing scholarship.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=True,
            comment="Review workflow: pending, approved, or rejected.",
        ),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the listing was scraped.",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a reviewer last acted on the listing.",
        ),
        sa.Column(
            "reviewed_by",
            sa.String(length=100),
            nullable=True,
            comment="Reviewer identifier (email or username).",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id", name="unique_source_record"),
        comment=(
            "Scholarship listings ingested from scrapers (for9a, ministry) "
            "and held for review before publication."
        ),
    )
    op.create_index("ix_scholarships_status", "scholarships", ["status"], unique=False)
    op.create_index("ix_scholarships_source", "scholarships", ["source"], unique=False)
    op.create_index("ix_scholarships_deadline", "scholarships", ["deadline"], unique=False)
    op.create_index("ix_scholarships_country", "scholarships", ["country"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scholarships_country", table_name="scholarships")
    op.drop_index("ix_scholarships_deadline", table_name="scholarships")
    op.drop_index("ix_scholarships_source", table_name="scholarships")
    op.drop_index("ix_scholarships_status", table_name="scholarships")
    op.drop_table("scholarships")
