"""add profile avatar metadata columns

Revision ID: 20260906_02
Revises: 20260906_01
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260906_02"
down_revision: str | Sequence[str] | None = "20260906_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profiles", sa.Column("avatar_object_key", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "profiles", sa.Column("avatar_file_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "profiles", sa.Column("avatar_content_type", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "profiles", sa.Column("avatar_file_size", sa.Integer(), nullable=True)
    )
    op.add_column(
        "profiles",
        sa.Column("avatar_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profiles", "avatar_uploaded_at")
    op.drop_column("profiles", "avatar_file_size")
    op.drop_column("profiles", "avatar_content_type")
    op.drop_column("profiles", "avatar_file_name")
    op.drop_column("profiles", "avatar_object_key")
