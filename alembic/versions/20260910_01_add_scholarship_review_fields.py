"""add scholarship review fields and updated_at

Revision ID: 20260910_01
Revises: 20260909_01
Create Date: 2026-09-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_01"
down_revision: str | Sequence[str] | None = "20260909_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scholarships",
        sa.Column(
            "study_level",
            sa.String(length=100),
            nullable=True,
            comment="المستوى الدراسي (بكالوريوس، ماجستير، دكتوراه)",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "funding_type",
            sa.String(length=100),
            nullable=True,
            comment="التغطية المالية (ممولة بالكامل، راتب شهري + رسوم)",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "majors",
            sa.JSON(),
            nullable=True,
            comment="التخصصات المتاحة",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "required_documents",
            sa.JSON(),
            nullable=True,
            comment="المستندات المطلوبة",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="وقت آخر تحديث للبيانات",
        ),
    )


def downgrade() -> None:
    op.drop_column("scholarships", "updated_at")
    op.drop_column("scholarships", "required_documents")
    op.drop_column("scholarships", "majors")
    op.drop_column("scholarships", "funding_type")
    op.drop_column("scholarships", "study_level")
