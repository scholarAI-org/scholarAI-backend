"""create document upload sessions table

Revision ID: 20260906_01
Revises: f67f854cd00c
Create Date: 2026-09-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260906_01"
down_revision: str | Sequence[str] | None = "f67f854cd00c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_upload_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("expected_content_type", sa.String(length=128), nullable=False),
        sa.Column("expected_file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_document_upload_sessions_user_id",
        "document_upload_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_upload_sessions_user_id",
        table_name="document_upload_sessions",
    )
    op.drop_table("document_upload_sessions")
