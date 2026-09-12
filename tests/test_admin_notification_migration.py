import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

from migrations.repair_admin_audit_revision import repair_revision


@pytest.fixture
def migration_engine():
    url = os.getenv("NOTIFICATIONS_MIGRATION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires a disposable local PostgreSQL migration database")
    engine = create_engine(url)
    assert engine.url.host in {"localhost", "127.0.0.1"}
    assert engine.url.database.startswith("scholarai_notifications_test")
    # This database is exclusively for destructive migration checks.
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def migrate(engine, operation, target):
    return subprocess.run(
        [sys.executable, "-m", "alembic", operation, target],
        env=os.environ
        | {"DATABASE_URL": engine.url.render_as_string(hide_password=False)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_upgrade_preserves_legacy_and_safe_downgrade(migration_engine):
    engine = migration_engine
    result = migrate(engine, "upgrade", "20260912_merge01")
    assert result.returncode == 0, result.stderr
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO admin_notifications (title,message,notification_type,is_read,read_at) VALUES "
                "('Unread','Body','general',false,NULL), ('Read','Body','legacy_custom',true,'2026-01-01T00:00:00Z')"
            )
        )
        before = connection.execute(
            text("SELECT * FROM admin_notifications ORDER BY id")
        ).all()
    result = migrate(engine, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        old_columns = "id,title,message,notification_type,is_read,created_at,read_at"
        assert (
            connection.execute(
                text(f"SELECT {old_columns} FROM admin_notifications ORDER BY id")
            ).all()
            == before
        )
        assert (
            connection.execute(
                text(
                    "SELECT recipient_id,related_entity_id,action_type,event_key FROM admin_notifications"
                )
            ).all()
            == [(None, None, None, None)] * 2
        )
        assert "admin_notification_reads" in inspect(connection).get_table_names()
    result = migrate(engine, "downgrade", "20260912_merge01")
    assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT * FROM admin_notifications ORDER BY id")
            ).all()
            == before
        )
    result = migrate(engine, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,full_name,email,hashed_password,role) VALUES (1,'Admin','admin@example.com','unused','admin')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO admin_notification_reads (admin_id,notification_id) VALUES (1,1)"
            )
        )
    rejected = migrate(engine, "downgrade", "20260912_merge01")
    assert rejected.returncode != 0
    assert "Notification downgrade stopped to protect" in rejected.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260912_notify01"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM admin_notification_reads")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize("existing", ["main", "legacy_admin", "both"])
def test_upgrade_from_main_and_repaired_existing_admin(migration_engine, existing):
    engine = migration_engine
    if existing in {"legacy_admin", "both"}:
        result = migrate(engine, "upgrade", "20260909_admin01")
        assert result.returncode == 0, result.stderr
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_logs (admin_name,action,action_display,entity_name) VALUES ('Admin','edit','Edit','Preserved')"
                )
            )
            if existing == "legacy_admin":
                connection.execute(
                    text("UPDATE alembic_version SET version_num='20260909_01'")
                )
    if existing in {"main", "both"}:
        result = migrate(engine, "upgrade", "20260910_01")
        assert result.returncode == 0, result.stderr
        if existing == "both":
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM alembic_version WHERE version_num='20260909_admin01'"
                    )
                )
    with engine.begin() as connection:
        before = connection.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).all()
        preview = repair_revision(connection)
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).all()
            == before
        )
        applied = repair_revision(connection, apply=True)
        if existing == "main":
            assert "No legacy" in preview
        else:
            assert "Preview:" in preview and "Applied:" in applied
            assert "already recorded" in repair_revision(connection, apply=True)
    result = migrate(engine, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260912_notify01"
        )
        if existing != "main":
            assert (
                connection.execute(
                    text("SELECT entity_name FROM audit_logs")
                ).scalar_one()
                == "Preserved"
            )
