"""allow nullable legacy profile full name

Revision ID: 77b9102d722d
Revises: 5f92f24a60ab
Create Date: 2026-08-30 20:35:59.947645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77b9102d722d'
down_revision: Union[str, Sequence[str], None] = '5f92f24a60ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow legacy profiles to be created without the retired full_name field."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "profiles" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("profiles")}
    if "full_name" in columns and not columns["full_name"]["nullable"]:
        op.alter_column(
            "profiles",
            "full_name",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    """Restore the old constraint after ensuring no NULL values remain."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "profiles" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("profiles")}
    if "full_name" in columns and columns["full_name"]["nullable"]:
        op.execute(sa.text("UPDATE profiles SET full_name = '' WHERE full_name IS NULL"))
        op.alter_column(
            "profiles",
            "full_name",
            existing_type=sa.String(),
            nullable=False,
        )
