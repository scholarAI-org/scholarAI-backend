import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "admin-review-statistics-test-key-at-least-32-bytes")

from app.api.admin import router
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.user import User

PATH = "/admin/scholarships/review/statistics"
NOW = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
MONDAY = datetime(2026, 9, 7, tzinfo=timezone.utc)
ZERO = {
    "pending_count": 0,
    "approved_this_week": 0,
    "reviewed_this_week": 0,
    "missing_source_url_count": 0,
}


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # Only queried columns: full scholarship loading would fail, as in existing
    # statistics fixtures. PostgreSQL-only ARRAY fields are intentionally omitted.
    scholarships = Table(
        "scholarships", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("status", String(20)),
        Column("source", String(20)),
        Column("source_url", String),
        Column("reviewed_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("scraped_at", DateTime(timezone=True)),
    )
    scholarships.create(engine)
    User.__table__.create(engine)
    AuditLog.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        for user_id, role in ((1, "admin"), (2, "student")):
            db.add(User(
                id=user_id, full_name=role, email=f"{role}@example.com",
                hashed_password="unused", role=role,
            ))
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        with sessions() as db:
            yield db

    def add_scholarship(**values):
        with engine.begin() as connection:
            result = connection.execute(scholarships.insert().values(**({
                "status": "pending", "source": "for9a",
                "source_url": "https://example.com/scholarship",
            } | values)))
            return result.inserted_primary_key[0]

    def add_audit(scholarship_id, when, action="publish", entity_type="scholarship"):
        with sessions() as db:
            db.add(AuditLog(
                admin_id=1, admin_name="admin", action=action, action_display=action,
                entity_id=scholarship_id, entity_type=entity_type,
                entity_name="Scholarship", created_at=when,
            ))
            db.commit()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client, patch(
            "app.services.admin_statistics.datetime", wraps=datetime
        ) as clock:
            clock.now.return_value = NOW
            client.headers["Authorization"] = f"Bearer {create_access_token({'sub': '1'})}"
            yield client, add_scholarship, add_audit, engine, clock
    finally:
        engine.dispose()


def statistics(client):
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == set(ZERO)
    assert all(type(value) is int for value in data.values())
    return data


def test_empty_database_returns_four_zero_counts(api):
    assert statistics(api[0]) == ZERO


def test_counts_current_statuses_across_all_sources(api):
    client, add, *_ = api
    for source in ("for9a", "ministry", "manual"):
        add(source=source)
    add(status="approved", reviewed_at=MONDAY)
    add(status="rejected", reviewed_at=MONDAY)
    add(status="pending", reviewed_at=NOW)
    for status in (None, "APPROVED", "published", "archived"):
        add(status=status, reviewed_at=NOW)
    assert statistics(client) == ZERO | {
        "pending_count": 4, "approved_this_week": 1, "reviewed_this_week": 2
    }


def test_approval_audit_has_priority_over_review_date_and_does_not_duplicate_rows(api):
    client, add, audit, *_ = api
    old = add(status="approved", reviewed_at=NOW)
    audit(old, MONDAY - timedelta(seconds=1))
    recent = add(status="approved", reviewed_at=MONDAY - timedelta(days=7))
    audit(recent, MONDAY - timedelta(days=7))
    audit(recent, MONDAY)
    audit(recent, NOW, action="approve")
    rejected = add(status="rejected", reviewed_at=NOW)
    audit(rejected, NOW)
    pending = add(status="pending")
    audit(pending, NOW)
    audit(99999, NOW)  # Deleted/nonexistent scholarship is not a current record.
    assert statistics(client) == ZERO | {
        "pending_count": 1, "approved_this_week": 1, "reviewed_this_week": 2
    }


def test_unrelated_audits_and_updates_cannot_create_weekly_approvals_or_reviews(api):
    client, add, audit, *_ = api
    old = add(
        status="approved", reviewed_at=MONDAY - timedelta(seconds=1),
        updated_at=NOW, scraped_at=NOW,
    )
    audit(old, NOW, action="edit")
    audit(old, NOW, action="publish", entity_type="user")
    add(status="rejected", reviewed_at=MONDAY - timedelta(days=1), updated_at=NOW)
    for status in ("approved", "rejected"):
        add(status=status, updated_at=NOW, scraped_at=NOW)
    assert statistics(client) == ZERO


@pytest.mark.parametrize("now", [
    NOW,
    datetime(2026, 9, 7, tzinfo=timezone.utc),  # Monday exactly.
    datetime(2026, 9, 13, 23, 59, 59, tzinfo=timezone.utc),  # Sunday.
    datetime(2027, 1, 1, 12, tzinfo=timezone.utc),  # Week spans year boundary.
])
def test_week_boundaries_include_monday_and_now_but_exclude_old_and_future_dates(api, now):
    client, add, audit, _, clock = api
    clock.now.return_value = now
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for timestamp in (
        start - timedelta(microseconds=1), start, now,
        now + timedelta(microseconds=1), start + timedelta(days=7),
    ):
        # Test both legacy review timestamps and audit-based approvals.
        add(status="approved", reviewed_at=timestamp)
        item_id = add(status="approved", reviewed_at=timestamp)
        audit(item_id, timestamp)
        add(status="rejected", reviewed_at=timestamp)
    assert statistics(client) == ZERO | {"approved_this_week": 4, "reviewed_this_week": 6}


@pytest.mark.parametrize("source_url", [None, "", "   ", "\t\n\r\f\v", " \n\t "])
def test_missing_source_urls_include_null_empty_and_whitespace_in_all_statuses(api, source_url):
    client, add, *_ = api
    for status in ("pending", "approved", "rejected"):
        add(status=status, source_url=source_url)
    add(source_url=" https://example.com/valid ")
    assert statistics(client) == ZERO | {"pending_count": 2, "missing_source_url_count": 3}


def test_undated_review_is_excluded_even_when_approval_history_is_available(api):
    client, add, audit, *_ = api
    item_id = add(status="approved", reviewed_at=None)
    audit(item_id, NOW)
    assert statistics(client) == ZERO | {"approved_this_week": 1}


@pytest.mark.parametrize("token", [None, "invalid", "student"])
def test_requires_existing_admin_authentication(api, token):
    client = api[0]
    client.headers.pop("Authorization")
    headers = {}
    if token is not None:
        value = create_access_token({"sub": "2", "role": "admin"}) if token == "student" else token
        headers["Authorization"] = f"Bearer {value}"
    response = client.get(PATH, headers=headers)
    existing = client.get("/admin/scholarships/review", headers=headers)
    assert response.status_code == (403 if token == "student" else 401)
    assert response.json() == existing.json()


def test_one_aggregate_query_and_no_writes_regardless_of_scholarship_count(api):
    client, add, _, engine, _ = api
    for _ in range(25):
        add()
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert statistics(client) == ZERO | {"pending_count": 25}
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 2  # Existing user authentication, then one aggregate.
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert "count(" in statements[1].lower()
