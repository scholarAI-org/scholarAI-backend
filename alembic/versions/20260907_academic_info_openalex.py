"""Support OpenAlex academic fields and study status without rewriting legacy data.

Revision ID: 20260907_01
Revises: 20260906_02

New columns stay nullable for existing and registration-only profiles. PUT
enforces the complete academic contract. Keep the old enum for safe downgrade.
Downgrade refuses to discard new data or coerce OpenAlex names to old enum values.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260907_01"
down_revision = "20260906_02"
branch_labels = None
depends_on = None

NEW_TEXT_COLUMNS = (
    "field_of_study_openalex_id",
    "target_field_of_study",
    "target_field_of_study_openalex_id",
    "research_specialization",
    "research_specialization_openalex_id",
)
LEGACY_FIELDS = (
    "SCIENTIFIC",
    "LITERARY",
    "SHARIA",
    "INDUSTRIAL",
    "ENTREPRENEURSHIP_BUSINESS",
    "AGRICULTURAL",
    "HOME_ECONOMICS",
    "ENGINEERING",
    "COMPUTER_SCIENCE",
    "MEDICINE",
    "BUSINESS",
    "ARTS",
    "OTHER",
)
study_status = postgresql.ENUM(
    "CURRENTLY_STUDYING", "GRADUATED", name="studystatus", create_type=False
)
legacy_field_type = postgresql.ENUM(
    *LEGACY_FIELDS, name="fieldofstudy", create_type=False
)


def upgrade() -> None:
    op.alter_column(
        "profiles",
        "field_of_study",
        existing_type=legacy_field_type,
        type_=sa.String(255),
        existing_nullable=True,
        postgresql_using="field_of_study::text",
    )
    study_status.create(op.get_bind(), checkfirst=True)
    op.add_column("profiles", sa.Column("study_status", study_status, nullable=True))
    for name in NEW_TEXT_COLUMNS:
        op.add_column("profiles", sa.Column(name, sa.String(255), nullable=True))


def downgrade() -> None:
    profiles = sa.table(
        "profiles",
        sa.column("field_of_study", sa.String()),
        sa.column("study_status", sa.String()),
        *(sa.column(name, sa.String()) for name in NEW_TEXT_COLUMNS),
    )
    contains_new_data = sa.or_(
        profiles.c.field_of_study.not_in(LEGACY_FIELDS),
        profiles.c.study_status.is_not(None),
        *(profiles.c[name].is_not(None) for name in NEW_TEXT_COLUMNS),
    )
    if (
        op.get_bind()
        .execute(
            sa.select(sa.literal(1))
            .select_from(profiles)
            .where(contains_new_data)
            .limit(1)
        )
        .first()
    ):
        raise RuntimeError(
            "Academic downgrade stopped to protect OpenAlex/study-status data. "
            "Export and explicitly migrate populated new fields before downgrading."
        )
    for name in reversed(NEW_TEXT_COLUMNS):
        op.drop_column("profiles", name)
    op.drop_column("profiles", "study_status")
    study_status.drop(op.get_bind(), checkfirst=True)
    op.alter_column(
        "profiles",
        "field_of_study",
        existing_type=sa.String(255),
        type_=legacy_field_type,
        existing_nullable=True,
        postgresql_using="field_of_study::fieldofstudy",
    )
