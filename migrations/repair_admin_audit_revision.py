"""Repair the historical audit/preferences revision collision before upgrading.

Run `python -m migrations.repair_admin_audit_revision` to preview, then add
`--apply` to update only Alembic bookkeeping after inspecting the actual schema.
"""

import argparse

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def repair_revision(connection: Connection, *, apply: bool = False) -> str:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables or "audit_logs" not in tables:
        return "No legacy admin audit revision to repair."
    versions = set(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    if versions & {
        "20260909_admin01",
        "20260910_admin01",
        "20260912_merge01",
        "20260912_notify01",
        "20260912_merge02",
    }:
        return "Admin audit revision is already recorded correctly."
    if versions not in ({"20260909_01"}, {"20260910_01"}):
        raise RuntimeError(
            "Unexpected migration versions; inspect the database before repairing"
        )
    required_audit = {
        "id",
        "admin_id",
        "admin_name",
        "action",
        "action_display",
        "entity_type",
        "entity_id",
        "entity_name",
        "details",
        "created_at",
    }
    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    if (
        not required_audit <= audit_columns
        or not {"profiles", "admin_notifications", "scholarships"} <= tables
    ):
        raise RuntimeError(
            "Incomplete legacy admin schema; refusing to stamp migrations"
        )
    preferences_applied = "detailed_specialization" in {
        column["name"] for column in inspector.get_columns("profiles")
    }
    review_columns = {
        "study_level",
        "funding_type",
        "majors",
        "required_documents",
        "updated_at",
    }
    scholarship_columns = {
        column["name"] for column in inspector.get_columns("scholarships")
    }
    review_applied = review_columns <= scholarship_columns
    if review_columns & scholarship_columns and not review_applied:
        raise RuntimeError(
            "Incomplete scholarship review schema; refusing to stamp migrations"
        )
    if not preferences_applied:
        if "auth_accounts" in tables or (
            versions == {"20260910_01"} and not review_applied
        ):
            raise RuntimeError("Inconsistent main schema; refusing to stamp migrations")
        corrected = "20260910_admin01" if review_applied else "20260909_admin01"
        description = f"Replace legacy admin stamp with {corrected}."
        if apply:
            connection.execute(
                text("UPDATE alembic_version SET version_num=:corrected"),
                {"corrected": corrected},
            )
    else:
        # The old 20260910_01 may mean review, not Google auth. Preserve only
        # the preferences stamp if review ran but Google auth has not run.
        google_pending = versions == {"20260910_01"} and "auth_accounts" not in tables
        if google_pending and not review_applied:
            raise RuntimeError("Inconsistent main schema; refusing to stamp migrations")
        corrected = "20260910_admin01" if review_applied else "20260909_admin01"
        description = "Keep main's stamp and record the already-applied admin head."
        if apply:
            if google_pending:
                connection.execute(
                    text("UPDATE alembic_version SET version_num='20260909_01'")
                )
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:corrected)"),
                {"corrected": corrected},
            )
    return ("Applied: " if apply else "Preview: ") + description


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from app.core.database import engine

    with engine.begin() as connection:
        if args.apply and connection.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE alembic_version IN EXCLUSIVE MODE"))
        print(repair_revision(connection, apply=args.apply))


if __name__ == "__main__":
    main()
