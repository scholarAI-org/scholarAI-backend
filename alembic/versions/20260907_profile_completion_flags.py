"""Add persisted profile completion choices.

Revision ID: 20260907_02
Revises: 20260907_01
"""

import sqlalchemy as sa

from alembic import op

revision = "20260907_02"
down_revision = "20260907_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("has_experience", sa.Boolean(), nullable=True))
    op.add_column(
        "profiles", sa.Column("open_to_all_countries", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("profiles", "open_to_all_countries")
    op.drop_column("profiles", "has_experience")
