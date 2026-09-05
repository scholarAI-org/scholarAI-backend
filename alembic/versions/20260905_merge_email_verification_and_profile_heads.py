"""merge email verification and profile migration heads

Revision ID: 20260905_01
Revises: 20260827_02, 20260903_01
Create Date: 2026-09-05

"""
from collections.abc import Sequence

revision: str = "20260905_01"
down_revision: str | Sequence[str] | None = (
    "20260827_02",
    "20260903_01",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
