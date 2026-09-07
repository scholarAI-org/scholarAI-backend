"""enforce normalized language and skill validation

Revision ID: 20260906_03
Revises: 20260906_02
Create Date: 2026-09-06

Languages and skills are stored as JSON arrays on profiles, so conventional
per-element unique indexes are not possible. Immutable validation functions and
CHECK constraints protect direct/concurrent database writes. Existing invalid
or duplicate data is reported by profile ID and is never changed automatically.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260906_03"
down_revision: str | Sequence[str] | None = "20260906_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SKILLS_FUNCTION = "scholarai_profile_skills_are_valid"
LANGUAGES_FUNCTION = "scholarai_profile_languages_are_valid"
SKILLS_CONSTRAINT = "ck_profiles_skills_valid_unique_normalized"
LANGUAGES_CONSTRAINT = "ck_profiles_languages_valid_unique_normalized"


def _create_validation_functions() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {SKILLS_FUNCTION}(values_json json)
            RETURNS boolean
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT CASE
                    WHEN values_json IS NULL THEN TRUE
                    WHEN json_typeof(values_json) <> 'array' THEN FALSE
                    WHEN json_array_length(values_json) > 100 THEN FALSE
                    ELSE json_array_length(values_json) = (
                        SELECT count(DISTINCT lower(btrim(item.value #>> '{{}}')))
                        FROM json_array_elements(values_json) AS item(value)
                        WHERE json_typeof(item.value) = 'string'
                          AND length(btrim(item.value #>> '{{}}')) BETWEEN 2 AND 100
                    )
                END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {LANGUAGES_FUNCTION}(values_json json)
            RETURNS boolean
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT CASE
                    WHEN values_json IS NULL THEN TRUE
                    WHEN json_typeof(values_json) <> 'array' THEN FALSE
                    WHEN json_array_length(values_json) > 50 THEN FALSE
                    ELSE json_array_length(values_json) = (
                        SELECT count(DISTINCT lower(btrim(item.value ->> 'name')))
                        FROM json_array_elements(values_json) AS item(value)
                        WHERE json_typeof(item.value) = 'object'
                          AND json_typeof(item.value -> 'name') = 'string'
                          AND length(btrim(item.value ->> 'name')) BETWEEN 2 AND 50
                          AND item.value ->> 'proficiency' IN (
                              'BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'NATIVE'
                          )
                    )
                END
            $$
            """
        )
    )


def _invalid_profiles() -> list[tuple[int, str]]:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
            SELECT id,
                   concat_ws(', ',
                       CASE WHEN NOT {LANGUAGES_FUNCTION}(languages_data)
                            THEN 'languages' END,
                       CASE WHEN NOT {SKILLS_FUNCTION}(skills_data)
                            THEN 'skills' END
                   ) AS invalid_fields
            FROM profiles
            WHERE NOT {LANGUAGES_FUNCTION}(languages_data)
               OR NOT {SKILLS_FUNCTION}(skills_data)
            ORDER BY id
            LIMIT 20
            """
            )
        )
        .all()
    )
    return [(int(row.id), str(row.invalid_fields)) for row in rows]


def upgrade() -> None:
    _create_validation_functions()
    invalid_profiles = _invalid_profiles()
    if invalid_profiles:
        details = "; ".join(
            f"profile {profile_id}: {fields}" for profile_id, fields in invalid_profiles
        )
        raise RuntimeError(
            "Migration stopped: invalid or case-insensitive duplicate profile "
            f"values must be resolved explicitly before retrying ({details})."
        )

    op.create_check_constraint(
        LANGUAGES_CONSTRAINT,
        "profiles",
        f"{LANGUAGES_FUNCTION}(languages_data)",
    )
    op.create_check_constraint(
        SKILLS_CONSTRAINT,
        "profiles",
        f"{SKILLS_FUNCTION}(skills_data)",
    )


def downgrade() -> None:
    op.drop_constraint(SKILLS_CONSTRAINT, "profiles", type_="check")
    op.drop_constraint(LANGUAGES_CONSTRAINT, "profiles", type_="check")
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {SKILLS_FUNCTION}(json)"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {LANGUAGES_FUNCTION}(json)"))
