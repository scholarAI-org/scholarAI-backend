"""merge profile and email verification migration histories

Revision ID: 20260831_01
Revises: 77b9102d722d, 20260827_02
Create Date: 2026-08-31

"""
from typing import Sequence, Union


revision: str = "20260831_01"
down_revision: Union[str, Sequence[str], None] = (
    "77b9102d722d",
    "20260827_02",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
