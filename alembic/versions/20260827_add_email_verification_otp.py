"""add email verification OTP fields

Revision ID: 20260827_02
Revises: 20260827_01
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_02"
down_revision: Union[str, Sequence[str], None] = "20260827_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_email_verified" not in columns:
        # Existing accounts predate verification, so keep their login behavior.
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

    optional_columns = (
        sa.Column("email_verification_otp_hash", sa.String(length=64), nullable=True),
        sa.Column("email_verification_otp_expires_at", sa.DateTime(), nullable=True),
        sa.Column("email_verification_otp_sent_at", sa.DateTime(), nullable=True),
    )
    for column in optional_columns:
        if column.name not in columns:
            op.add_column("users", column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    for name in (
        "email_verification_otp_sent_at",
        "email_verification_otp_expires_at",
        "email_verification_otp_hash",
        "is_email_verified",
    ):
        if name in columns:
            op.drop_column("users", name)
