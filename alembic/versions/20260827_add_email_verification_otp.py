"""add email verification OTP fields

Revision ID: 20260827_02
Revises: 20260827_01
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260827_02"
down_revision: Union[str, Sequence[str], None] = "20260827_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing accounts predate email verification, so keep their login behavior.
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(sa.text("UPDATE users SET is_email_verified = true"))
    op.add_column(
        "users",
        sa.Column("email_verification_otp_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_otp_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_otp_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verification_otp_sent_at")
    op.drop_column("users", "email_verification_otp_expires_at")
    op.drop_column("users", "email_verification_otp_hash")
    op.drop_column("users", "is_email_verified")
