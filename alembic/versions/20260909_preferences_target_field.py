"""Move target ownership to preferences and add PhD detailed specialization.

Revision ID: 20260909_01
Revises: 20260907_02

Existing target columns and the legacy preferred-fields JSON stay untouched.
No preferred-field value is selected or overwritten automatically.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260909_01"
down_revision = "20260907_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profiles", sa.Column("detailed_specialization", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    profiles = sa.table(
        "profiles", sa.column("detailed_specialization", sa.String(255))
    )
    populated = (
        op.get_bind()
        .execute(
            sa.select(sa.literal(1))
            .select_from(profiles)
            .where(profiles.c.detailed_specialization.is_not(None))
            .limit(1)
        )
        .first()
    )
    if populated:
        raise RuntimeError(
            "Preferences downgrade stopped to protect detailed specialization data. "
            "Export and explicitly migrate populated values before downgrading."
        )
    op.drop_column("profiles", "detailed_specialization")
