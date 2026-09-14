"""add scholarship eligibility_criteria

Revision ID: 20260914_eligibility01
Revises: 20260912_reject01
Create Date: 2026-09-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_eligibility01"
down_revision: str | Sequence[str] | None = "20260912_reject01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scholarships",
        sa.Column(
            "eligibility_criteria",
            sa.JSON(),
            nullable=True,
            comment="شروط الأهلية: قائمة شروط الأهلية أو مؤهلات التقديم",
        ),
    )


def downgrade() -> None:
    op.drop_column("scholarships", "eligibility_criteria")
