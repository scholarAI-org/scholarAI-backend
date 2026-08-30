"""repair profile schema

Revision ID: 5f92f24a60ab
Revises: 
Create Date: 2026-08-30 20:10:11.934008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5f92f24a60ab'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Move the profile schema to ``profiles`` without deleting legacy data."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "profiles" not in inspector.get_table_names():
        return

    enum_types = {
        "gender": ("MALE", "FEMALE"),
        "financialstatus": ("LIMITED", "MODERATE", "STABLE"),
        "passportavailability": ("AVAILABLE", "IN_PROGRESS", "NOT_AVAILABLE"),
        "fieldofstudy": ("ENGINEERING", "COMPUTER_SCIENCE", "MEDICINE", "BUSINESS", "ARTS", "OTHER"),
        "academiclevel": ("BACHELOR", "MASTER", "PHD"),
        "gpascale": ("SCALE_4", "SCALE_5", "SCALE_10", "SCALE_100"),
        "desireddegreelevel": ("BACHELOR", "MASTER", "PHD", "DIPLOMA", "OTHER"),
        "fundingtype": ("FULL", "PARTIAL", "SELF", "ANY"),
    }
    for name, values in enum_types.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    enum = lambda name, *values: postgresql.ENUM(*values, name=name, create_type=False)
    columns = {
        "first_name": sa.String(length=50),
        "last_name": sa.String(length=50),
        "phone_number": sa.String(length=30),
        "gender": enum("gender", *enum_types["gender"]),
        "birth_date": sa.Date(),
        "nationality": sa.String(length=2),
        "country_of_residence": sa.String(length=2),
        "city": sa.String(length=100),
        "financial_status": enum("financialstatus", *enum_types["financialstatus"]),
        "id_number": sa.String(length=50),
        "passport_status": enum("passportavailability", *enum_types["passportavailability"]),
        "field_of_study": enum("fieldofstudy", *enum_types["fieldofstudy"]),
        "academic_level": enum("academiclevel", *enum_types["academiclevel"]),
        "gpa_value": sa.Float(),
        "gpa_scale": enum("gpascale", *enum_types["gpascale"]),
        "institution": sa.String(length=255),
        "current_study_language": postgresql.ARRAY(sa.String()),
        "expected_graduation_year": sa.Integer(),
        "documents_data": sa.JSON(),
        "languages_data": sa.JSON(),
        "skills_data": sa.JSON(),
        "desired_degree_level": enum("desireddegreelevel", *enum_types["desireddegreelevel"]),
        "funding_type": enum("fundingtype", *enum_types["fundingtype"]),
        "preferred_fields_of_study": sa.JSON(),
        "preferred_countries": sa.JSON(),
        "is_completed": sa.Boolean(),
    }

    existing_profile_columns = {column["name"] for column in inspector.get_columns("profiles")}
    added_columns = []
    for name, column_type in columns.items():
        if name not in existing_profile_columns:
            op.add_column("profiles", sa.Column(name, column_type, nullable=True))
            added_columns.append(name)

    # Earlier code mistakenly placed these columns on ``experiences``. Preserve
    # any values by copying the newest experience row for each profile. Legacy
    # columns are deliberately retained and can be removed in a later cleanup.
    if "experiences" in inspector.get_table_names() and added_columns:
        experience_columns = {column["name"] for column in inspector.get_columns("experiences")}
        copy_columns = [name for name in added_columns if name in experience_columns]
        if copy_columns:
            assignments = ", ".join(
                f"{name} = COALESCE(p.{name}, e.{name})" for name in copy_columns
            )
            op.execute(
                sa.text(
                    "UPDATE profiles AS p "
                    f"SET {assignments} "
                    "FROM (SELECT DISTINCT ON (profile_id) * FROM experiences "
                    "ORDER BY profile_id, id DESC) AS e "
                    "WHERE p.id = e.profile_id"
                )
            )


def downgrade() -> None:
    """This migration intentionally preserves legacy data and is not reversible."""
    raise NotImplementedError("Restore a database backup instead of downgrading this data-preserving migration.")
