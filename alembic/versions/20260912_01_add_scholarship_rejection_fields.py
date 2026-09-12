"""add scholarship rejection fields: rejection_reason, admin_id, and rejected_at

Revision ID: 20260912_reject01
Revises: 20260912_merge02
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_reject01"
down_revision: str | Sequence[str] | None = "20260912_merge02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scholarships",
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
            comment="سبب رفض المنحة",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "admin_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="معرف المشرف الذي قام برفض أو مراجعة المنحة",
        ),
    )
    op.add_column(
        "scholarships",
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="تاريخ ووقت رفض المنحة",
        ),
    )


def downgrade() -> None:
    op.drop_column("scholarships", "rejected_at")
    op.drop_column("scholarships", "admin_id")
    op.drop_column("scholarships", "rejection_reason")
