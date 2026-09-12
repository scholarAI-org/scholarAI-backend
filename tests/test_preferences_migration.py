import os
import subprocess
import sys

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def test_preferences_migration_has_one_head_and_preserves_existing_history():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260912_notify01"]
    migration = script.get_revision("20260909_01")
    assert migration.down_revision == "20260907_02"
    assert script.get_revision("20260907_01").down_revision == "20260906_02"


@pytest.mark.skipif(
    not os.getenv("PREFERENCES_MIGRATION_TEST_DATABASE_URL"),
    reason="Requires a disposable local PostgreSQL database for migration checks.",
)
def test_upgrade_preserves_targets_and_legacy_arrays_and_downgrade_guards_data():
    url = os.environ["PREFERENCES_MIGRATION_TEST_DATABASE_URL"]
    engine = create_engine(url)
    assert engine.url.host in {"localhost", "127.0.0.1"}
    assert engine.url.database.startswith("scholarai_academic_test_")

    def migrate(operation, target):
        return subprocess.run(
            [sys.executable, "-m", "alembic", operation, target],
            env=os.environ | {"DATABASE_URL": url},
            capture_output=True,
            text=True,
            check=False,
        )

    try:
        initialized = migrate("upgrade", "head")
        assert initialized.returncode == 0, initialized.stderr
        before = migrate("downgrade", "20260907_02")
        assert before.returncode == 0, before.stderr
        with engine.begin() as connection:
            owner = connection.execute(
                text(
                    "INSERT INTO users (full_name,email,hashed_password) VALUES "
                    "('Migration Test','preferences-migration@example.com','unused') RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO profiles (user_id, field_of_study, target_field_of_study, "
                    "target_field_of_study_openalex_id, preferred_fields_of_study) VALUES "
                    "(:owner, 'Current field', 'Existing future field', "
                    "'https://openalex.org/subfields/1706', '[\"Different field\", \"Another field\"]')"
                ),
                {"owner": owner},
            )
        upgraded = migrate("upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr
        with engine.begin() as connection:
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("profiles")
            }
            assert columns["detailed_specialization"]["nullable"]
            assert str(columns["detailed_specialization"]["type"]) == "VARCHAR(255)"
            row = connection.execute(
                text(
                    "SELECT field_of_study, target_field_of_study, target_field_of_study_openalex_id, "
                    "preferred_fields_of_study, detailed_specialization FROM profiles WHERE user_id=:owner"
                ),
                {"owner": owner},
            ).one()
            assert tuple(row) == (
                "Current field",
                "Existing future field",
                "https://openalex.org/subfields/1706",
                ["Different field", "Another field"],
                None,
            )
            connection.execute(
                text(
                    "UPDATE profiles SET desired_degree_level='PHD', detailed_specialization='Distributed Systems' "
                    "WHERE user_id=:owner"
                ),
                {"owner": owner},
            )
        rejected = migrate("downgrade", "20260907_02")
        assert rejected.returncode != 0
        assert "Preferences downgrade stopped to protect" in rejected.stderr
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == "20260912_notify01"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT detailed_specialization FROM profiles WHERE user_id=:owner"
                    ),
                    {"owner": owner},
                ).scalar_one()
                == "Distributed Systems"
            )
            connection.execute(
                text(
                    "UPDATE profiles SET detailed_specialization=NULL WHERE user_id=:owner"
                ),
                {"owner": owner},
            )
        assert migrate("downgrade", "20260907_02").returncode == 0
        with engine.connect() as connection:
            assert "detailed_specialization" not in {
                column["name"] for column in inspect(connection).get_columns("profiles")
            }
            assert (
                connection.execute(
                    text(
                        "SELECT target_field_of_study FROM profiles WHERE user_id=:owner"
                    ),
                    {"owner": owner},
                ).scalar_one()
                == "Existing future field"
            )
        assert migrate("upgrade", "head").returncode == 0
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM users WHERE id=:owner"), {"owner": owner}
            )
    finally:
        engine.dispose()
