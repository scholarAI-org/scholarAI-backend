"""Add notification metadata, private recipients, and independent admin reads.

Revision ID: 20260912_notify01
Revises: 20260912_merge01
"""

import sqlalchemy as sa

from alembic import op

revision = "20260912_notify01"
down_revision = "20260912_merge01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing content and legacy read fields remain intact as a frozen baseline.
    op.add_column(
        "admin_notifications", sa.Column("recipient_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "admin_notifications",
        sa.Column("related_entity_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "admin_notifications", sa.Column("action_type", sa.String(50), nullable=True)
    )
    op.add_column(
        "admin_notifications", sa.Column("event_key", sa.String(255), nullable=True)
    )
    op.create_foreign_key(
        "fk_admin_notifications_recipient",
        "admin_notifications",
        "users",
        ["recipient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_admin_notifications_event_key", "admin_notifications", ["event_key"]
    )
    op.create_index(
        "ix_admin_notifications_recipient_created",
        "admin_notifications",
        ["recipient_id", "created_at", "id"],
    )
    op.create_table(
        "admin_notification_reads",
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["admin_notifications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("admin_id", "notification_id"),
    )


def downgrade() -> None:
    # The old schema cannot represent private audiences or per-admin reads.
    # Refuse to lose those semantics rather than silently exposing private content.
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM admin_notification_reads) OR EXISTS "
            "(SELECT 1 FROM admin_notifications WHERE recipient_id IS NOT NULL "
            "OR related_entity_id IS NOT NULL OR action_type IS NOT NULL OR event_key IS NOT NULL)"
        )
    ).scalar():
        raise RuntimeError(
            "Notification downgrade stopped to protect notification metadata and per-admin state"
        )
    op.drop_table("admin_notification_reads")
    op.drop_index(
        "ix_admin_notifications_recipient_created", table_name="admin_notifications"
    )
    op.drop_constraint(
        "uq_admin_notifications_event_key", "admin_notifications", type_="unique"
    )
    op.drop_constraint(
        "fk_admin_notifications_recipient", "admin_notifications", type_="foreignkey"
    )
    for column in ("event_key", "action_type", "related_entity_id", "recipient_id"):
        op.drop_column("admin_notifications", column)
