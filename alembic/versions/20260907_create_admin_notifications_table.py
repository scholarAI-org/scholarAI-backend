"""create admin notifications table

Revision ID: 20260907_01
Revises: 20260906_02
Create Date: 2026-09-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_01"
down_revision: str | Sequence[str] | None = "20260906_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False, server_default="general"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_notifications_id", "admin_notifications", ["id"], unique=False
    )
    op.create_index(
        "ix_admin_notifications_is_read", "admin_notifications", ["is_read"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_admin_notifications_is_read", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_id", table_name="admin_notifications")
    op.drop_table("admin_notifications")
