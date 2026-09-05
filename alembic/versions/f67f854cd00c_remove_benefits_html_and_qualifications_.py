"""remove benefits html and qualifications html columns

Revision ID: f67f854cd00c
Revises: 20260905_01
Create Date: 2026-09-05 11:05:18.306790

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f67f854cd00c"
down_revision: str | Sequence[str] | None = "20260905_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("scholarships", "benefits_html")
    op.drop_column("scholarships", "qualifications_html")


def downgrade() -> None:
    op.add_column(
        "scholarships",
        sa.Column(
            "benefits_html",
            sa.Text(),
            nullable=True,
            comment="Benefits / funding HTML.",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "qualifications_html",
            sa.Text(),
            nullable=True,
            comment="Eligibility / qualifications HTML.",
        ),
    )
