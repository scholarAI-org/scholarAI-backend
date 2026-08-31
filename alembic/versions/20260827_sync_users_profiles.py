"""sync users, profiles, and remaining schema with models

Revision ID: 20260827_01
Revises: 20260826_01
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "20260827_01"
down_revision: Union[str, Sequence[str], None] = "20260826_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _ensure_column(table: str, column: sa.Column) -> None:
    if column.name not in _column_names(table):
        op.add_column(table, column)


def _ensure_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    inspector = _inspector()
    existing_indexes = inspector.get_indexes(table)
    if any(index.get("name") == name for index in existing_indexes):
        return
    if unique:
        for index in existing_indexes:
            if index.get("unique") and index.get("column_names") == columns:
                return
        for constraint in inspector.get_unique_constraints(table):
            if constraint.get("column_names") == columns:
                return
    op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=True, server_default="student"),
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        if "full_name" not in _column_names("users"):
            op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))
            op.execute(
                sa.text(
                    "UPDATE users SET full_name = COALESCE(NULLIF(full_name, ''), email, 'user')"
                )
            )
            op.alter_column("users", "full_name", existing_type=sa.String(), nullable=False)
        _ensure_column("users", sa.Column("email", sa.String(), nullable=False))
        _ensure_column("users", sa.Column("hashed_password", sa.String(), nullable=False))
        _ensure_column(
            "users",
            sa.Column("role", sa.String(), nullable=True, server_default="student"),
        )
        _ensure_column(
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
        )
        _ensure_column("users", sa.Column("created_at", sa.DateTime(), nullable=True))

    _ensure_index("ix_users_id", "users", ["id"])
    _ensure_index("ix_users_email", "users", ["email"], unique=True)

    if not _has_table("profiles"):
        op.create_table(
            "profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=False),
            sa.Column("gender", sa.String(), nullable=False),
            sa.Column("marital_status", sa.String(), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=False),
            sa.Column("country_of_birth", sa.String(), nullable=True),
            sa.Column("nationality", sa.String(), nullable=False),
            sa.Column("country_of_residence", sa.String(), nullable=False),
            sa.Column("id_type", sa.String(), nullable=True),
            sa.Column("id_number", sa.String(), nullable=True),
            sa.Column("father_name", sa.String(), nullable=True),
            sa.Column("mother_name", sa.String(), nullable=True),
            sa.Column("father_income", sa.Float(), nullable=True, server_default="0"),
            sa.Column("mother_income", sa.Float(), nullable=True, server_default="0"),
            sa.Column("num_of_siblings", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("currency", sa.String(), nullable=True, server_default="USD"),
            sa.Column("country", sa.String(), nullable=False),
            sa.Column("city", sa.String(), nullable=False),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("phone_number", sa.String(), nullable=False),
            sa.Column("degree", sa.String(), nullable=False),
            sa.Column("major", sa.String(), nullable=False),
            sa.Column("institution_name", sa.String(), nullable=False),
            sa.Column("graduation_year", sa.Integer(), nullable=False),
            sa.Column("gpa", sa.Float(), nullable=False),
            sa.Column("gpa_scale", sa.String(), nullable=True, server_default="100"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
    else:
        profile_columns = [
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("full_name", sa.String(), nullable=True),
            sa.Column("gender", sa.String(), nullable=True),
            sa.Column("marital_status", sa.String(), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("country_of_birth", sa.String(), nullable=True),
            sa.Column("nationality", sa.String(), nullable=True),
            sa.Column("country_of_residence", sa.String(), nullable=True),
            sa.Column("id_type", sa.String(), nullable=True),
            sa.Column("id_number", sa.String(), nullable=True),
            sa.Column("father_name", sa.String(), nullable=True),
            sa.Column("mother_name", sa.String(), nullable=True),
            sa.Column("father_income", sa.Float(), nullable=True, server_default="0"),
            sa.Column("mother_income", sa.Float(), nullable=True, server_default="0"),
            sa.Column("num_of_siblings", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("currency", sa.String(), nullable=True, server_default="USD"),
            sa.Column("country", sa.String(), nullable=True),
            sa.Column("city", sa.String(), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("phone_number", sa.String(), nullable=True),
            sa.Column("degree", sa.String(), nullable=True),
            sa.Column("major", sa.String(), nullable=True),
            sa.Column("institution_name", sa.String(), nullable=True),
            sa.Column("graduation_year", sa.Integer(), nullable=True),
            sa.Column("gpa", sa.Float(), nullable=True),
            sa.Column("gpa_scale", sa.String(), nullable=True, server_default="100"),
        ]
        for column in profile_columns:
            _ensure_column("profiles", column)

        existing_fks = _inspector().get_foreign_keys("profiles")
        has_user_fk = any(fk.get("referred_table") == "users" for fk in existing_fks)
        if not has_user_fk:
            op.create_foreign_key(
                "fk_profiles_user_id_users",
                "profiles",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )

    _ensure_index("ix_profiles_id", "profiles", ["id"])

    if not _has_table("work_experiences"):
        op.create_table(
            "work_experiences",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("company_name", sa.String(), nullable=False),
            sa.Column("role_title", sa.String(), nullable=True),
            sa.Column("employment_type", sa.String(), nullable=True),
            sa.Column("location", sa.String(), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=True, server_default=sa.false()),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _ensure_column("work_experiences", sa.Column("profile_id", sa.Integer(), nullable=True))
        _ensure_column("work_experiences", sa.Column("company_name", sa.String(), nullable=True))
        _ensure_column("work_experiences", sa.Column("role_title", sa.String(), nullable=True))
        _ensure_column("work_experiences", sa.Column("employment_type", sa.String(), nullable=True))
        _ensure_column("work_experiences", sa.Column("location", sa.String(), nullable=True))
        _ensure_column("work_experiences", sa.Column("start_date", sa.Date(), nullable=True))
        _ensure_column("work_experiences", sa.Column("end_date", sa.Date(), nullable=True))
        _ensure_column(
            "work_experiences",
            sa.Column("is_current", sa.Boolean(), nullable=True, server_default=sa.false()),
        )

    _ensure_index("ix_work_experiences_id", "work_experiences", ["id"])

    if not _has_table("language_details"):
        op.create_table(
            "language_details",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("language_name", sa.String(), nullable=False),
            sa.Column("proficiency_level", sa.String(), nullable=True),
            sa.Column("certificate_url", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _ensure_column("language_details", sa.Column("profile_id", sa.Integer(), nullable=True))
        _ensure_column("language_details", sa.Column("language_name", sa.String(), nullable=True))
        _ensure_column(
            "language_details",
            sa.Column("proficiency_level", sa.String(), nullable=True),
        )
        _ensure_column(
            "language_details",
            sa.Column("certificate_url", sa.String(), nullable=True),
        )

    _ensure_index("ix_language_details_id", "language_details", ["id"])


def downgrade() -> None:
    if _has_table("language_details"):
        op.drop_table("language_details")
    if _has_table("work_experiences"):
        op.drop_table("work_experiences")
    if _has_table("profiles"):
        op.drop_table("profiles")
    if _has_table("users"):
        op.drop_table("users")
