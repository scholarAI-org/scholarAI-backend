"""replace the legacy profile schema with profile v2

Revision ID: 1023f6ed1956
Revises: 20260827_01
Create Date: 2026-09-02 12:16:56.936945

The profile-v2 API is not compatible with the legacy profile, work-experience,
and language tables. This migration deliberately refuses to rebuild populated
legacy tables so an operator cannot lose user data accidentally.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1023f6ed1956"
down_revision: str | Sequence[str] | None = "20260827_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _row_count(table_name: str) -> int:
    if not _has_table(table_name):
        return 0
    quoted_name = op.get_bind().dialect.identifier_preparer.quote(table_name)
    return op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {quoted_name}")
    ).scalar_one()


def _drop_empty_legacy_profile_schema() -> None:
    legacy_tables = ("profiles", "work_experiences", "language_details")
    populated = [name for name in legacy_tables if _row_count(name)]
    if populated:
        names = ", ".join(populated)
        raise RuntimeError(
            "Profile-v2 migration stopped to protect legacy data in: " + names
        )

    # Child tables must be removed before profiles because of foreign keys.
    for table_name in ("language_details", "work_experiences", "profiles"):
        if _has_table(table_name):
            op.drop_table(table_name)


def _create_profiles() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=50), nullable=True),
        sa.Column("last_name", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column(
            "gender",
            sa.Enum("MALE", "FEMALE", name="gender"),
            nullable=True,
        ),
        sa.Column("nationality", sa.String(length=2), nullable=True),
        sa.Column("country_of_residence", sa.String(length=2), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column(
            "financial_status",
            sa.Enum("LIMITED", "MODERATE", "STABLE", name="financialstatus"),
            nullable=True,
        ),
        sa.Column("id_number", sa.String(length=9), nullable=True),
        sa.Column("passport_number", sa.String(length=20), nullable=True),
        sa.Column(
            "academic_level",
            sa.Enum("BACHELOR", "MASTER", "PHD", name="academiclevel"),
            nullable=True,
        ),
        sa.Column(
            "field_of_study",
            sa.Enum(
                "ENGINEERING",
                "COMPUTER_SCIENCE",
                "MEDICINE",
                "BUSINESS",
                "ARTS",
                "OTHER",
                name="fieldofstudy",
            ),
            nullable=True,
        ),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("gpa_value", sa.Float(), nullable=True),
        sa.Column(
            "gpa_scale",
            sa.Enum(
                "SCALE_4",
                "SCALE_5",
                "SCALE_10",
                "SCALE_100",
                name="gpascale",
            ),
            nullable=True,
        ),
        sa.Column(
            "current_study_language",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("expected_graduation_year", sa.Integer(), nullable=True),
        sa.Column(
            "documents",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "languages_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "skills_data",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "desired_degree_level",
            sa.Enum(
                "BACHELOR",
                "MASTER",
                "PHD",
                "DIPLOMA",
                "OTHER",
                name="desireddegreelevel",
            ),
            nullable=True,
        ),
        sa.Column(
            "funding_type",
            sa.Enum("FULL", "PARTIAL", "SELF", "ANY", name="fundingtype"),
            nullable=True,
        ),
        sa.Column(
            "preferred_fields_of_study",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "preferred_countries",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "is_completed",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
        sa.Column(
            "profile_completion_percentage",
            sa.Float(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_profiles_id", "profiles", ["id"], unique=False)
    op.create_index("ix_profiles_email", "profiles", ["email"], unique=False)


def _create_experiences() -> None:
    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column(
            "experience_type",
            sa.Enum(
                "WORK",
                "VOLUNTEER",
                "RESEARCH",
                "STUDENT_ACTIVITY",
                name="experiencetype",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("organization", sa.String(length=250), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiences_id", "experiences", ["id"], unique=False)


def upgrade() -> None:
    if _has_table("profiles") and "first_name" not in _columns("profiles"):
        _drop_empty_legacy_profile_schema()

    if not _has_table("profiles"):
        _create_profiles()
    if not _has_table("experiences"):
        _create_experiences()


def downgrade() -> None:
    populated = [name for name in ("experiences", "profiles") if _row_count(name)]
    if populated:
        names = ", ".join(populated)
        raise RuntimeError(
            "Profile-v2 downgrade stopped to protect current data in: " + names
        )

    if _has_table("experiences"):
        op.drop_table("experiences")
    if _has_table("profiles"):
        op.drop_table("profiles")
