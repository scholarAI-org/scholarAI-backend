import os
import subprocess
import sys

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

MIGRATION_DATABASE = os.getenv("ACADEMIC_MIGRATION_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not MIGRATION_DATABASE,
    reason="Requires a disposable local PostgreSQL database for Alembic verification.",
)


def migrate(target, operation="upgrade"):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = MIGRATION_DATABASE
    result = subprocess.run(
        [sys.executable, "-m", "alembic", operation, target],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def test_upgrade_preserves_legacy_data_and_downgrade_protects_new_values():
    engine = create_engine(MIGRATION_DATABASE)
    assert engine.url.host in {"localhost", "127.0.0.1"}
    assert engine.url.database.startswith("scholarai_academic_test_")
    try:
        assert migrate("head").returncode == 0
        assert migrate("20260906_02", "downgrade").returncode == 0
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (full_name, email, hashed_password, is_email_verified) "
                    "VALUES ('Legacy User', 'academic-migration@example.com', 'unused', true) RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO profiles (user_id, academic_level, field_of_study, institution, gpa_value, gpa_scale) "
                    "VALUES (:user_id, 'BACHELOR', 'COMPUTER_SCIENCE', 'Legacy University', 3.2, 'SCALE_4')"
                ),
                {"user_id": user_id},
            )
        result = migrate("head")
        assert result.returncode == 0, result.stderr
        with engine.connect() as connection:
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("profiles")
            }
            assert str(columns["field_of_study"]["type"]) == "VARCHAR(255)"
            assert columns["study_status"]["nullable"]
            saved = connection.execute(
                text(
                    "SELECT field_of_study, institution, gpa_value, study_status, target_field_of_study "
                    "FROM profiles WHERE user_id=:user_id"
                ),
                {"user_id": user_id},
            ).one()
            assert tuple(saved) == (
                "COMPUTER_SCIENCE",
                "Legacy University",
                3.2,
                None,
                None,
            )
        # A legacy-only populated database can be downgraded and upgraded safely.
        assert migrate("20260906_02", "downgrade").returncode == 0
        assert migrate("head").returncode == 0
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE profiles SET field_of_study='Software Engineering', "
                    "field_of_study_openalex_id='https://openalex.org/subfields/1702', "
                    "study_status='CURRENTLY_STUDYING', target_field_of_study='Artificial Intelligence' "
                    "WHERE user_id=:user_id"
                ),
                {"user_id": user_id},
            )
        rejected = migrate("20260906_02", "downgrade")
        assert rejected.returncode != 0
        assert "Academic downgrade stopped to protect" in rejected.stderr
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
            )
            assert (
                connection.execute(
                    text("SELECT field_of_study FROM profiles WHERE user_id=:user_id"),
                    {"user_id": user_id},
                ).scalar_one()
                == "Software Engineering"
            )
            connection.execute(
                text("DELETE FROM users WHERE id=:user_id"), {"user_id": user_id}
            )
    finally:
        engine.dispose()


def test_completion_flag_migration_preserves_existing_academic_values():
    engine = create_engine(MIGRATION_DATABASE)
    assert engine.url.host in {"localhost", "127.0.0.1"}
    assert engine.url.database.startswith("scholarai_academic_test_")
    try:
        assert migrate("20260907_01", "downgrade").returncode == 0
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (full_name, email, hashed_password, is_email_verified) "
                    "VALUES ('Flags Test', 'completion-migration@example.com', 'unused', true) RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO profiles (user_id, field_of_study) VALUES (:id, 'Software Engineering')"
                ),
                {"id": user_id},
            )
        assert migrate("head").returncode == 0
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT field_of_study, has_experience, open_to_all_countries FROM profiles WHERE user_id=:id"
                ),
                {"id": user_id},
            ).one()
            assert tuple(row) == ("Software Engineering", None, None)
            connection.execute(
                text(
                    "UPDATE profiles SET has_experience=false, open_to_all_countries=true WHERE user_id=:id"
                ),
                {"id": user_id},
            )
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT has_experience, open_to_all_countries FROM profiles WHERE user_id=:id"
                ),
                {"id": user_id},
            ).one()
            assert tuple(row) == (False, True)
        assert migrate("20260907_01", "downgrade").returncode == 0
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT field_of_study FROM profiles WHERE user_id=:id"),
                    {"id": user_id},
                ).scalar_one()
                == "Software Engineering"
            )
        assert migrate("head").returncode == 0
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
    finally:
        engine.dispose()
